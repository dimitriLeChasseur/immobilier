"""E-mails de l'application, à la charte graphique du site.

Deux familles : les messages d'authentification, dont les gabarits sont servis au service
d'authentification (qui y insère lui-même le lien), et le reçu envoyé après un paiement.
Le HTML est en tableaux et styles en ligne, seule mise en page fiable dans les messageries.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import Any

from app.core.mailer import Email

SITE_NAME = "Audit Immobilier"
# Couleurs du site (frontend/src/style.css).
_BRAND = "#0f766e"
_BRAND_LIGHT = "#f0fdfa"
_INK = "#0f172a"
_TEXT = "#475569"
_MUTED = "#94a3b8"
_BORDER = "#e2e8f0"
_PAGE = "#f8fafc"
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _button(url: str, label: str) -> str:
    """Bouton d'action ; `url` est inséré tel quel (déjà échappé, ou repère de gabarit)."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0">'
        f'<tr><td style="border-radius:8px;background:{_BRAND}">'
        f'<a href="{url}" style="display:inline-block;padding:12px 22px;font-family:{_FONT};'
        f'font-size:15px;font-weight:600;color:#ffffff;text-decoration:none">{label}</a>'
        f"</td></tr></table>"
    )


def _paragraph(html: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{_TEXT}">{html}</p>'


def layout(title: str, body: str, *, preheader: str, site_url: str) -> str:
    """Habillage commun : bandeau à la couleur du site, carte blanche, pied de page."""
    home = escape(site_url, quote=True)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{_PAGE}">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_PAGE}">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
<tr><td style="background:{_BRAND};border-radius:16px 16px 0 0;padding:20px 28px">
<a href="{home}" style="font-family:{_FONT};font-size:18px;font-weight:700;color:#ffffff;text-decoration:none">{SITE_NAME}</a>
</td></tr>
<tr><td style="background:#ffffff;border:1px solid {_BORDER};border-top:0;border-radius:0 0 16px 16px;padding:28px;font-family:{_FONT}">
<h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;color:{_INK}">{title}</h1>
{body}
</td></tr>
<tr><td style="padding:18px 28px;font-family:{_FONT};font-size:12px;line-height:1.5;color:{_MUTED}">
{SITE_NAME} · audit d'une adresse à partir des données publiques.<br>
Vous recevez ce message parce qu'un compte utilise cette adresse e-mail sur
<a href="{home}" style="color:{_MUTED}">{home.removeprefix("https://")}</a>.
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


@dataclass(frozen=True, slots=True)
class AuthTemplate:
    subject: str
    title: str
    intro: str
    action: str
    note: str


# Messages envoyés par le service d'authentification. « {{ .ConfirmationURL }} » est le repère
# qu'il remplace par le lien à usage unique.
AUTH_TEMPLATES: dict[str, AuthTemplate] = {
    "confirmation": AuthTemplate(
        subject="Confirmez votre adresse e-mail",
        title="Confirmez votre adresse e-mail",
        intro="Bienvenue ! Il ne reste qu'à confirmer cette adresse pour activer votre compte "
        "et retrouver l'adresse que vous étiez en train d'analyser.",
        action="Confirmer mon adresse",
        note="Si vous n'avez pas créé de compte, ignorez ce message : rien ne sera activé.",
    ),
    "recovery": AuthTemplate(
        subject="Réinitialisez votre mot de passe",
        title="Réinitialisez votre mot de passe",
        intro="Vous avez demandé à choisir un nouveau mot de passe.",
        action="Choisir un nouveau mot de passe",
        note="Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : votre "
        "mot de passe actuel reste valable.",
    ),
    "magic_link": AuthTemplate(
        subject="Votre lien de connexion",
        title="Connectez-vous en un clic",
        intro="Voici le lien de connexion que vous avez demandé.",
        action="Me connecter",
        note="Ce lien ne fonctionne qu'une fois. Si vous ne l'avez pas demandé, ignorez ce "
        "message.",
    ),
    "email_change": AuthTemplate(
        subject="Confirmez votre nouvelle adresse e-mail",
        title="Confirmez votre nouvelle adresse",
        intro="Vous avez demandé à utiliser cette adresse pour votre compte.",
        action="Confirmer cette adresse",
        note="Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.",
    ),
}
_LINK = "{{ .ConfirmationURL }}"


def auth_template(kind: str, *, site_url: str) -> str | None:
    """Gabarit HTML d'un message d'authentification, None si ce message n'existe pas."""
    template = AUTH_TEMPLATES.get(kind)
    if template is None:
        return None
    body = (
        _paragraph(escape(template.intro))
        + _button(_LINK, escape(template.action))
        + _paragraph(
            "Le bouton ne fonctionne pas ? Copiez ce lien dans votre navigateur :<br>"
            f'<span style="word-break:break-all;color:{_BRAND}">{_LINK}</span>'
        )
        + _paragraph(f'<span style="font-size:13px">{escape(template.note)}</span>')
    )
    return layout(escape(template.title), body, preheader=escape(template.intro), site_url=site_url)


# --- Reçu de paiement


def format_amount(cents: Any, currency: Any) -> str:
    """« 4,99 € » à partir d'un montant en centimes."""
    amount = cents if isinstance(cents, int) else 0
    symbol = "€" if str(currency).lower() == "eur" else str(currency).upper()
    return f"{amount // 100},{amount % 100:02d} {symbol}"


def format_day(timestamp: Any) -> str:
    """« 9 octobre 2026 » à partir d'un horodatage Unix."""
    moment = datetime.fromtimestamp(timestamp if isinstance(timestamp, int | float) else 0, UTC)
    return f"{moment.day} {_MONTHS[moment.month - 1]} {moment.year}"


def _safe_url(value: Any) -> str | None:
    """Lien Stripe utilisable dans le message : HTTPS uniquement."""
    return value if isinstance(value, str) and value.startswith("https://") else None


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td style="padding:8px 0;font-size:14px;color:{_TEXT};'
        f'border-bottom:1px solid {_BORDER}">{escape(label)}</td>'
        f'<td align="right" style="padding:8px 0;font-size:14px;font-weight:600;color:{_INK};'
        f'border-bottom:1px solid {_BORDER}">{escape(value)}</td></tr>'
    )


