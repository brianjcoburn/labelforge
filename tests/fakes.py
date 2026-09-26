"""Test-only fakes — never imported by app/ code."""

from app.ai.llm_provider import ClassificationResult, LabelSpec, LLMProvider
from app.models.enums import ClassificationType


class FakeLLMProvider(LLMProvider):
    """Deterministic stand-in for tests: always predicts the first label."""

    def __init__(self, label_names_to_return: list[str] | None = None) -> None:
        self.calls: list[str] = []
        self._label_names_to_return = label_names_to_return

    def generate(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
        self.calls.append(prompt)
        return "generated text"

    def classify(
        self,
        text: str,
        labels: list[LabelSpec],
        *,
        classification_type: ClassificationType,
        prompt_template: str | None = None,
    ) -> ClassificationResult:
        self.calls.append(text)
        if not labels:
            return ClassificationResult(label_ids=[], raw_response="{}")
        names = self._label_names_to_return
        if names is None:
            names = [labels[0].name]
        by_name = {label.name: label.id for label in labels}
        ids = [by_name[n] for n in names if n in by_name]
        return ClassificationResult(label_ids=ids, raw_response=f'{{"labels": {names!r}}}')
