from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class SamplingContext:
    """Signals a strategy may use, degrading gracefully as they become available.

    v0.1 only ever has an empty/default context (no classifier, no LLM yet) —
    populated fully once milestones 2/3 exist.
    """

    taxonomy_version_id: int | None = None
    has_active_model: bool = False
    has_llm_predictions: bool = False


class SamplingStrategy(ABC):
    @abstractmethod
    def select_next(
        self,
        *,
        project_id: int,
        candidate_record_ids: Sequence[int],
        context: SamplingContext,
    ) -> int | None: ...


class SequentialSamplingStrategy(SamplingStrategy):
    """v0.1 concrete strategy: walk unlabeled records in id order.

    Stands in for Random/Balanced/Uncertainty/Smart, all of which need
    signals (a trained classifier, predictions) that don't exist until
    later milestones.
    """

    def select_next(
        self,
        *,
        project_id: int,
        candidate_record_ids: Sequence[int],
        context: SamplingContext,
    ) -> int | None:
        if not candidate_record_ids:
            return None
        return min(candidate_record_ids)
