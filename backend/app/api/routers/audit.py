"""Routes d'audit : rapport consolidé et flux progressif (Server-Sent Events)."""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import AuditServiceDep, enforce_rate_limit
from app.core.errors import LocationNotFoundError, SourceError
from app.schemas.audit import AuditQuery, AuditReport
from app.services.audit_service import AuditService, DoneEvent, LocationEvent

router = APIRouter(prefix="/api/v1", tags=["audit"])

_NOT_FOUND_DETAIL = "Aucune adresse ou commune française ne correspond à ces coordonnées."
_GEOCODING_DOWN_DETAIL = "Service de géocodage indisponible, réessayez dans un instant."

AuditQueryDep = Annotated[AuditQuery, Query()]


@router.get("/sources")
async def list_sources(service: AuditServiceDep) -> dict[str, list[str]]:
    """Noms des sources d'un rapport, pour afficher les squelettes de chargement."""
    return {"sources": service.source_names}


@router.get(
    "/audit",
    dependencies=[Depends(enforce_rate_limit)],
    responses={404: {"description": "Hors couverture"}, 429: {"description": "Débit dépassé"}},
)
async def get_audit(query: AuditQueryDep, service: AuditServiceDep) -> AuditReport:
    """Rapport d'audit complet en une seule réponse JSON."""
    try:
        return await service.get_report(query)
    except LocationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND_DETAIL) from exc
    except SourceError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _GEOCODING_DOWN_DETAIL) from exc


@router.get("/audit/stream", dependencies=[Depends(enforce_rate_limit)])
async def stream_audit(query: AuditQueryDep, service: AuditServiceDep) -> StreamingResponse:
    """Même rapport, émis source par source : `location`, `source`…, puis `done` ou `error`."""
    return StreamingResponse(
        _sse_events(service, query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _sse_events(service: AuditService, query: AuditQuery) -> AsyncIterator[str]:
    try:
        async for event in service.stream(query):
            if isinstance(event, LocationEvent):
                yield _sse("location", event.location.model_dump(mode="json"))
            elif isinstance(event, DoneEvent):
                yield _sse("done", event.meta.model_dump(mode="json"))
            else:
                yield _sse(
                    "source", {"name": event.name, "result": event.result.model_dump(mode="json")}
                )
    except LocationNotFoundError:
        yield _sse("error", {"code": "location_not_found", "detail": _NOT_FOUND_DETAIL})
    except SourceError:
        yield _sse("error", {"code": "geocoding_unavailable", "detail": _GEOCODING_DOWN_DETAIL})
