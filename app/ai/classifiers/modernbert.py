import json
import os
from collections import Counter
from typing import Any

import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

from app.ai.classifier import BaseClassifier, TrainingMetrics
from app.config import get_settings
from app.models.enums import ClassificationType

_LABELS_FILENAME = "labelforge_labels.json"


def _hf_cache_dir() -> str:
    """Keep every HuggingFace download under LabelForge's own data directory
    (sibling to the local GGUF models) rather than the user's global
    ~/.cache/huggingface — disk is tight, and this keeps everything the app
    downloads in one place the user can find and clean up."""
    base = os.path.dirname(get_settings().db_path) or "."
    path = os.path.join(base, "models", "hf_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class _TextDataset(torch.utils.data.Dataset):
    def __init__(self, encodings: dict, labels: torch.Tensor) -> None:
        self._encodings = encodings
        self._labels = labels

    def __len__(self) -> int:
        return len(self._labels)

    def __getitem__(self, idx: int) -> dict:
        item = {k: v[idx] for k, v in self._encodings.items()}
        item["labels"] = self._labels[idx]
        return item


class ModernBertClassifier(BaseClassifier):
    """Full fine-tuning of a real pretrained transformer (answerdotai/
    ModernBERT-base) — the one classifier LabelForge ships. No frozen-
    embedding shortcut, no bag-of-words baseline: this is the actual model,
    fine-tuned on this project's human-confirmed annotations.
    """

    MODEL_NAME = "answerdotai/ModernBERT-base"
    MAX_LENGTH = 256
    INFERENCE_BATCH_SIZE = 32
    NUM_EPOCHS = 4
    TRAIN_BATCH_SIZE = 8

    def __init__(self, classification_type: ClassificationType) -> None:
        self.classification_type = classification_type
        self._tokenizer = None
        self._model = None
        self._label_names: list[str] = []  # fixed order: id <-> index mapping

    def _encode_labels(self, labels: list[Any]) -> torch.Tensor:
        if self.classification_type == ClassificationType.MULTILABEL:
            self._label_names = sorted({name for row in labels for name in row})
            index = {name: i for i, name in enumerate(self._label_names)}
            y = torch.zeros((len(labels), len(self._label_names)), dtype=torch.float32)
            for i, row in enumerate(labels):
                for name in row:
                    y[i, index[name]] = 1.0
            return y

        self._label_names = sorted(set(labels))
        index = {name: i for i, name in enumerate(self._label_names)}
        return torch.tensor([index[label] for label in labels], dtype=torch.long)

    def train(self, texts: list[str], labels: list[Any]) -> TrainingMetrics:
        cache_dir = _hf_cache_dir()
        self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME, cache_dir=cache_dir)

        y = self._encode_labels(labels)
        problem_type = (
            "multi_label_classification"
            if self.classification_type == ClassificationType.MULTILABEL
            else "single_label_classification"
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.MODEL_NAME,
            num_labels=len(self._label_names),
            problem_type=problem_type,
            cache_dir=cache_dir,
        )
        self._model.to(_device())

        encodings = self._tokenizer(
            texts, truncation=True, padding=True, max_length=self.MAX_LENGTH, return_tensors="pt"
        )
        dataset = _TextDataset(dict(encodings), y)

        with torch.inference_mode(False):  # Trainer needs grad mode available
            training_args = TrainingArguments(
                output_dir=os.path.join(cache_dir, "_trainer_scratch"),
                num_train_epochs=self.NUM_EPOCHS,
                per_device_train_batch_size=self.TRAIN_BATCH_SIZE,
                logging_strategy="no",
                save_strategy="no",
                report_to=[],
                disable_tqdm=True,
            )
            trainer = Trainer(model=self._model, args=training_args, train_dataset=dataset)
            trainer.train()

        if self.classification_type == ClassificationType.MULTILABEL:
            distribution = Counter(name for row in labels for name in row)
        else:
            distribution = Counter(labels)

        return TrainingMetrics(n_examples=len(texts), label_distribution=dict(distribution))

    def _forward_scores(self, texts: list[str]) -> torch.Tensor:
        self._model.eval()
        device = _device()
        self._model.to(device)
        all_scores = []
        with torch.no_grad():
            for start in range(0, len(texts), self.INFERENCE_BATCH_SIZE):
                chunk = texts[start : start + self.INFERENCE_BATCH_SIZE]
                encodings = self._tokenizer(
                    chunk,
                    truncation=True,
                    padding=True,
                    max_length=self.MAX_LENGTH,
                    return_tensors="pt",
                ).to(device)
                logits = self._model(**encodings).logits
                if self.classification_type == ClassificationType.MULTILABEL:
                    scores = torch.sigmoid(logits)
                else:
                    scores = torch.softmax(logits, dim=-1)
                all_scores.append(scores.cpu())
        return torch.cat(all_scores, dim=0)

    def predict(self, texts: list[str]) -> list[Any]:
        scores = self._forward_scores(texts)
        if self.classification_type == ClassificationType.MULTILABEL:
            return [
                [self._label_names[i] for i, v in enumerate(row) if v > 0.5]
                for row in scores.tolist()
            ]
        return [self._label_names[idx] for idx in scores.argmax(dim=-1).tolist()]

    def predict_scores(self, texts: list[str]) -> list[dict[str, float]]:
        scores = self._forward_scores(texts)
        return [
            {name: float(score) for name, score in zip(self._label_names, row, strict=True)}
            for row in scores.tolist()
        ]

    def save(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        self._model.save_pretrained(path, safe_serialization=True)
        self._tokenizer.save_pretrained(path)
        with open(os.path.join(path, _LABELS_FILENAME), "w") as f:
            json.dump(
                {"classification_type": self.classification_type.value, "label_names": self._label_names},
                f,
            )

    @classmethod
    def load(cls, path: str) -> "ModernBertClassifier":
        with open(os.path.join(path, _LABELS_FILENAME)) as f:
            meta = json.load(f)
        instance = cls(ClassificationType(meta["classification_type"]))
        instance._label_names = meta["label_names"]
        instance._tokenizer = AutoTokenizer.from_pretrained(path)
        instance._model = AutoModelForSequenceClassification.from_pretrained(path)
        instance._model.to(_device())
        return instance
