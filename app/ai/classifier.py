from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.models.enums import ClassificationType


@dataclass
class TrainingMetrics:
    """What fitting produced — not evaluation quality (that's a separate,
    held-out-data concern; see app/services/evaluation_service.py)."""

    n_examples: int
    label_distribution: dict[str, int]


class BaseClassifier(ABC):
    """Not tied to one algorithm — a future classifier implements this same
    interface and registers in app/ai/classifiers/registry.py. v0.1 ships one
    concrete implementation, ModernBertClassifier (real transformer
    fine-tuning) — see that module."""

    classification_type: ClassificationType

    @abstractmethod
    def train(self, texts: list[str], labels: list[Any]) -> TrainingMetrics:
        """`labels[i]` is a single label name (str) for binary/multiclass, or
        a list of label names for multilabel."""
        ...

    @abstractmethod
    def predict(self, texts: list[str]) -> list[Any]:
        """Same shape as `labels` in train(): str per text, or list[str] per
        text for multilabel."""
        ...

    @abstractmethod
    def predict_scores(self, texts: list[str]) -> list[dict[str, float]]:
        """Per-text {label_name: score}. Unlike an LLM's self-reported
        confidence, these ARE calibrated-ish probabilities from the
        underlying model — still worth treating as relative signal rather
        than ground truth, but a meaningfully different kind of number than
        an LLM's, which is why LabelSuggestion keeps prediction sources
        distinct rather than conflating them."""
        ...

    @abstractmethod
    def save(self, path: str) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> "BaseClassifier": ...
