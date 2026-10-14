"""Routes d'audit : rapport consolidé et flux progressif (Server-Sent Events)."""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    AccessCheck,
    AccessCheckDep,
    AuditServiceDep,
    DailyLimitReachedError,
    enforce_anonymous_quota,
    enforce_rate_limit,
)
from app.core.errors import LocationNotFoundError, SourceError
from app.schemas.audit import AuditQuery, AuditReport
from app.services.audit_service import AuditService, DoneEvent, LocationEvent
from app.services.teaser import mask_meta, mask_report, mask_result

router = APIRouter(prefix="/api/v1", tags=["audit"])

_NOT_FOUND_DETAIL = "Aucune adresse ou commune française ne correspond à ces coordonnées."
_GEOCODING_DOWN_DETAIL = "Service de géocodage indisponible, réessayez dans un instant."
_DAILY_LIMIT_DETAIL = (
    "Vous avez atteint le plafond quotidien d'adresses de l'offre Pro. Les adresses déjà "
    "consultées restent accessibles ; les nouvelles le seront à nouveau demain."
)

AuditQueryDep = Annotated[AuditQuery, Query()]


@router.get("/sources")
async def list_sources(service: AuditServiceDep) -> dict[str, list[str]]:
    """Noms des sources d'un rapport, pour afficher les squelettes de chargement."""
    return {"sources": service.source_names}


@router.get(
    "/audit",
    dependencies=[Depends(enforce_rate_limit), Depends(enforce_anonymous_quota)],
    responses={404: {"description": "Hors couverture"}, 429: {"description": "Débit dépassé"}},
)
async def get_audit(
    query: AuditQueryDep, service: AuditServiceDep, access: AccessCheckDep
) -> AuditReport:
    """Rapport d'audit en une seule réponse JSON ; version « teaser » sans droit d'accès."""
    try:
        report = await service.get_report(query)
        if not await access.allows(report.location):
            return mask_report(report)
        return _mark_demo(report, access)
    except DailyLimitReachedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _DAILY_LIMIT_DETAIL) from exc
    except LocationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND_DETAIL) from exc
    except SourceError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _GEOCODING_DOWN_DETAIL) from exc


def _mark_demo(report: AuditReport, access: AccessCheck) -> AuditReport:
    if not access.is_demo(report.location):
        return report
    return report.model_copy(update={"meta": report.meta.model_copy(update={"access": "demo"})})


@router.get(
    "/audit/stream",
    dependencies=[Depends(enforce_rate_limit), Depends(enforce_anonymous_quota)],
)
async def stream_audit(
    query: AuditQueryDep, service: AuditServiceDep, access: AccessCheckDep
) -> StreamingResponse:
    """Rapport émis pas à pas : `location`, `access`, `source`…, puis `done` ou `error`."""
    return StreamingResponse(
        _sse_events(service, query, access),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _access_level(full_access: bool, demo: bool) -> str:
    """Même valeur que `meta.access` de l'évènement final."""
    if demo:
        return "demo"
    return "full" if full_access else "teaser"


async def _sse_events(
    service: AuditService, query: AuditQuery, access: AccessCheck
) -> AsyncIterator[str]:
    # Restreint tant que la localisation, premier évènement du flux, n'a pas ouvert le droit.
    full_access = False
    demo = False
    try:
        async for event in service.stream(query):
            if isinstance(event, LocationEvent):
                full_access = await access.allows(event.location)
                demo = access.is_demo(event.location)
                yield _sse("location", event.location.model_dump(mode="json"))
                # Annoncé dès maintenant, et non avec `done` : l'interface place l'aperçu et son
                # bouton de déblocage avant les cartes, la page ne bouge plus à la fin du flux.
                yield _sse("access", {"access": _access_level(full_access, demo)})
            elif isinstance(event, DoneEvent):
                meta = event.meta if full_access else mask_meta(event.meta)
                if demo:
                    meta = meta.model_copy(update={"access": "demo"})
                yield _sse("done", meta.model_dump(mode="json"))
            else:
                # Le masquage a lieu avant la sérialisation : la valeur ne quitte pas le serveur.
                result = event.result if full_access else mask_result(event.name, event.result)
                yield _sse("source", {"name": event.name, "result": result.model_dump(mode="json")})
    except DailyLimitReachedError:
        yield _sse("error", {"code": "daily_limit_reached", "detail": _DAILY_LIMIT_DETAIL})
    except LocationNotFoundError:
        yield _sse("error", {"code": "location_not_found", "detail": _NOT_FOUND_DETAIL})
    except SourceError:
        yield _sse("error", {"code": "geocoding_unavailable", "detail": _GEOCODING_DOWN_DETAIL})
