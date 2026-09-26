from fastapi.testclient import TestClient


def test_local_catalog_lists_expected_brands(client: TestClient) -> None:
    resp = client.get("/api/models/local/catalog")
    assert resp.status_code == 200
    body = resp.json()
    brands = {entry["brand"] for entry in body}
    assert brands == {"Mistral AI", "Google", "OpenAI"}
    assert all(entry["downloaded"] is False for entry in body)


def test_download_unknown_model_404s(client: TestClient) -> None:
    resp = client.post("/api/models/local/not-a-real-model/download")
    assert resp.status_code == 404


def test_project_settings_expose_llm_provider_fields(client: TestClient) -> None:
    project_id = client.post(
        "/api/projects", json={"name": "P", "classification_type": "binary"}
    ).json()["id"]

    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["settings"]["llm_provider"] == "local"
    assert detail["settings"]["local_model_id"] is None

    resp = client.patch(
        f"/api/projects/{project_id}/settings",
        json={"llm_provider": "local", "local_model_id": "mistral-7b-instruct"},
    )
    assert resp.status_code == 200
    assert resp.json()["local_model_id"] == "mistral-7b-instruct"

    resp = client.patch(
        f"/api/projects/{project_id}/settings", json={"llm_provider": "anthropic"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_provider"] == "anthropic"
    # Switching provider doesn't silently wipe the previously chosen local model.
    assert body["local_model_id"] == "mistral-7b-instruct"


def test_no_provider_configured_falls_back_gracefully(client: TestClient) -> None:
    """Real factory (not the fake_llm fixture): local provider selected but no
    model downloaded yet must degrade to 'no suggestion', never error, on the
    main annotation-reading path."""
    project_id = client.post(
        "/api/projects", json={"name": "P", "classification_type": "binary"}
    ).json()["id"]
    client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "A"}, {"name": "B"}]},
    )
    client.patch(f"/api/projects/{project_id}/settings", json={"annotation_mode": "ai_first"})

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

    resp = client.get(f"/api/projects/{project_id}/annotate/next")
    assert resp.status_code == 200
    assert resp.json()["suggestion"] is None
