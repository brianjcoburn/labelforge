from fastapi.testclient import TestClient


def _setup_project(client: TestClient) -> tuple[int, list[int]]:
    project_id = client.post(
        "/api/projects", json={"name": "P", "classification_type": "binary"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Positive"}, {"name": "Negative"}]},
    ).json()
    return project_id, [label["id"] for label in taxonomy["labels"]]


def test_generate_draft_includes_label_definitions(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "P", "classification_type": "binary"}
    ).json()["id"]
    client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={
            "name": "T",
            "labels": [
                {"name": "Positive", "description": "Happy sentiment"},
                {"name": "Negative", "description": "Unhappy sentiment"},
            ],
        },
    )
    resp = client.post(f"/api/projects/{project_id}/prompts/generate")
    assert resp.status_code == 200
    text = resp.json()["template_text"]
    assert "Positive" in text and "Happy sentiment" in text
    assert "{{text}}" in text


def test_create_list_and_activate_prompt_version(client: TestClient) -> None:
    project_id, _ = _setup_project(client)

    v1 = client.post(
        f"/api/projects/{project_id}/prompts", json={"template_text": "Classify: {{text}}"}
    )
    assert v1.status_code == 201
    assert v1.json()["version_number"] == 1
    assert v1.json()["is_active"] is False

    v2 = client.post(
        f"/api/projects/{project_id}/prompts", json={"template_text": "v2 {{text}}"}
    ).json()
    assert v2["version_number"] == 2

    activated = client.post(f"/api/projects/{project_id}/prompts/{v2['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True

    versions = client.get(f"/api/projects/{project_id}/prompts").json()
    active_flags = {v["id"]: v["is_active"] for v in versions}
    assert active_flags[v2["id"]] is True
    assert active_flags[v1.json()["id"]] is False


def test_test_prompt_without_provider_configured_errors(client: TestClient) -> None:
    project_id, _ = _setup_project(client)
    from pathlib import Path

    fixture = Path(__file__).parent.parent / "fixtures" / "sample.csv"
    with open(fixture, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "text_column": "complaint_text"},
    )
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    resp = client.post(
        f"/api/projects/{project_id}/prompts/test",
        json={"record_id": record_id},
    )
    assert resp.status_code == 422


def test_test_prompt_with_fake_provider(client: TestClient, fake_llm) -> None:
    project_id, label_ids = _setup_project(client)
    from pathlib import Path

    fixture = Path(__file__).parent.parent / "fixtures" / "sample.csv"
    with open(fixture, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "text_column": "complaint_text"},
    )
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]

    resp = client.post(
        f"/api/projects/{project_id}/prompts/test",
        json={"record_id": record_id, "template_text": "Classify: {{text}}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_label_names"] == ["Positive"]  # FakeLLMProvider default
    assert len(fake_llm.calls) == 1
