import json

from app.ai.llm_provider import LabelSpec
from app.models.enums import ClassificationType

TEXT_PLACEHOLDER = "{{text}}"

_CONSTRAINT_TEXT = {
    ClassificationType.BINARY: "Choose exactly one label.",
    ClassificationType.MULTICLASS: "Choose exactly one label.",
    ClassificationType.MULTILABEL: "Choose zero or more labels that apply. An empty list is a valid answer if none apply.",
}


def _split_criteria(text: str | None) -> list[str]:
    """include_criteria/exclude_criteria are stored as one string, which may
    itself hold multiple bullet points joined by newlines (e.g. from a
    multi-bullet taxonomy import) — split those back out into a proper list
    for the JSON representation, rather than dumping one run-on string."""
    if not text:
        return []
    return [line.strip() for line in text.split("\n") if line.strip()]


def _label_to_dict(label: LabelSpec) -> dict:
    return {
        "name": label.name,
        "description": label.description,
        "include_criteria": _split_criteria(label.include_criteria),
        "exclude_criteria": _split_criteria(label.exclude_criteria),
        "examples": label.examples,
    }


def _example_response(labels: list[LabelSpec], classification_type: ClassificationType) -> str:
    """A concrete, pretty-printed example using real label names when
    available — grounding the format in the actual taxonomy (rather than a
    generic placeholder) helps smaller local models pattern-match it more
    reliably than the compact inline form alone."""
    names = [label.name for label in labels]
    if classification_type == ClassificationType.MULTILABEL:
        example_labels = names[:2] if len(names) >= 2 else names[:1]
    else:
        example_labels = names[:1]
    return json.dumps({"labels": example_labels}, indent=2)


def build_default_prompt(
    labels: list[LabelSpec], classification_type: ClassificationType
) -> str:
    """Generate an initial labeling prompt from the taxonomy.

    The user can edit this freely before saving it as a PromptVersion —
    this is only the starting draft.
    """
    constraint = _CONSTRAINT_TEXT[classification_type]
    labels_json = json.dumps([_label_to_dict(label) for label in labels], indent=2)
    example = _example_response(labels, classification_type)

    return f"""You are classifying a piece of text against a fixed taxonomy of labels.

{constraint}

Labels:
{labels_json}

Text to classify:
\"\"\"
{TEXT_PLACEHOLDER}
\"\"\"

Respond with ONLY a JSON object of the form {{"labels": ["<label name>", ...]}} \
using the exact label names above. Do not include any other text.

Example response:
{example}
"""
