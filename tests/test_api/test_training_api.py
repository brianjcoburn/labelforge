from fastapi.testclient import TestClient

# Per-label phrase pools distinctive enough for a bag-of-words model (the
# FakeClassifier fixture) to actually learn the boundary, per the new
# bootstrap floor (>=20 confirmed examples per class, >=150 total).
_POSITIVE_PHRASES = [
    "The staff was incredibly kind and helpful during my visit",
    "I loved the service, everyone was so friendly",
    "Great experience overall, would recommend to others",
    "Wonderful care and a very pleasant waiting room",
    "The doctor explained everything clearly and I felt at ease",
    "Absolutely fantastic, the nurses were wonderful people",
    "Everyone made me feel welcome and comfortable",
    "Such a pleasant and reassuring appointment",
    "Truly excellent bedside manner from the whole team",
    "I felt genuinely cared for throughout the visit",
]
_NEGATIVE_PHRASES = [
    "Terrible service, I waited two hours for nothing",
    "Very rude staff and a dirty waiting area",
    "Awful experience, I will never come back here",
    "The billing department overcharged me and was unhelpful",
    "Disappointing visit, nobody seemed to care at all",
    "Horrible wait times and an unpleasant front desk",
    "Rude and dismissive from the moment I arrived",
    "A frustrating and unpleasant ordeal from start to finish",
    "The whole visit felt careless and disorganized",
    "Extremely unhappy with how I was treated",
]


def _bulk_texts(phrases: list[str], n: int) -> list[str]:
    """Repeats/varies a phrase pool out to n distinct-enough sentences."""
    out = []
    for i in range(n):
        out.append(f"{phrases[i % len(phrases)]} (visit #{i}).")
    return out


def _import_and_label(
    client: TestClient, project_id: int, texts_by_label: dict[str, list[str]], label_ids: dict[str, int]
) -> None:
    rows = []
    order: list[str] = []
    idx = 0
    for label_name, texts in texts_by_label.items():
        for text in texts:
            rows.append(f'{idx},"{text}"')
            order.append(label_name)
            idx += 1
    csv_content = "record_id,text\n" + "\n".join(rows)

    upload = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("data.csv", csv_content, "text/csv")},
    ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "id_column": "record_id", "text_column": "text"},
    )
    for label_name in order:
        record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "submitted", "label_ids": [label_ids[label_name]]},
        )


def _setup_binary_project(client: TestClient, per_class: int = 80) -> tuple[int, dict[str, int]]:
    project_id = client.post(
        "/api/projects", json={"name": "Sentiment", "classification_type": "binary"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Positive"}, {"name": "Negative"}]},
    ).json()
    label_ids = {label["name"]: label["id"] for label in taxonomy["labels"]}
    _import_and_label(
        client,
        project_id,
        {
            "Positive": _bulk_texts(_POSITIVE_PHRASES, per_class),
            "Negative": _bulk_texts(_NEGATIVE_PHRASES, per_class),
        },
        label_ids,
    )
    return project_id, label_ids


def test_train_now_requires_minimum_examples(client: TestClient, fake_classifier) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Tiny", "classification_type": "binary"}
    ).json()["id"]
    client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    )
    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 422
    assert "confirmed" in resp.json()["detail"].lower()


def test_bootstrap_status_reports_per_class_gaps(client: TestClient, fake_classifier) -> None:
    project_id, label_ids = _setup_binary_project(client, per_class=5)
    resp = client.get(f"/api/projects/{project_id}/models/bootstrap-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    assert set(body["classes_under_floor"].keys()) == {"Positive", "Negative"}


def test_train_now_produces_model_with_evaluation_metrics(client: TestClient, fake_classifier) -> None:
    project_id, _ = _setup_binary_project(client, per_class=80)

    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 201
    body = resp.json()
    assert body["version_number"] == 1
    assert body["classifier_type"] == "transformer"
    assert body["state"] == "inactive"

    metrics = body["metrics_json"]
    assert "accuracy" in metrics
    assert "macro_f1" in metrics
    assert "confusion_matrix" in metrics
    assert metrics["n_train"] + metrics["n_held_out"] == 160

    runs = client.get(f"/api/projects/{project_id}/training-runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["trigger"] == "manual"
    assert runs[0]["resulting_model_version_id"] == body["id"]


def test_frozen_holdout_persists_across_training_runs(client: TestClient, fake_classifier) -> None:
    project_id, _ = _setup_binary_project(client, per_class=80)
    v1 = client.post(f"/api/projects/{project_id}/models/train").json()
    v2 = client.post(f"/api/projects/{project_id}/models/train").json()
    # Same held-out set size both times -> the split wasn't re-randomized.
    assert v1["metrics_json"]["n_held_out"] == v2["metrics_json"]["n_held_out"]
    assert v1["metrics_json"]["n_train"] == v2["metrics_json"]["n_train"]


def test_train_now_twice_increments_version(client: TestClient, fake_classifier) -> None:
    project_id, _ = _setup_binary_project(client, per_class=80)
    v1 = client.post(f"/api/projects/{project_id}/models/train").json()
    v2 = client.post(f"/api/projects/{project_id}/models/train").json()
    assert v1["version_number"] == 1
    assert v2["version_number"] == 2

    models = client.get(f"/api/projects/{project_id}/models").json()
    assert [m["version_number"] for m in models] == [2, 1]


def test_activate_model_deactivates_previous(client: TestClient, fake_classifier) -> None:
    project_id, _ = _setup_binary_project(client, per_class=80)
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


def test_activate_unknown_model_404s(client: TestClient, fake_classifier) -> None:
    project_id, _ = _setup_binary_project(client, per_class=80)
    resp = client.post(f"/api/projects/{project_id}/models/999999/activate")
    assert resp.status_code == 404


def test_multiclass_training_and_metrics_shape(client: TestClient, fake_classifier) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Triage", "classification_type": "multiclass"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Billing"}, {"name": "Access"}, {"name": "Quality"}]},
    ).json()
    label_ids = {label["name"]: label["id"] for label in taxonomy["labels"]}

    billing = [
        "I was overcharged on my bill",
        "The invoice had the wrong amount",
        "My payment was processed twice",
        "Another billing statement arrived with an error",
        "The charges on my account don't add up",
    ]
    access = [
        "I could not get an appointment for weeks",
        "There were no available providers near me",
        "Scheduling was impossible this month",
        "Still cannot book a visit with any specialist",
        "No openings anywhere for a routine checkup",
    ]
    quality = [
        "The doctor was dismissive of my concerns",
        "The care I received felt rushed and careless",
        "Staff seemed poorly trained for the procedure",
        "The exam felt incomplete and unprofessional",
        "My concerns were not taken seriously at all",
    ]
    _import_and_label(
        client,
        project_id,
        {
            "Billing": _bulk_texts(billing, 55),
            "Access": _bulk_texts(access, 55),
            "Quality": _bulk_texts(quality, 55),
        },
        label_ids,
    )

    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 201
    metrics = resp.json()["metrics_json"]
    assert "per_class" in metrics
    assert "roc_auc" not in metrics  # binary-only metric, must not appear for multiclass


