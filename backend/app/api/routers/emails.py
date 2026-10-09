"""Gabarits d'e-mail lus par le service d'authentification (réseau interne uniquement)."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.services.emails import auth_template

router = APIRouter(include_in_schema=False)


@router.get("/emails/{kind}.html", response_class=HTMLResponse)
async def email_template(kind: str) -> HTMLResponse:
    """Gabarit d'un message d'authentification, à la charte du site.

    Cette route n'est pas publiée par le serveur frontal : seul le service d'authentification,
    sur le réseau interne, la consulte.
    """
    html = auth_template(kind, site_url=get_settings().site_url)
    if html is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return HTMLResponse(html)
