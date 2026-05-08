from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DispatchResponse(BaseModel):
    task_id: str
    status: str


class JobStatusResponse(BaseModel):
    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
