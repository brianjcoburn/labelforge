from pydantic import BaseModel


class DatasetUploadOut(BaseModel):
    dataset_id: int
    columns: list[str]
    preview_rows: list[dict[str, str]]


class DatasetImportRequest(BaseModel):
    name: str
    id_column: str | None = None
    text_column: str
    label_column: str | None = None
    metadata_columns: list[str] = []


class DatasetImportOut(BaseModel):
    dataset_id: int
    record_count: int
    matched_label_count: int
    unmatched_label_count: int


class DatasetOut(BaseModel):
    id: int
    name: str
    source_filename: str
    record_count: int
