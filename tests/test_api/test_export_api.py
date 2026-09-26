import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.csv"


def _setup_labeled_project(client: TestClient) -> tuple[int, list[int]]:
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
        json={
            "name": "D",
            "id_column": "record_id",
            "text_column": "complaint_text",
            "label_column": "existing_label",
            "metadata_columns": ["region"],
        },
    )
    return project_id, label_ids


def test_progress_reflects_outcomes(client: TestClient) -> None:
    project_id, label_ids = _setup_labeled_project(client)

    r1 = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
    client.post(
        f"/api/projects/{project_id}/records/{r1}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[0]]},
    )
    r2 = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
    client.post(
        f"/api/projects/{project_id}/records/{r2}/annotations", json={"outcome": "skipped"}
    )
    r3 = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
    client.post(
        f"/api/projects/{project_id}/records/{r3}/annotations",
        json={"outcome": "flagged", "note": "check"},
    )

    resp = client.get(f"/api/projects/{project_id}/progress")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert body["submitted"] == 1
    assert body["skipped"] == 1
    assert body["flagged"] == 1
    assert body["completed"] == 3
    assert body["remaining"] == 1
    assert body["label_distribution"] == {"Access to Care": 1}


def test_export_annotations_csv(client: TestClient) -> None:
    project_id, label_ids = _setup_labeled_project(client)
    record_id = client.get(f"/api/projects/{project_id}/annotate/next").json()["record"]["id"]
    client.post(
        f"/api/projects/{project_id}/records/{record_id}/annotations",
        json={"outcome": "submitted", "label_ids": [label_ids[1]]},
    )

    resp = client.get(f"/api/projects/{project_id}/export/annotations.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 4  # one row per record, regardless of annotation status
    labeled_row = next(r for r in rows if r["record_id"] == str(record_id))
    assert labeled_row["human_labels"] == "Billing"
    assert labeled_row["annotation_outcome"] == "submitted"
    assert labeled_row["annotation_state"] == "valid"


def test_export_taxonomy_and_config_json(client: TestClient) -> None:
    project_id, _ = _setup_labeled_project(client)

    taxonomy_resp = client.get(f"/api/projects/{project_id}/export/taxonomy.json")
    assert taxonomy_resp.status_code == 200
    taxonomy_body = taxonomy_resp.json()
    assert taxonomy_body["version_number"] == 1
    assert {label["name"] for label in taxonomy_body["labels"]} == {
        "Access to Care",
        "Billing",
    }

    config_resp = client.get(f"/api/projects/{project_id}/export/config.json")
    assert config_resp.status_code == 200
    config_body = config_resp.json()
    assert config_body["classification_type"] == "multiclass"
    # No secret-shaped keys anywhere in the exported config.
    dumped = str(config_body).lower()
    for forbidden in ("api_key", "token", "secret", "password"):
        assert forbidden not in dumped


def test_exported_taxonomy_json_reimports_with_full_fidelity(client: TestClient) -> None:
    """The taxonomy.json export must be re-importable (into a fresh project)
    via the same taxonomy-creation endpoint the UI's "Import from JSON" file
    picker posts to — including examples, which are easy to lose in transit."""
    project_id = client.post(
        "/api/projects", json={"name": "Source", "classification_type": "multiclass"}
    ).json()["id"]
    client.post(
        f"/api/projects/{project_id}/taxonomy",
        json={
            "name": "Complaint Types",
            "labels": [
                {
                    "name": "Access to Care",
                    "description": "Cant get care",
                    "include_criteria": "no appt",
                    "exclude_criteria": "billing issues",
                    "examples": ["couldnt get appointment", "provider unavailable"],
                },
                {"name": "Billing", "description": "payment issues", "examples": ["double charged"]},
            ],
        },
    )
    exported = client.get(f"/api/projects/{project_id}/export/taxonomy.json").json()

    other_project_id = client.post(
        "/api/projects", json={"name": "Destination", "classification_type": "multiclass"}
    ).json()["id"]
    imported = client.post(
        f"/api/projects/{other_project_id}/taxonomy", json=exported
    )
    assert imported.status_code == 201
    body = imported.json()
    by_name = {label["name"]: label for label in body["labels"]}
    assert by_name["Access to Care"]["include_criteria"] == "no appt"
    assert by_name["Access to Care"]["examples"] == [
        "couldnt get appointment",
        "provider unavailable",
    ]
    assert by_name["Billing"]["examples"] == ["double charged"]
