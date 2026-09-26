from collections import Counter
from typing import Any

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from app.ai.classifier import BaseClassifier, TrainingMetrics
from app.models.enums import ClassificationType


class TfidfLogisticClassifier(BaseClassifier):
    """The one baseline v0.1 ships: TF-IDF features + logistic regression.

    Deliberately not a model zoo — this is a fast, dependency-light,
    interpretable baseline appropriate as a starting point per the spec; a
    different algorithm is a job for a new BaseClassifier implementation
    later, not a config flag here.

    Binary/multiclass share one LogisticRegression (sklearn handles multiclass
    natively). Multilabel wraps the same building blocks in a
    MultiLabelBinarizer + OneVsRestClassifier instead of a different model
    family — sklearn's OneVsRestClassifier already degrades gracefully (a
    constant predictor, with a warning) for any label with no positive
    examples in the training split, so no special-casing is needed here for
    a taxonomy's most sparsely-annotated labels.
    """

    def __init__(self, classification_type: ClassificationType) -> None:
        self.classification_type = classification_type
        self._vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=1)
        self._mlb: MultiLabelBinarizer | None = None
        if classification_type == ClassificationType.MULTILABEL:
            self._model = OneVsRestClassifier(
                LogisticRegression(max_iter=1000, class_weight="balanced")
            )
        else:
            self._model = LogisticRegression(max_iter=1000, class_weight="balanced")

    def train(self, texts: list[str], labels: list[Any]) -> TrainingMetrics:
        X = self._vectorizer.fit_transform(texts)

        if self.classification_type == ClassificationType.MULTILABEL:
            self._mlb = MultiLabelBinarizer()
            Y = self._mlb.fit_transform(labels)
            self._model.fit(X, Y)
            distribution = Counter(name for label_list in labels for name in label_list)
        else:
            self._model.fit(X, labels)
            distribution = Counter(labels)

        return TrainingMetrics(n_examples=len(texts), label_distribution=dict(distribution))

    def predict(self, texts: list[str]) -> list[Any]:
        X = self._vectorizer.transform(texts)
        if self.classification_type == ClassificationType.MULTILABEL:
            Y = self._model.predict(X)
            return [list(row) for row in self._mlb.inverse_transform(Y)]
        return list(self._model.predict(X))

    def predict_scores(self, texts: list[str]) -> list[dict[str, float]]:
        X = self._vectorizer.transform(texts)
        proba = self._model.predict_proba(X)
        class_names = (
            list(self._mlb.classes_)
            if self.classification_type == ClassificationType.MULTILABEL
            else list(self._model.classes_)
        )
        return [
            {name: float(score) for name, score in zip(class_names, row, strict=True)}
            for row in proba
        ]

    def save(self, path: str) -> None:
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
    def load(cls, path: str) -> "TfidfLogisticClassifier":
        data = joblib.load(path)
        instance = cls(data["classification_type"])
        instance._vectorizer = data["vectorizer"]
        instance._model = data["model"]
        instance._mlb = data["mlb"]
        return instance
