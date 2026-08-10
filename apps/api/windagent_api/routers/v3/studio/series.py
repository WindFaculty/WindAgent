"""Series resource router (/api/v3/studio/series)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, status

from windagent_api.routers.v3.studio.dependencies import (
    get_studio_application_service,
    require_idempotency_key,
)
from windagent_api.routers.v3.studio.schemas import CreateSeriesRequest, SeriesListResponse
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_core.contracts.studio.errors import StudioNotFoundError
from windagent_core.contracts.studio.ids import SeriesProjectId

router = APIRouter(prefix="/series", tags=["studio-series"])


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_series(
    body: CreateSeriesRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    result = await service.create_series(
        title=body.title,
        description=body.description,
        metadata=body.metadata,
        idempotency_key=idempotency_key,
    )
    return {
        "series_id": str(result.series_id),
        "title": result.title,
        "series_url": f"/api/v3/studio/series/{result.series_id}",
    }


@router.get("", response_model=SeriesListResponse)
async def list_series(
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> SeriesListResponse:
    data = await service.list_series(cursor=cursor, limit=limit)
    return SeriesListResponse(**data)


@router.get("/{series_id}", response_model=dict)
async def get_series(
    series_id: str = Path(...),
    service: StudioApplicationService = Depends(get_studio_application_service),
) -> dict:
    parsed = service.parse_id(SeriesProjectId, series_id, "series_id")
    view = await service.get_series(series_id=parsed)
    if view is None:
        raise StudioNotFoundError(
            f"Series {series_id!r} does not exist.",
            details={"series_id": series_id},
        )
    return view
