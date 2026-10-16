from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=80_000)


class KnowledgeDocumentUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=80_000)


class KnowledgeDocumentResponse(BaseModel):
    id: int
    title: str
    source: str
    is_active: bool
    version: int
    content_hash: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeIngestResponse(BaseModel):
    document: KnowledgeDocumentResponse
    chunk_count: int


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=3, ge=1, le=10)


class RetrievedKnowledgeResponse(BaseModel):
    chunk_id: int
    title: str
    source: str
    content: str
    score: float
    keyword_score: float | None = None
    vector_score: float | None = None
    retrieval_method: str | None = None
    citation_id: str | None = None
    document_version: int | None = None
    chunk_index: int | None = None