def test_multilabel_training_and_metrics_shape(client: TestClient, fake_classifier) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Multi", "classification_type": "multilabel"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Urgent"}, {"name": "Billing"}]},
    ).json()
    label_ids = {label["name"]: label["id"] for label in taxonomy["labels"]}

    urgent_texts = _bulk_texts(
        ["This needs attention right away, it's an emergency",
         "Please handle this urgently, the situation is critical",
         "Emergency: my prescription was never filled"], 40,
    )
    billing_texts = _bulk_texts(
        ["I was charged twice for the same visit",
         "My invoice has an incorrect amount on it",
         "The statement I received doesn't match what I paid"], 40,
    )
    both_texts = _bulk_texts(
        ["Urgent billing issue, I was overcharged and need this fixed now",
         "This billing error is urgent and needs immediate correction"], 40,
    )
    none_texts = _bulk_texts(
        ["Just a general question about my appointment next month",
         "Wondering about your office hours on weekends",
         "Curious about parking near the clinic"], 40,
    )

    rows = []
    labels_per_row: list[list[str]] = []
    idx = 0
    for text in urgent_texts:
        rows.append(f'{idx},"{text}"')
        labels_per_row.append(["Urgent"])
        idx += 1
    for text in billing_texts:
        rows.append(f'{idx},"{text}"')
        labels_per_row.append(["Billing"])
        idx += 1
    for text in both_texts:
        rows.append(f'{idx},"{text}"')
        labels_per_row.append(["Urgent", "Billing"])
        idx += 1
    for text in none_texts:
        rows.append(f'{idx},"{text}"')
        labels_per_row.append([])
        idx += 1

    upload = client.post(
        f"/api/projects/{project_id}/datasets/upload",
        files={"file": ("data.csv", "record_id,text\n" + "\n".join(rows), "text/csv")},
    ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "id_column": "record_id", "text_column": "text"},
    )
    for names in labels_per_row:
        record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "submitted", "label_ids": [label_ids[n] for n in names]},
        )

    resp = client.post(f"/api/projects/{project_id}/models/train")
    assert resp.status_code == 201
    metrics = resp.json()["metrics_json"]
    assert "micro_f1" in metrics
    assert "macro_f1" in metrics
    assert "hamming_loss" in metrics
    assert set(metrics["per_label"].keys()) == {"Urgent", "Billing"}


def test_never_activated_model_artifact_is_not_pruned(client: TestClient, fake_classifier, db_session) -> None:
    """Regression test: a freshly trained, never-yet-activated model's
    artifact must survive on disk (caught live — the pruning logic was
    deleting it immediately after training, before anyone could activate it)."""
    import os

    from app.models.model import ModelVersion

    project_id, _ = _setup_binary_project(client, per_class=80)
    model = client.post(f"/api/projects/{project_id}/models/train").json()
    assert model["state"] == "inactive"

    artifact_path = db_session.get(ModelVersion, model["id"]).artifact_path
    assert artifact_path is not None
    assert os.path.exists(artifact_path), f"artifact was pruned before activation: {artifact_path}"


def test_auto_activation_when_automation_enabled(client: TestClient, fake_classifier) -> None:
    project_id, _ = _setup_binary_project(client, per_class=80)
    client.patch(f"/api/projects/{project_id}/settings", json={"automation_enabled": True})

    v1 = client.post(f"/api/projects/{project_id}/models/train").json()
    # First model ever: auto-activates unconditionally.
    assert v1["state"] == "active"

    v2 = client.post(f"/api/projects/{project_id}/models/train").json()
    # Retrained on the exact same data -> should score the same and, being a
    # tie (not a regression), also auto-activate.
    assert v2["state"] == "active"
    models = {m["id"]: m for m in client.get(f"/api/projects/{project_id}/models").json()}
    assert models[v1["id"]]["state"] == "inactive"
