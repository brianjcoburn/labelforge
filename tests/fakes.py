"""Test-only fakes — never imported by app/ code."""

from collections import Counter
from typing import Any

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from app.ai.classifier import BaseClassifier, TrainingMetrics
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


class FakeClassifier(BaseClassifier):
    """Test-only stand-in for the real (slow, real-fine-tuning) classifier —
    a tiny sklearn model, fast enough to run in every test, that still
    genuinely learns from the training text so tests of comparison/
    regression/evaluation logic exercise real, meaningfully different
    quality between models rather than a hardcoded constant. Never
    registered in the production CLASSIFIER_REGISTRY.
    """

    def __init__(self, classification_type: ClassificationType) -> None:
        self.classification_type = classification_type
        self._vectorizer = CountVectorizer()
        self._mlb: MultiLabelBinarizer | None = None
        self._model = (
            OneVsRestClassifier(LogisticRegression(max_iter=200))
            if classification_type == ClassificationType.MULTILABEL
            else LogisticRegression(max_iter=200)
        )

    def train(self, texts: list[str], labels: list[Any]) -> TrainingMetrics:
        X = self._vectorizer.fit_transform(texts)
        if self.classification_type == ClassificationType.MULTILABEL:
            self._mlb = MultiLabelBinarizer()
            Y = self._mlb.fit_transform(labels)
            self._model.fit(X, Y)
            distribution = Counter(name for row in labels for name in row)
        else:
            self._model.fit(X, labels)
            distribution = Counter(labels)
        return TrainingMetrics(n_examples=len(texts), label_distribution=dict(distribution))

    def predict(self, texts: list[str]) -> list[Any]:
        X = self._vectorizer.transform(texts)
        if self.classification_type == ClassificationType.MULTILABEL:
            return [list(row) for row in self._mlb.inverse_transform(self._model.predict(X))]
        return list(self._model.predict(X))

    def predict_scores(self, texts: list[str]) -> list[dict[str, float]]:
        X = self._vectorizer.transform(texts)
        proba = self._model.predict_proba(X)
        names = list(self._mlb.classes_) if self._mlb else list(self._model.classes_)
        return [
            {name: float(score) for name, score in zip(names, row, strict=True)} for row in proba
        ]

    def save(self, path: str) -> None:
        import os

        import joblib

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        joblib.dump(
            {
                "classification_type": self.classification_type,
                "vectorizer": self._vectorizer,
                "model": self._model,
                "mlb": self._mlb,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "FakeClassifier":
        import joblib

        data = joblib.load(path)
        instance = cls(data["classification_type"])
        instance._vectorizer = data["vectorizer"]
        instance._model = data["model"]
        instance._mlb = data["mlb"]
        return instance
