"""Alerte d'exploitation par e-mail.

    journal | docker compose exec -T backend python -m app.notify "Sauvegarde en échec"

Le corps du message est lu sur l'entrée standard. Sans destinataire (ALERT_EMAIL) ou sans
serveur d'envoi, la commande ne fait rien et sort en erreur pour que cela se voie.
"""

import asyncio
import sys
from html import escape

from app.container import build_mailer
from app.core.config import get_settings
from app.core.mailer import Email, MailError
from app.services.emails import SITE_NAME, layout

_MAX_BODY_CHARS = 6000


def alert_email(subject: str, details: str, *, to: str, site_url: str) -> Email:
    """Message d'alerte : le sujet en titre, le journal en texte à chasse fixe."""
    excerpt = details[-_MAX_BODY_CHARS:].strip() or "(aucun détail)"
    body = (
        '<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#475569">'
        "Une tâche planifiée du serveur a échoué. Derniers messages :</p>"
        '<pre style="margin:0;padding:14px;background:#f1f5f9;border-radius:8px;font-size:12px;'
        f'line-height:1.5;color:#0f172a;white-space:pre-wrap;word-break:break-word">{escape(excerpt)}</pre>'
    )
    return Email(
        to=to,
        subject=f"[{SITE_NAME}] {subject}",
        html=layout(escape(subject), body, preheader=escape(subject), site_url=site_url),
        text=f"{subject}\n\n{excerpt}",
    )


async def run(subject: str, details: str) -> int:
    settings = get_settings()
    mailer = build_mailer(settings)
    if mailer is None or not settings.alert_email:
        print("Alerte non envoyée : ALERT_EMAIL ou serveur d'envoi non configuré.", file=sys.stderr)
        return 1
    try:
        await mailer.send(
            alert_email(subject, details, to=settings.alert_email, site_url=settings.site_url)
        )
    except MailError as exc:
        print(f"Alerte non envoyée : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else "Tâche en échec"
    sys.exit(asyncio.run(run(title, sys.stdin.read())))
