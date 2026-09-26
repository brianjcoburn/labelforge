from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    annotations,
    datasets,
    export,
    models,
    projects,
    prompts,
    taxonomies,
    training,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError

app = FastAPI(title="LabelForge", version="0.1.0")

# Dev-only CORS: the Vite dev server runs on a different port than uvicorn.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(projects.router)
app.include_router(taxonomies.router)
app.include_router(datasets.router)
app.include_router(annotations.router)
app.include_router(export.router)
app.include_router(prompts.router)
app.include_router(models.router)
app.include_router(training.router)
