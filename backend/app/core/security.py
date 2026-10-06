"""Vérification des jetons d'accès émis par Supabase Auth (GoTrue)."""

from dataclasses import dataclass

import jwt

_ALGORITHMS = ["HS256"]
_AUDIENCE = "authenticated"


class InvalidTokenError(Exception):
    """Jeton absent de forme, falsifié, expiré ou qui n'identifie pas un utilisateur."""


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


def decode_access_token(token: str, secret: str) -> AuthenticatedUser:
    """Utilisateur porté par un jeton de session valide.

    La clé « anon » de Supabase est aussi un JWT signé avec le même secret : elle est
    refusée ici, car elle n'a ni sujet (`sub`) ni audience « authenticated ».
    """
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=_ALGORITHMS,
            audience=_AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(type(exc).__name__) from exc
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or claims.get("role") != _AUDIENCE:
        raise InvalidTokenError("not a user session")
    email = claims.get("email")
    return AuthenticatedUser(id=subject, email=email if isinstance(email, str) else None)
