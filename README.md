# LabelForge

AI-assisted data annotation platform — human labeling, AI-assisted labeling, smart
sampling, and integrated model training, in one tool.

**v0.1 scope**: text classification only (binary, multi-class, multi-label). The
architecture anticipates image/audio and richer AI/model workflows without
implementing them yet — see [Roadmap](#roadmap).

## What's here (Milestone 1)

A working manual annotation app: create a project, define a taxonomy, import a
CSV, label records through a fast keyboard-friendly-ish workspace, track
progress, and export the labeled dataset. No AI/model training yet — that's
milestone 2+.

## Stack

- Backend: FastAPI + SQLAlchemy 2.0 + Alembic, SQLite
- Frontend: React + Vite + TypeScript, proxying `/api` to the backend
- Dependency management: [`uv`](https://docs.astral.sh/uv/)
- Tests: pytest

## Setup

Requires Python 3.13+ and Node.

```bash
# Backend
uv sync --extra dev
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

- **Milestone 2**: LLM provider abstraction, prompt generation/versioning, AI
  predictions, ai-first/human-first/on-demand modes end-to-end
- **Milestone 3**: baseline classifier, training, evaluation
- **Milestone 4**: batch/adaptive training
- **Milestone 5**: smart/uncertainty/balanced sampling
- **Milestone 6**: taxonomy revision workflow (add/merge/split/remove class,
  targeted re-validation)
- **Milestone 7**: synthetic dataset generation
- **Milestone 8**: dashboard/comparison polish, usability, docs
