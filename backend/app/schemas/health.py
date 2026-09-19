from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str
    postgis: str | None = None
    migration: str | None = None
    detail: str | None = None
