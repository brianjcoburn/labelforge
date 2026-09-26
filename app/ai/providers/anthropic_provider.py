import json
import re

import anthropic

from app.ai.llm_provider import ClassificationResult, LabelSpec, LLMProvider
from app.ai.prompt_builder import TEXT_PLACEHOLDER, build_default_prompt
from app.models.enums import ClassificationType


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def classify(
        self,
        text: str,
        labels: list[LabelSpec],
        *,
        classification_type: ClassificationType,
        prompt_template: str | None = None,
    ) -> ClassificationResult:
        template = prompt_template or build_default_prompt(labels, classification_type)
        if TEXT_PLACEHOLDER in template:
            prompt = template.replace(TEXT_PLACEHOLDER, text)
        else:
            # A hand-edited prompt that dropped the placeholder — append the
            # text rather than fail outright.
            prompt = f"{template}\n\nText to classify:\n\"\"\"\n{text}\n\"\"\""

        raw = self.generate(prompt, temperature=0.0, max_tokens=256)
        label_names = _parse_label_names(raw)

        by_name = {label.name.strip().lower(): label.id for label in labels}
        label_ids = [by_name[name.strip().lower()] for name in label_names if name.strip().lower() in by_name]

        return ClassificationResult(label_ids=label_ids, raw_response=raw)


def _parse_label_names(raw: str) -> list[str]:
    """Best-effort JSON extraction — models occasionally wrap JSON in prose
    or a code fence despite instructions."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    labels = data.get("labels", [])
    return [str(name) for name in labels] if isinstance(labels, list) else []
