from llama_cpp import Llama

from app.ai.llm_provider import ClassificationResult, LabelSpec, LLMProvider
from app.ai.prompt_builder import TEXT_PLACEHOLDER, build_default_prompt
from app.ai.response_parsing import label_ids_from_names, parse_label_names
from app.models.enums import ClassificationType


class LocalLlamaProvider(LLMProvider):
    """Runs a local GGUF model via llama.cpp, offloaded to Metal on Apple
    Silicon. Loading the model into memory happens once in __init__ (several
    seconds) — callers should cache instances per model_path rather than
    constructing a new one per request. See app/ai/factory.py.
    """

    def __init__(self, model_path: str, n_ctx: int = 4096) -> None:
        self._llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            # llama-cpp-python defaults n_batch/n_ubatch to 512 regardless of
            # n_ctx. A real taxonomy prompt (several labels with definitions
            # and include/exclude criteria) easily exceeds that and causes a
            # native decode failure ("llama_decode returned -3"), so these
            # must scale with n_ctx, not be left at the library default.
            n_batch=n_ctx,
            n_ubatch=n_ctx,
            n_gpu_layers=-1,  # offload every layer it can to the GPU (Metal on macOS)
            verbose=False,
        )

    def generate(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
        # Defensive: clears the KV cache before each call. A prior failed
        # decode on this same instance can otherwise leave stale/inconsistent
        # cache state that corrupts (or hangs) the next call.
        self._llm.reset()
        result = self._llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return result["choices"][0]["message"]["content"] or ""

    def classify(
        self,
        text: str,
        labels: list[LabelSpec],
        *,
        classification_type: ClassificationType,
        prompt_template: str | None = None,
    ) -> ClassificationResult:
        template = prompt_template or build_default_prompt(labels, classification_type)
        if TEXT_PLACEHOLDER in template:
            prompt = template.replace(TEXT_PLACEHOLDER, text)
        else:
            prompt = f"{template}\n\nText to classify:\n\"\"\"\n{text}\n\"\"\""

        raw = self.generate(prompt, temperature=0.0, max_tokens=256)
        label_ids = label_ids_from_names(parse_label_names(raw), labels)
        return ClassificationResult(label_ids=label_ids, raw_response=raw)
