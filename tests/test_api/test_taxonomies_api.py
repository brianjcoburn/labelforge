from fastapi.testclient import TestClient


def _create_project(client: TestClient, classification_type: str) -> int:
    resp = client.post(
        "/api/projects", json={"name": "P", "classification_type": classification_type}
    )
    return resp.json()["id"]


def test_create_taxonomy_binary_requires_exactly_two_labels(client: TestClient) -> None:
    project_id = _create_project(client, "binary")

    resp = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Yes"}]},
    )
    assert resp.status_code == 422

    resp = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Yes"}, {"name": "No"}]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["active_version_number"] == 1
    assert [label_name["name"] for label_name in body["labels"]] == ["Yes", "No"]


def test_create_taxonomy_multilabel_allows_one_label(client: TestClient) -> None:
    project_id = _create_project(client, "multilabel")

    resp = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Urgent"}]},
    )
    assert resp.status_code == 201


def test_create_taxonomy_duplicate_names_rejected(client: TestClient) -> None:
    project_id = _create_project(client, "multiclass")

    resp = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "a"}]},
    )
    assert resp.status_code == 422


def test_second_taxonomy_conflicts(client: TestClient) -> None:
    project_id = _create_project(client, "multiclass")
    payload = {"name": "T", "labels": [{"name": "A"}, {"name": "B"}]}
    assert client.post(f"/api/projects/{project_id}/taxonomy", json=payload).status_code == 201
    resp = client.post(f"/api/projects/{project_id}/taxonomy", json=payload)
    assert resp.status_code == 409


def test_get_taxonomy_for_project_without_one_404s(client: TestClient) -> None:
    project_id = _create_project(client, "multiclass")
    resp = client.get(f"/api/projects/{project_id}/taxonomy")
    assert resp.status_code == 404


def test_update_label_include_exclude(client: TestClient) -> None:
    project_id = _create_project(client, "multiclass")
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    ).json()
    label_id = taxonomy["labels"][0]["id"]

    resp = client.patch(
        f"/api/projects/{project_id}/taxonomy/labels/{label_id}",
        json={
            "description": "Definition text",
            "include_criteria": "include this",
            "exclude_criteria": "exclude that",
            "examples": ["ex1", "ex2"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["include_criteria"] == "include this"
    assert body["exclude_criteria"] == "exclude that"
    assert body["examples"] == ["ex1", "ex2"]

    # Persisted, not just returned — confirm via a fresh GET.
    refetched = client.get(f"/api/projects/{project_id}/taxonomy").json()
    updated = next(l for l in refetched["labels"] if l["id"] == label_id)
    assert updated["include_criteria"] == "include this"


def test_update_label_rename(client: TestClient) -> None:
    project_id = _create_project(client, "multiclass")
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    ).json()
    label_id = taxonomy["labels"][0]["id"]

    resp = client.patch(
        f"/api/projects/{project_id}/taxonomy/labels/{label_id}", json={"name": "Renamed"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_update_label_rejects_name_collision(client: TestClient) -> None:
    project_id = _create_project(client, "multiclass")
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    ).json()
    label_id = taxonomy["labels"][0]["id"]

    resp = client.patch(
        f"/api/projects/{project_id}/taxonomy/labels/{label_id}", json={"name": "b"}
    )
    assert resp.status_code == 422


def test_update_unknown_label_404s(client: TestClient) -> None:
    project_id = _create_project(client, "multiclass")
    client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    )
    resp = client.patch(
        f"/api/projects/{project_id}/taxonomy/labels/999999", json={"name": "X"}
    )
    assert resp.status_code == 404
