"""Fiche publique d'une commune (chiffres communaux, sans donnée à l'adresse)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status

from app.api.deps import enforce_rate_limit
from app.core.errors import RepositoryError, SourceError
from app.schemas.commune import CommuneProfile
from app.services.communes import CommuneService

router = APIRouter(prefix="/api/v1", tags=["communes"])

_CODE_PATTERN = r"^[0-9][0-9AB][0-9]{3}$"
# Les référentiels ne changent qu'à l'ingestion : la fiche peut être gardée une journée.
_CACHE_CONTROL = "public, max-age=86400"


def get_commune_service(request: Request) -> CommuneService:
    service: CommuneService = request.app.state.commune_service
    return service


@router.get("/communes/{code}", dependencies=[Depends(enforce_rate_limit)])
async def get_commune(
    code: Annotated[str, Path(pattern=_CODE_PATTERN)],
    service: Annotated[CommuneService, Depends(get_commune_service)],
    response: Response,
) -> CommuneProfile:
    """Chiffres clés d'une commune, désignée par son code INSEE."""
    try:
        identity = await service.identity(code)
        if identity is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Commune inconnue.")
        profile = await service.profile(identity)
    except (SourceError, RepositoryError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Fiche momentanément indisponible."
        ) from exc
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return profile
