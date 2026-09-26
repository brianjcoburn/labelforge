from pathlib import Path

from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.csv"


def test_create_and_get_project(client: TestClient) -> None:
    resp = client.post(
        "/api/projects",
        json={"name": "Complaint Triage", "classification_type": "multiclass"},
    )
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Complaint Triage"
    assert body["has_taxonomy"] is False
    assert body["record_count"] == 0
    assert body["settings"]["annotation_mode"] == "on_demand"
    assert body["settings"]["sampling_strategy"] == "random"


def test_list_projects(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "A", "classification_type": "binary"})
    client.post("/api/projects", json={"name": "B", "classification_type": "binary"})

    resp = client.get("/api/projects")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"A", "B"}


def test_get_unknown_project_404(client: TestClient) -> None:
    resp = client.get("/api/projects/999")
    assert resp.status_code == 404


def test_update_settings(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "C", "classification_type": "multilabel"}
    ).json()["id"]

    resp = client.patch(
        f"/api/projects/{project_id}/settings",
        json={"annotation_mode": "ai_first", "batch_training_threshold": 50},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["annotation_mode"] == "ai_first"
    assert body["batch_training_threshold"] == 50
    # Untouched fields keep their defaults
    assert body["sampling_strategy"] == "random"


def test_delete_project_requires_matching_name(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Delete Me", "classification_type": "binary"}
    ).json()["id"]

    resp = client.delete(f"/api/projects/{project_id}", params={"confirm_name": "Wrong Name"})
    assert resp.status_code == 422
    # Still there.
    assert client.get(f"/api/projects/{project_id}").status_code == 200

    resp = client.delete(f"/api/projects/{project_id}", params={"confirm_name": "Delete Me"})
    assert resp.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_delete_unknown_project_404s(client: TestClient) -> None:
    resp = client.delete("/api/projects/999999", params={"confirm_name": "anything"})
    assert resp.status_code == 404


def test_delete_project_removes_everything_under_it(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "Full Project", "classification_type": "multiclass"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    ).json()
    label_id = taxonomy["labels"][0]["id"]

    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "text_column": "complaint_text"},
    )
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
    client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_id]},
    )
    client.post(f"/api/projects/{project_id}/prompts", json={"template_text": "hello {{text}}"})

    resp = client.delete(f"/api/projects/{project_id}", params={"confirm_name": "Full Project"})
    assert resp.status_code == 204

    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get(f"/api/projects/{project_id}/taxonomy").status_code == 404
    assert client.get(f"/api/projects/{project_id}/prompts").status_code == 200
    assert client.get(f"/api/projects/{project_id}/prompts").json() == []

    # A new project can reuse the same ids without collision (autoincrement
    # keeps advancing, but nothing from the old project should leak through).
    other_id = client.post(
        "/api/projects", json={"name": "Fresh One", "classification_type": "binary"}
    ).json()["id"]
    assert client.get(f"/api/projects/{other_id}").json()["record_count"] == 0