def receipt_email(invoice: dict[str, Any], *, site_url: str) -> Email | None:
    """Confirmation de paiement avec la facture ; None si la facture n'a pas de destinataire."""
    recipient = invoice.get("customer_email")
    if not isinstance(recipient, str) or "@" not in recipient:
        return None
    lines = (invoice.get("lines") or {}).get("data") or []
    description = str((lines[0].get("description") if lines else None) or "Audit immobilier")
    metadata = invoice.get("metadata") or {}
    address = metadata.get("label")
    number = str(invoice.get("number") or invoice.get("id") or "")
    paid_at = (invoice.get("status_transitions") or {}).get("paid_at") or invoice.get("created")
    amount = format_amount(invoice.get("amount_paid"), invoice.get("currency"))
    details = [("Prestation", description)]
    if isinstance(address, str) and address:
        details.append(("Adresse débloquée", address))
    details += [("Montant payé", amount), ("Date", format_day(paid_at)), ("Facture n°", number)]

    pdf, online = (
        _safe_url(invoice.get("invoice_pdf")),
        _safe_url(invoice.get("hosted_invoice_url")),
    )
    account = f"{site_url.rstrip('/')}/compte"
    table = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:6px 0 4px;background:{_BRAND_LIGHT};border-radius:12px">'
        '<tr><td style="padding:10px 18px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        + "".join(_row(label, value) for label, value in details)
        + "</table></td></tr></table>"
    )
    invoice_button = _button(escape(pdf, quote=True), "Télécharger la facture (PDF)") if pdf else ""
    online_link = (
        _paragraph(
            f'<a href="{escape(online, quote=True)}" style="color:{_BRAND}">Voir la facture en ligne</a>'
        )
        if online
        else ""
    )
    body = (
        _paragraph(
            "Merci pour votre achat. Votre paiement est confirmé, en voici le récapitulatif."
        )
        + table
        + invoice_button
        + online_link
        + _paragraph(
            f'Vos audits débloqués sont dans <a href="{escape(account, quote=True)}" '
            f'style="color:{_BRAND}">votre compte</a>.'
        )
    )
    text_lines = ["Merci pour votre achat. Votre paiement est confirmé.", ""]
    text_lines += [f"{label} : {value}" for label, value in details]
    text_lines += ["", f"Facture (PDF) : {pdf}" if pdf else "", f"Vos audits : {account}"]
    return Email(
        to=recipient,
        subject=f"Votre reçu {SITE_NAME} : {amount}",
        html=layout(
            "Paiement confirmé",
            body,
            preheader=escape(f"{description} : {amount}. Votre facture est jointe en lien."),
            site_url=site_url,
        ),
        text="\n".join(line for line in text_lines if line is not None),
    )
