"""Exceptions métier partagées par les couches services et repositories."""

from typing import Literal

ErrorKind = Literal[
    "timeout", "http_error", "not_found", "circuit_open", "invalid_response", "quota"
]

_PUBLIC_MESSAGES: dict[ErrorKind, str] = {
    "timeout": "La source n'a pas répondu dans le délai imparti.",
    "http_error": "La source a renvoyé une erreur.",
    "not_found": "Ressource introuvable auprès de la source.",
    "circuit_open": "Source temporairement désactivée après des échecs répétés.",
    "invalid_response": "Réponse inattendue de la source.",
    "quota": "Source très sollicitée, réessayez dans une minute.",
}


class SourceError(Exception):
    """Échec d'une source de données externe ou locale."""

    def __init__(self, kind: ErrorKind, detail: str = "", *, transient: bool = True) -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind: ErrorKind = kind
        self.detail = detail
        # Un échec transitoire (timeout, 5xx, réseau) compte pour le circuit-breaker.
        self.transient = transient

    @property
    def public_message(self) -> str:
        """Message exposable au client, sans détail technique."""
        return _PUBLIC_MESSAGES[self.kind]


class NoDataError(Exception):
    """La source a répondu mais ne possède aucune donnée pour cette localisation."""


class LocationNotFoundError(Exception):
    """Les coordonnées ne correspondent à aucune adresse ou commune connue."""


class RepositoryError(Exception):
    """La base de données est injoignable ou a rejeté la requête."""
