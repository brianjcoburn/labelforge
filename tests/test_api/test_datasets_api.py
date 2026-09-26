from pathlib import Path

from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.csv"


def _setup_project_with_taxonomy(client: TestClient) -> int:
    project_id = client.post(
        "/api/projects", json={"name": "Complaints", "classification_type": "multiclass"}
    ).json()["id"]
    client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={
            "name": "Complaint Types",
            "labels": [{"name": "Access to Care"}, {"name": "Billing"}],
        },
    )
    return project_id


def test_upload_returns_columns_and_preview(client: TestClient) -> None:
    project_id = _setup_project_with_taxonomy(client)

    with open(FIXTURE, "rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["record_id", "complaint_text", "region", "existing_label"]
    assert len(body["preview_rows"]) == 4


def test_import_creates_records_and_matches_imported_labels(client: TestClient) -> None:
    project_id = _setup_project_with_taxonomy(client)

    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()
    dataset_id = upload["dataset_id"]

    resp = client.post(
        f"/api/projects/{project_id}/datasets/{dataset_id}/import",
        json={
            "name": "Complaints Q1",
            "id_column": "record_id",
            "text_column": "complaint_text",
            "label_column": "existing_label",
            "metadata_columns": ["region"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["record_count"] == 4
    # "Access to Care" and "Billing" match taxonomy labels; "Unmapped Category" doesn't;
    # the 4th row has no label value at all.
    assert body["matched_label_count"] == 2
    assert body["unmatched_label_count"] == 1

    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["record_count"] == 4


def test_import_missing_text_column_rejected(client: TestClient) -> None:
    project_id = _setup_project_with_taxonomy(client)
    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()

    resp = client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "X", "text_column": "does_not_exist"},
    )
    assert resp.status_code == 422


def test_reimporting_same_dataset_conflicts(client: TestClient) -> None:
    project_id = _setup_project_with_taxonomy(client)
    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()
    payload = {"name": "X", "text_column": "complaint_text"}
    dataset_id = upload["dataset_id"]
    assert client.post(
        f"/api/projects/{project_id}/datasets/{dataset_id}/import", json=payload
    ).status_code == 200
    resp = client.post(
        f"/api/projects/{project_id}/datasets/{dataset_id}/import", json=payload
    )
    assert resp.status_code == 409
