from pathlib import Path

from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.csv"


def _setup_project(client: TestClient) -> tuple[int, list[int]]:
    project_id = client.post(
        "/api/projects", json={"name": "P", "classification_type": "multiclass"}
    ).json()["id"]
    taxonomy = client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={"name": "T", "labels": [{"name": "Access to Care"}, {"name": "Billing"}]},
    ).json()
    label_ids = [label["id"] for label in taxonomy["labels"]]
    with open(FIXTURE, "rb") as f:
        upload = client.post(
            f"/api/projects/{project_id}/datasets/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        ).json()
    client.post(
        f"/api/projects/{project_id}/datasets/{upload['dataset_id']}/import",
        json={"name": "D", "text_column": "complaint_text"},  # no label_column this time
    )
    return project_id, label_ids


def test_ai_first_generates_and_caches_llm_suggestion(client: TestClient, fake_llm) -> None:
    project_id, label_ids = _setup_project(client)
    client.patch(f"/api/projects/{project_id}/settings", json={"annotation_mode": "ai_first"})

    first = client.get(f"/api/projects/{project_id}/annotate/next").json()
    assert first["suggestion"]["source"] == "llm"
    assert first["suggestion"]["label_names"] == ["Access to Care"]
    assert len(fake_llm.calls) == 1

    # Re-fetching the same unlabeled record must reuse the cached prediction,
    # not call the provider again.
    again = client.get(f"/api/projects/{project_id}/annotate/next").json()
    assert again["record"]["id"] == first["record"]["id"]
    assert len(fake_llm.calls) == 1


def test_on_demand_hides_until_reveal_requested(client: TestClient, fake_llm) -> None:
    project_id, _ = _setup_project(client)
    # on_demand is the default annotation_mode

    hidden = client.get(f"/api/projects/{project_id}/annotate/next").json()
    assert hidden["suggestion"] is None
    assert len(fake_llm.calls) == 0

    revealed = client.get(
        f"/api/projects/{project_id}/annotate/next?reveal_suggestion=true"
    ).json()
    assert revealed["suggestion"]["source"] == "llm"
    assert len(fake_llm.calls) == 1


def test_human_first_reveals_suggestion_only_after_submit(client: TestClient, fake_llm) -> None:
    project_id, label_ids = _setup_project(client)
    client.patch(
        f"/api/projects/{project_id}/settings", json={"annotation_mode": "human_first"}
    )

    next_resp = client.get(f"/api/projects/{project_id}/annotate/next").json()
    assert next_resp["suggestion"] is None
    assert len(fake_llm.calls) == 0
    record_id = next_resp["record"]["id"]

    submit_resp = client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[1]]},  # human picks Billing
    )
    assert submit_resp.status_code == 200
    body = submit_resp.json()
    assert body["revealed_suggestion"]["source"] == "llm"
    assert body["revealed_suggestion"]["label_names"] == ["Access to Care"]
    # Human's own submitted choice is unaffected by the revealed suggestion.
    assert body["current_labels"] == ["Billing"]
    assert body["revisions"][0]["saw_suggestion_before_submit"] is False


def test_llm_agreement_in_progress(client: TestClient, fake_llm) -> None:
    project_id, label_ids = _setup_project(client)
    client.patch(f"/api/projects/{project_id}/settings", json={"annotation_mode": "ai_first"})

    # Record 1: human agrees with the (fake) LLM suggestion ("Access to Care").
    r1 = client.get(f"/api/projects/{project_id}/annotate/next").json()
    client.post(
        f"/api/projects/{project_id}/records/{r1['record']['id']}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[0]]},
    )
    # Record 2: human disagrees, picks Billing instead.
    r2 = client.get(f"/api/projects/{project_id}/annotate/next").json()
    client.post(
        f"/api/projects/{project_id}/records/{r2['record']['id']}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[1]]},
    )

    progress = client.get(f"/api/projects/{project_id}/progress").json()
    assert progress["llm_agreement"] == 50.0
