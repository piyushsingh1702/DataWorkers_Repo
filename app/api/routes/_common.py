"""Shared request/response models for routes that operate on a named database."""

from typing import Any

from pydantic import BaseModel, Field


class DBNameRequest(BaseModel):
    """Request body containing the target database name.

    The ``db_name`` field is rendered as a dropdown in the Swagger UI by
    ``app.main._customize_openapi`` which dynamically injects the list of
    registered databases from the dq_admin registry.
    """

    db_name: str | None = Field(
        default=None,
        description="Registered database name (see GET /api/v1/database/list).",
    )


class PipelineRunRequest(DBNameRequest):
    description: str | None = Field(
        default=None,
        description="Optional description stored in the dq_admin registry.",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata stored as JSON in the dq_admin registry.",
    )
