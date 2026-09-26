from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    hamming_loss,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import MultiLabelBinarizer

from app.models.enums import ClassificationType


def compute_metrics(
    y_true: list,
    y_pred: list,
    classification_type: ClassificationType,
    label_names: list[str],
    y_scores: list[dict[str, float]] | None = None,
) -> dict:
    """Held-out-set metrics, shaped per classification type per the spec:
    binary/multiclass get precision/recall/F1/accuracy/confusion matrix (plus
    ROC-AUC for binary, where the classifier's own probabilities are
    available); multilabel gets micro/macro F1, per-label precision/recall/F1,
    and Hamming loss.
    """
    if classification_type == ClassificationType.MULTILABEL:
        return _multilabel_metrics(y_true, y_pred, label_names)
    return _single_label_metrics(y_true, y_pred, classification_type, label_names, y_scores)


def _single_label_metrics(
    y_true: list[str],
    y_pred: list[str],
    classification_type: ClassificationType,
    label_names: list[str],
    y_scores: list[dict[str, float]] | None,
) -> dict:
    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=label_names, average=None, zero_division=0
    )
    macro_f1 = f1_score(y_true, y_pred, labels=label_names, average="macro", zero_division=0)
    per_class = {
        name: {
            "precision": float(p),
            "recall": float(r),
            "f1": float(f),
            "support": int(s),
        }
        for name, p, r, f, s in zip(label_names, precision, recall, f1, support, strict=True)
    }
    result: dict = {
        "accuracy": float(accuracy),
        "macro_f1": float(macro_f1),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": label_names,
            "matrix": confusion_matrix(y_true, y_pred, labels=label_names).tolist(),
        },
    }

    if classification_type == ClassificationType.BINARY and len(label_names) == 2:
        positive = label_names[1]
        result["precision"] = per_class[positive]["precision"]
        result["recall"] = per_class[positive]["recall"]
        result["f1"] = per_class[positive]["f1"]
        if y_scores is not None:
            try:
                positive_scores = [row.get(positive, 0.0) for row in y_scores]
                binary_true = [1 if label == positive else 0 for label in y_true]
                result["roc_auc"] = float(roc_auc_score(binary_true, positive_scores))
            except ValueError:
                pass  # e.g. held-out set has only one class present — not computable

    return result


def _multilabel_metrics(
    y_true: list[list[str]], y_pred: list[list[str]], label_names: list[str]
) -> dict:
    mlb = MultiLabelBinarizer(classes=label_names)
    Y_true = mlb.fit_transform(y_true)
    Y_pred = mlb.transform(y_pred)

    precision, recall, f1, support = precision_recall_fscore_support(
        Y_true, Y_pred, average=None, zero_division=0
    )
    per_label = {
        name: {
            "precision": float(p),
            "recall": float(r),
            "f1": float(f),
            "support": int(s),
        }
        for name, p, r, f, s in zip(label_names, precision, recall, f1, support, strict=True)
    }

    return {
        "micro_f1": float(f1_score(Y_true, Y_pred, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(Y_true, Y_pred, average="macro", zero_division=0)),
        "per_label": per_label,
        "hamming_loss": float(hamming_loss(Y_true, Y_pred)),
    }
