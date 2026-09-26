from pydantic import BaseModel, ConfigDict


class LabelCreate(BaseModel):
    name: str
    description: str | None = None
    include_criteria: str | None = None
    exclude_criteria: str | None = None
    examples: list[str] = []


class TaxonomyCreate(BaseModel):
    name: str
    labels: list[LabelCreate]


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    include_criteria: str | None
    exclude_criteria: str | None
    examples: list[str]
    display_order: int


class TaxonomyOut(BaseModel):
    id: int
    name: str
    active_version_number: int
    labels: list[LabelOut]
