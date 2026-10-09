"""Suppression d'un compte par son titulaire.

Le compte vit dans le service d'authentification : sa suppression passe par son interface
d'administration, jointe sur le réseau interne avec la clé de service. Les droits, crédits,
abonnement, marque blanche et historique rattachés disparaissent avec lui (suppression en
cascade en base).
"""

from app.core.http import HttpClient


class AccountDeletionUnavailableError(Exception):
    """La clé de service n'est pas configurée : pas de suppression en libre-service."""


class AccountDeleter:
    def __init__(self, http: HttpClient, *, auth_url: str, service_key: str | None) -> None:
        self._http = http
        self._auth_url = auth_url.rstrip("/")
        self._service_key = service_key or None

    async def delete(self, user_id: str) -> None:
        if self._service_key is None:
            raise AccountDeletionUnavailableError
        await self._http.delete(
            "auth_admin",
            f"{self._auth_url}/admin/users/{user_id}",
            headers={
                "Authorization": f"Bearer {self._service_key}",
                "apikey": self._service_key,
            },
        )
