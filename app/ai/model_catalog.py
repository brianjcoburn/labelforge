from dataclasses import dataclass


@dataclass(frozen=True)
class LocalModelSpec:
    id: str
    display_name: str
    brand: str
    repo_id: str
    filename: str
    size_gb: float
    notes: str = ""
    # Set only for a known-broken combination with the current
    # llama-cpp-python version — surfaced distinctly from `notes` in the UI
    # (a warning, not just informational text) since it means "this will
    # currently fail," not "here's a tradeoff to weigh."
    warning: str | None = None


# Verified, public, ungated GGUF repos — no HuggingFace account or token
# needed to download any of these. Deliberately excludes DeepSeek/Alibaba per
# project preference; Anthropic has no open-weight models to offer, so Google
# fills that third "reputable major lab" slot instead.
LOCAL_MODEL_CATALOG: list[LocalModelSpec] = [
    LocalModelSpec(
        id="mistral-7b-instruct",
        display_name="Mistral 7B Instruct v0.3",
        brand="Mistral AI",
        repo_id="bartowski/Mistral-7B-Instruct-v0.3-GGUF",
        filename="Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        size_gb=4.37,
        notes="Good default — smallest download, comfortably fits 18GB+ unified memory.",
    ),
    LocalModelSpec(
        id="gemma-2-9b-instruct",
        display_name="Gemma 2 9B Instruct",
        brand="Google",
        repo_id="bartowski/gemma-2-9b-it-GGUF",
        filename="gemma-2-9b-it-Q4_K_M.gguf",
        size_gb=5.76,
        notes="Larger, generally stronger than the 7B Mistral model.",
    ),
    LocalModelSpec(
        id="gpt-oss-20b",
        display_name="gpt-oss 20B",
        brand="OpenAI",
        repo_id="ggml-org/gpt-oss-20b-GGUF",
        filename="gpt-oss-20b-MXFP4.gguf",
        size_gb=12.1,
        notes="Large download and memory footprint — check free disk/RAM before downloading.",
        warning=(
            "Currently fails on every classification (llama_decode error) — "
            "llama-cpp-python 0.3.35 (the latest release as of writing) has no "
            "chat-format support for gpt-oss's Harmony format, so it produces "
            "malformed input for this model's architecture. Not something "
            "LabelForge can fix; needs upstream support. Use Mistral or Gemma instead."
        ),
    ),
]

_BY_ID = {spec.id: spec for spec in LOCAL_MODEL_CATALOG}


def get_model_spec(catalog_id: str) -> LocalModelSpec | None:
    return _BY_ID.get(catalog_id)
