"""Import every model module so Base.metadata is complete for Alembic autogenerate."""

from app.models.annotation import (  # noqa: F401
    Annotation,
    AnnotationRevision,
    annotation_revision_labels,
)
from app.models.dataset import Dataset  # noqa: F401
from app.models.evaluation import EvaluationRun  # noqa: F401
from app.models.model import ModelVersion, TrainingRun  # noqa: F401
from app.models.project import Project, ProjectSettings  # noqa: F401
from app.models.record import Record  # noqa: F401
from app.models.suggestion import (  # noqa: F401
    LabelSuggestion,
    PromptVersion,
    label_suggestion_labels,
)
from app.models.taxonomy import Label, Taxonomy, TaxonomyVersion  # noqa: F401
