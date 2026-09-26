import json
import re

from app.ai.llm_provider import LabelSpec


def parse_label_names(raw: str) -> list[str]:
    """Best-effort JSON extraction — models occasionally wrap JSON in prose or
    a code fence despite instructions to respond with only JSON."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    labels = data.get("labels", [])
    return [str(name) for name in labels] if isinstance(labels, list) else []


def label_ids_from_names(names: list[str], labels: list[LabelSpec]) -> list[int]:
    by_name = {label.name.strip().lower(): label.id for label in labels}
    return [by_name[name.strip().lower()] for name in names if name.strip().lower() in by_name]
