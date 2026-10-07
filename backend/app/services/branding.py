"""Marque blanche : contrôle du logo déposé par un abonné.

Le logo est fourni par le navigateur : seul un PNG ou un JPEG de taille raisonnable est
accepté, d'après son contenu réel et non le type qu'il annonce. Le SVG est exclu, car il peut
embarquer du script.
"""

import base64
import binascii
import re

MAX_LOGO_BYTES = 200 * 1024
_DATA_URL = re.compile(r"^data:(image/png|image/jpeg);base64,([A-Za-z0-9+/=\s]+)$")
_SIGNATURES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}


class InvalidLogoError(ValueError):
    """Le fichier n'est pas un PNG ou un JPEG acceptable."""


def decode_logo(data_url: str) -> tuple[bytes, str]:
    """(octets, type MIME) d'un logo reçu sous forme d'URL « data: »."""
    match = _DATA_URL.match(data_url)
    if match is None:
        raise InvalidLogoError("Le logo doit être une image PNG ou JPEG.")
    declared = match.group(1)
    try:
        content = base64.b64decode(match.group(2), validate=False)
    except (binascii.Error, ValueError) as exc:
        raise InvalidLogoError("Le logo est illisible.") from exc
    if not content or len(content) > MAX_LOGO_BYTES:
        raise InvalidLogoError(f"Le logo doit peser moins de {MAX_LOGO_BYTES // 1024} Ko.")
    # Le type réel se lit dans les premiers octets, pas dans l'étiquette fournie.
    actual = next(
        (kind for kind, signature in _SIGNATURES.items() if content.startswith(signature)), None
    )
    if actual != declared:
        raise InvalidLogoError("Le logo doit être une image PNG ou JPEG.")
    return content, declared


def encode_logo(content: bytes, kind: str) -> str:
    return f"data:{kind};base64,{base64.b64encode(content).decode('ascii')}"
