from pathlib import Path

from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.csv"


def _setup_project(client: TestClient, classification_type: str) -> tuple[int, list[int]]:
    project_id = client.post(
        "/api/projects", json={"name": "P", "classification_type": classification_type}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={
            "name": "T",
            "labels": [{"name": "Access to Care"}, {"name": "Billing"}],
        },
    ).json()
    label_ids = [label["id"] for label in taxonomy["labels"]]

    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={
            "name": "D",
            "id_column": "record_id",
            "text_column": "complaint_text",
            "label_column": "existing_label",
            "metadata_columns": ["region"],
        },
    )
    return project_id, label_ids


def test_binary_requires_exactly_one_label(client: TestClient) -> None:
    project_id, label_ids = _setup_project(client, "binary")
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": []},
    )
    assert resp.status_code == 422

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": label_ids},  # both labels
    )
    assert resp.status_code == 422

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[0]]},
    )
    assert resp.status_code == 200
    assert resp.json()["current_labels"] == ["Access to Care"]


def test_multilabel_allows_zero_or_many(client: TestClient) -> None:
    project_id, label_ids = _setup_project(client, "multilabel")
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": []},
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": label_ids},
    )
    assert resp.status_code == 200
    assert set(resp.json()["current_labels"]) == {"Access to Care", "Billing"}


def test_skip_rejects_labels(client: TestClient) -> None:
    project_id, label_ids = _setup_project(client, "multiclass")
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "skipped", "label_ids": [label_ids[0]]},
    )
    assert resp.status_code == 422

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "skipped"},
    )
    assert resp.status_code == 200


def test_flag_sets_needs_review_and_resubmit_sets_reviewed(client: TestClient) -> None:
    project_id, label_ids = _setup_project(client, "multiclass")
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "flagged", "note": "ambiguous wording"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "needs_review"
    assert len(body["revisions"]) == 1

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[0]]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "reviewed"
    assert len(body["revisions"]) == 2
    # First revision is preserved untouched — history is append-only.
    assert body["revisions"][0]["outcome"] == "flagged"
    assert body["revisions"][0]["note"] == "ambiguous wording"
    assert body["revisions"][1]["outcome"] == "submitted"


def test_editing_annotation_preserves_history_and_provenance(client: TestClient) -> None:
    project_id, label_ids = _setup_project(client, "multiclass")
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[0]]},
    )
    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[1]]},
    )
    body = resp.json()
    assert len(body["revisions"]) == 2
    assert body["revisions"][0]["label_names"] == ["Access to Care"]
    assert body["revisions"][1]["label_names"] == ["Billing"]
    assert body["current_labels"] == ["Billing"]
    for rev in body["revisions"]:
        assert rev["annotator_id"]
        assert rev["taxonomy_version_id"]
        assert rev["created_at"]


def test_invalid_label_id_rejected(client: TestClient) -> None:
    project_id, _ = _setup_project(client, "multiclass")
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [99999]},
    )
    assert resp.status_code == 422


def test_progress_advances_and_next_excludes_annotated(client: TestClient) -> None:
    project_id, label_ids = _setup_project(client, "multiclass")

    first = client.get(f"/api/projects/{project_id}/annotate/next").json()
    assert first["progress"] == {"completed": 0, "total": 4}
    record_id = first["record"]["id"]

    client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[0]]},
    )

    second = client.get(f"/api/projects/{project_id}/annotate/next").json()
    assert second["progress"] == {"completed": 1, "total": 4}
    assert second["record"]["id"] != record_id


def test_annotate_next_returns_none_when_all_done(client: TestClient) -> None:
    project_id, label_ids = _setup_project(client, "multiclass")
    for _ in range(4):
        record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "skipped"},
        )

    final = client.get(f"/api/projects/{project_id}/annotate/next").json()
    assert final["record"] is None
    assert final["progress"] == {"completed": 4, "total": 4}


def test_ai_first_mode_shows_imported_suggestion(client: TestClient) -> None:
    project_id, _ = _setup_project(client, "multiclass")
    client.patch(f"/api/projects/{project_id}/settings", json={"annotation_mode": "ai_first"})

    # Walk records until we find the one whose imported label matched the taxonomy.
    found_suggestion = False
    for _ in range(4):
        next_resp = client.get(f"/api/projects/{project_id}/annotate/next").json()
        record_id = next_resp["record"]["id"]
        if next_resp["suggestion"] is not None:
            assert next_resp["suggestion"]["source"] == "imported"
            found_suggestion = True
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "skipped"},
        )
    assert found_suggestion


def test_human_first_mode_hides_suggestion_and_existing_label(client: TestClient) -> None:
    project_id, _ = _setup_project(client, "multiclass")
    client.patch(
        f"/api/projects/{project_id}/settings", json={"annotation_mode": "human_first"}
    )

    for _ in range(4):
        next_resp = client.get(f"/api/projects/{project_id}/annotate/next").json()
        assert next_resp["suggestion"] is None
        assert next_resp["record"]["existing_label_raw"] is None
        record_id = next_resp["record"]["id"]
        client.post(
            f"/api/projects/{project_id}/records/{record_id}/annotations",
            json={"outcome": "skipped"},
        )
