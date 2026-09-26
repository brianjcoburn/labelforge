from fastapi.testclient import TestClient

BINARY_TEXTS = [
    ("The staff was incredibly kind and helpful during my visit.", "Positive"),
    ("I loved the service, everyone was so friendly.", "Positive"),
    ("Great experience overall, would recommend to others.", "Positive"),
    ("Wonderful care and a very pleasant waiting room.", "Positive"),
    ("The doctor explained everything clearly and I felt at ease.", "Positive"),
    ("Terrible service, I waited two hours for nothing.", "Negative"),
    ("Very rude staff and a dirty waiting area.", "Negative"),
    ("Awful experience, I will never come back here.", "Negative"),
    ("The billing department overcharged me and was unhelpful.", "Negative"),
    ("Disappointing visit, nobody seemed to care at all.", "Negative"),
    ("Absolutely fantastic, the nurses were wonderful people.", "Positive"),
    ("Horrible wait times and an unpleasant front desk.", "Negative"),
]


def _setup_binary_project_with_annotations(client: TestClient) -> tuple[int, list[int]]:
    project_id = client.post(
        "/api/projects", json={"name": "Sentiment", "classification_type": "binary"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Positive"}, {"name": "Negative"}]},
    ).json()
    by_name = {label["name"]: label["id"] for label in taxonomy["labels"]}

    csv_lines = ["record_id,text"]
    for i, (text, _label) in enumerate(BINARY_TEXTS):
        csv_lines.append(f'{i},"{text}"')
    csv_content = "\n".join(csv_lines)

    upload = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("data.csv", csv_content, "text/csv")},
    ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "id_column": "record_id", "text_column": "text"},
    )

    label_ids = []
    for _text, label_name in BINARY_TEXTS:
        record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "submitted", "label_ids": [by_name[label_name]]},
        )
        label_ids.append(by_name[label_name])
    return project_id, label_ids


def test_train_now_requires_minimum_examples(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Tiny", "classification_type": "binary"}
    ).json()["id"]
    client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    )
    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 422


def test_train_now_produces_model_with_evaluation_metrics(client: TestClient) -> None:
    project_id, _ = _setup_binary_project_with_annotations(client)

    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 201
    body = resp.json()
    assert body["version_number"] == 1
    assert body["classifier_type"] == "tfidf_logistic"
    assert body["state"] == "inactive"

    metrics = body["metrics_json"]
    assert "accuracy" in metrics
    assert "macro_f1" in metrics
    assert "confusion_matrix" in metrics
    assert metrics["n_train"] + metrics["n_held_out"] == len(BINARY_TEXTS)

    runs = client.get(f"/api/projects/{project_id}/training-runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["resulting_model_version_id"] == body["id"]


def test_train_now_twice_increments_version(client: TestClient) -> None:
    project_id, _ = _setup_binary_project_with_annotations(client)
    v1 = client.post(f"/api/projects/{project_id}/models/train").json()
    v2 = client.post(f"/api/projects/{project_id}/models/train").json()
    assert v1["version_number"] == 1
    assert v2["version_number"] == 2

    models = client.get(f"/api/projects/{project_id}/models").json()
    assert [m["version_number"] for m in models] == [2, 1]


def test_activate_model_deactivates_previous(client: TestClient) -> None:
    project_id, _ = _setup_binary_project_with_annotations(client)
    v1 = client.post(f"/api/projects/{project_id}/models/train").json()
    v2 = client.post(f"/api/projects/{project_id}/models/train").json()

    resp = client.post(f"/api/projects/{project_id}/models/{v1['id']}/activate")
    assert resp.status_code == 200
    assert resp.json()["state"] == "active"

    resp = client.post(f"/api/projects/{project_id}/models/{v2['id']}/activate")
    assert resp.status_code == 200
    assert resp.json()["state"] == "active"

    models = {m["id"]: m for m in client.get(f"/api/projects/{project_id}/models").json()}
    assert models[v1["id"]]["state"] == "inactive"
    assert models[v1["id"]]["deactivated_at"] is not None
    assert models[v2["id"]]["state"] == "active"


def test_activate_unknown_model_404s(client: TestClient) -> None:
    project_id, _ = _setup_binary_project_with_annotations(client)
    resp = client.post(f"/api/projects/{project_id}/models/999999/activate")
    assert resp.status_code == 404


def test_multiclass_training_and_metrics_shape(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Triage", "classification_type": "multiclass"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Billing"}, {"name": "Access"}, {"name": "Quality"}]},
    ).json()
    by_name = {label["name"]: label["id"] for label in taxonomy["labels"]}

    samples = [
        ("I was overcharged on my bill.", "Billing"),
        ("The invoice had the wrong amount.", "Billing"),
        ("My payment was processed twice.", "Billing"),
        ("I could not get an appointment for weeks.", "Access"),
        ("There were no available providers near me.", "Access"),
        ("Scheduling was impossible this month.", "Access"),
        ("The doctor was dismissive of my concerns.", "Quality"),
        ("The care I received felt rushed and careless.", "Quality"),
        ("Staff seemed poorly trained for the procedure.", "Quality"),
        ("Another billing statement arrived with an error.", "Billing"),
        ("Still cannot book a visit with any specialist.", "Access"),
        ("The exam felt incomplete and unprofessional.", "Quality"),
    ]
    csv_lines = ["record_id,text"] + [f'{i},"{t}"' for i, (t, _) in enumerate(samples)]
    upload = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("data.csv", "\n".join(csv_lines), "text/csv")},
    ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "id_column": "record_id", "text_column": "text"},
    )
    for _text, label_name in samples:
        record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "submitted", "label_ids": [by_name[label_name]]},
        )

    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 201
    metrics = resp.json()["metrics_json"]
    assert "per_class" in metrics
    assert "roc_auc" not in metrics  # binary-only metric, must not appear for multiclass


def test_multilabel_training_and_metrics_shape(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Multi", "classification_type": "multilabel"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Urgent"}, {"name": "Billing"}]},
    ).json()
    by_name = {label["name"]: label["id"] for label in taxonomy["labels"]}

    samples = [
        ("This needs attention right away, it's an emergency.", ["Urgent"]),
        ("Please handle this urgently, the situation is critical.", ["Urgent"]),
        ("I was charged twice for the same visit.", ["Billing"]),
        ("My invoice has an incorrect amount on it.", ["Billing"]),
        ("Urgent billing issue, I was overcharged and need this fixed now.", ["Urgent", "Billing"]),
        ("This billing error is urgent and needs immediate correction.", ["Urgent", "Billing"]),
        ("Just a general question about my appointment next month.", []),
        ("Wondering about your office hours on weekends.", []),
        ("Emergency: my prescription was never filled.", ["Urgent"]),
        ("The statement I received doesn't match what I paid.", ["Billing"]),
        ("Nothing urgent, just checking on my account balance.", ["Billing"]),
        ("Curious about parking near the clinic.", []),
    ]
    csv_lines = ["record_id,text"] + [f'{i},"{t}"' for i, (t, _) in enumerate(samples)]
    upload = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("data.csv", "\n".join(csv_lines), "text/csv")},
    ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "id_column": "record_id", "text_column": "text"},
    )
    for _text, names in samples:
        record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "submitted", "label_ids": [by_name[n] for n in names]},
        )

    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 201
    metrics = resp.json()["metrics_json"]
    assert "micro_f1" in metrics
    assert "macro_f1" in metrics
    assert "hamming_loss" in metrics
    assert set(metrics["per_label"].keys()) == {"Urgent", "Billing"}
