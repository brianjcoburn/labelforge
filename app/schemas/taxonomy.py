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


class LabelUpdate(BaseModel):
    """In-place edit of an existing label — name/definition/include/exclude/
    examples only. Per the taxonomy-versioning rules these are "rename" and
    "wording clarification" changes: existing annotations remain valid, no
    new taxonomy version needed. Adding or removing labels is a different,
    bigger workflow (new version, historical-annotation review) not built
    yet — deliberately not exposed here."""

    name: str | None = None
    description: str | None = None
    include_criteria: str | None = None
    exclude_criteria: str | None = None
    examples: list[str] | None = None


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
