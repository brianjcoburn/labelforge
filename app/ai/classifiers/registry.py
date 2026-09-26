from app.ai.classifier import BaseClassifier
from app.ai.classifiers.modernbert import ModernBertClassifier
from app.core.exceptions import ValidationError
from app.models.enums import ClassificationType

# One entry today — kept as a registry (not a hardcoded reference to
# ModernBertClassifier everywhere) so a future model is a one-class,
# one-entry addition, not a redesign. Deliberately does not include the
# old TF-IDF+logistic-regression baseline: it was removed, not deprioritized.
CLASSIFIER_REGISTRY: dict[str, type[BaseClassifier]] = {
    "transformer": ModernBertClassifier,
}


def get_classifier_class(classifier_type: str) -> type[BaseClassifier]:
    cls = CLASSIFIER_REGISTRY.get(classifier_type)
    if cls is None:
        raise ValidationError(f"Unknown classifier_type '{classifier_type}'")
    return cls


def build_classifier(classifier_type: str, classification_type: ClassificationType) -> BaseClassifier:
    return get_classifier_class(classifier_type)(classification_type)


def load_classifier(classifier_type: str, artifact_path: str) -> BaseClassifier:
    return get_classifier_class(classifier_type).load(artifact_path)
