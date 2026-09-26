from fastapi.testclient import TestClient


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
