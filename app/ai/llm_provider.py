from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.enums import ClassificationType


@dataclass
class LabelSpec:
    id: int
    name: str
    description: str | None = None
    include_criteria: str | None = None
    exclude_criteria: str | None = None
    examples: list[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    label_ids: list[int]
    raw_response: str
    # No confidence/score field: an LLM's self-reported confidence is not a
    # calibrated probability, and v0.1 avoids fabricating false precision by
    # not asking for one. See app/models/suggestion.py — LabelSuggestion still
    # has a scores_json column for a future calibrated classifier to use.


class LLMProvider(ABC):
    """Not tightly coupled to any one vendor — Claude, OpenAI, a local model,
    etc. all implement this same interface."""

    @abstractmethod
    def generate(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str: ...

    @abstractmethod
    def classify(
        self,
        text: str,
        labels: list[LabelSpec],
        *,
        classification_type: ClassificationType,
        prompt_template: str | None = None,
    ) -> ClassificationResult: ...
