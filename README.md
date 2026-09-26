# LabelForge

AI-assisted data annotation platform — human labeling, AI-assisted labeling, smart
sampling, and integrated model training, in one tool.

**v0.1 scope**: text classification only (binary, multi-class, multi-label). The
architecture anticipates image/audio and richer AI/model workflows without
implementing them yet — see [Roadmap](#roadmap).

## What's here (Milestones 1-3)

A working manual + AI-assisted annotation app: create a project, define a
taxonomy, import a CSV, label records through a fast keyboard-friendly-ish
workspace, track progress, and export the labeled dataset (milestone 1) —
plus a choice of LLM providers per project — a free local open-source model
(Mistral/Gemma/gpt-oss, no account needed) or the Anthropic API — prompt
generation/editing/versioning, AI predictions surfaced through
`ai_first`/`human_first`/`on_demand` modes, and human/AI agreement tracking
(milestone 2) — plus a baseline classifier (TF-IDF + logistic regression)
trained on your human-confirmed annotations via "Train Now," evaluated on a
held-out split, fully versioned, with explicit activation (**Models /
Training** on the project dashboard) (milestone 3). Training the classifier
into the live annotation-suggestion loop and automatic (batch/adaptive)
retraining are milestone 4+ — for now, training is on-demand and its
predictions live only on the Models page, not yet in the workspace.

AI features are entirely optional: without `ANTHROPIC_API_KEY` set, the app
runs exactly as milestone 1 did — every AI code path degrades gracefully
rather than erroring.

## Stack

- Backend: FastAPI + SQLAlchemy 2.0 + Alembic, SQLite
- Frontend: React + Vite + TypeScript, proxying `/api` to the backend
- Dependency management: [`uv`](https://docs.astral.sh/uv/)
- Tests: pytest

## Setup

Requires Python 3.13+, Node, and `cmake` (needed to compile `llama-cpp-python`
for local model support — `brew install cmake` on macOS).

```bash
# Backend — CMAKE_ARGS enables Metal acceleration for local models on Apple Silicon
CMAKE_ARGS="-DGGML_METAL=on" uv sync --extra dev
cp .env.example .env   # adjust if needed; never commit the real .env
uv run alembic upgrade head

# Frontend
cd frontend
npm install
```

## Running

Two processes, in separate terminals:

```bash
# Backend (from repo root)
uv run uvicorn app.main:app --reload --port 8000

# Frontend (from frontend/)
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` requests to
the backend on port 8000.

### Enabling AI-assisted labeling

Each project picks its own AI model in **Manage Prompt → AI model** — no
global config needed for the local option:

- **Local, free, open-source** (no account, no API key): pick a model from
  the catalog and click Download. Runs entirely on your machine via
  [`llama.cpp`](https://github.com/ggml-org/llama.cpp) (Metal-accelerated on
  Apple Silicon). Catalog:
  | Model | Brand | Size |
  |---|---|---|
  | Mistral 7B Instruct v0.3 | Mistral AI | 4.4 GB |
  | Gemma 2 9B Instruct | Google | 5.8 GB |
  | gpt-oss 20B | OpenAI | 12.1 GB |

  All three are public, ungated HuggingFace repos — downloaded anonymously,
  no HuggingFace account required. Check free disk space before downloading;
  models are cached under `data/models/` (gitignored) so each is only
  downloaded once. First inference after selecting a model takes a few
  seconds to load it into memory; after that it's cached for the life of the
  backend process.
- **Anthropic API**: set `ANTHROPIC_API_KEY` in `.env` (get one at
  https://console.anthropic.com/settings/keys) and restart the backend, then
  pick "Anthropic API" for the project. `LABELFORGE_ANTHROPIC_MODEL` picks
  the model (defaults to a fast, inexpensive one).

A project with no model selected/downloaded yet simply has no AI
features — never an error, just milestone-1 behavior.

## Testing

```bash
uv run pytest
```

## Database migrations

Schema changes go through Alembic from day one (the schema grows a lot as
taxonomy/model/training versioning workflows arrive in later milestones):

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

## Core concepts

- **Ground truth vs. suggestions**: human-confirmed annotations
  (`Annotation`/`AnnotationRevision`) are the only authoritative labels, and
  editing one never destroys history — it appends a new revision. Everything
  else (an imported label, an LLM prediction, a trained classifier's
  prediction) is a non-authoritative `LabelSuggestion`, distinguished by
  `source` (`imported` / `llm` / `classifier`).
- **Provenance**: every annotation revision records who labeled it, when,
  under which taxonomy version, in what annotation mode, and whether a
  suggestion was shown before submission.
- **Versioning**: taxonomies, prompts, and models are all versioned; nothing
  meaningful is silently overwritten.

## Roadmap

- ~~**Milestone 2**: LLM provider abstraction, prompt generation/versioning, AI
  predictions, ai-first/human-first/on-demand modes end-to-end~~ done
- ~~**Milestone 3**: baseline classifier, training, evaluation~~ done
- **Milestone 4**: batch/adaptive training
- **Milestone 5**: smart/uncertainty/balanced sampling
- **Milestone 6**: taxonomy revision workflow (add/merge/split/remove class,
  targeted re-validation)
- **Milestone 7**: synthetic dataset generation
- **Milestone 8**: dashboard/comparison polish, usability, docs
