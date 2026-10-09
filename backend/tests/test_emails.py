"""E-mails : gabarits à la charte du site, reçu de paiement, envoi SMTP."""

from email.message import EmailMessage
from typing import Any

import aiosmtplib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import emails
from app.core.mailer import Email, MailError, SmtpMailer
from app.core.security import AuthenticatedUser
from app.notify import alert_email
from app.services.billing import OFFERS, BillingService, CheckoutTarget, checkout_params
from app.services.emails import (
    AUTH_TEMPLATES,
    auth_template,
    format_amount,
    format_day,
    receipt_email,
)

SITE = "https://audit-immobilier.fr"
INVOICE = {
    "id": "in_1",
    "number": "A1B2C3D4-0001",
    "customer_email": "client@example.org",
    "amount_paid": 499,
    "currency": "eur",
    "status_transitions": {"paid_at": 1_791_549_000},
    "hosted_invoice_url": "https://invoice.stripe.com/i/acct_1/test_abc",
    "invoice_pdf": "https://pay.stripe.com/invoice/acct_1/test_abc/pdf",
    "lines": {"data": [{"description": "Audit Contre-Visite (1 adresse)"}]},
    "metadata": {"label": "10 Rue du Canal 49100 Angers"},
}


@pytest.mark.parametrize("kind", sorted(AUTH_TEMPLATES))
def test_auth_templates_carry_the_link_placeholder_and_the_site_identity(kind: str) -> None:
    html = auth_template(kind, site_url=SITE)
    assert html is not None
    # Le service d'authentification remplace ce repère par le lien à usage unique.
    assert html.count("{{ .ConfirmationURL }}") == 2
    assert "Audit Immobilier" in html
    assert "#0f766e" in html
    assert 'lang="fr"' in html
    assert f'href="{SITE}"' in html
    assert "<script" not in html


def test_unknown_template_does_not_exist() -> None:
    assert auth_template("../../etc/passwd", site_url=SITE) is None


def test_templates_are_served_to_the_auth_service() -> None:
    app = FastAPI()
    app.include_router(emails.router)
    client = TestClient(app)
    response = client.get("/emails/confirmation.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Confirmer mon adresse" in response.text
    assert client.get("/emails/inconnu.html").status_code == 404


def test_amounts_and_dates_are_written_the_french_way() -> None:
    assert format_amount(499, "eur") == "4,99 €"
    assert format_amount(2499, "eur") == "24,99 €"
    assert format_amount(5880, "EUR") == "58,80 €"
    assert format_amount(None, "usd") == "0,00 USD"
    assert format_day(1_791_549_000) == "9 octobre 2026"


def test_receipt_summarises_the_purchase_and_links_the_invoice() -> None:
    email = receipt_email(INVOICE, site_url=SITE)
    assert email is not None
    assert email.to == "client@example.org"
    assert email.subject == "Votre reçu Audit Immobilier : 4,99 €"
    for expected in (
        "Paiement confirmé",
        "Audit Contre-Visite (1 adresse)",
        "10 Rue du Canal 49100 Angers",
        "4,99 €",
        "9 octobre 2026",
        "A1B2C3D4-0001",
        'href="https://pay.stripe.com/invoice/acct_1/test_abc/pdf"',
        'href="https://invoice.stripe.com/i/acct_1/test_abc"',
        f'href="{SITE}/compte"',
    ):
        assert expected in email.html
    assert "Montant payé : 4,99 €" in email.text
    assert "Facture (PDF) : https://pay.stripe.com/invoice/acct_1/test_abc/pdf" in email.text


def test_receipt_escapes_what_comes_from_outside_and_drops_unsafe_links() -> None:
    hostile = INVOICE | {
        "metadata": {"label": '<img src=x onerror="alert(1)">'},
        "invoice_pdf": "javascript:alert(1)",
        "hosted_invoice_url": None,
    }
    email = receipt_email(hostile, site_url=SITE)
    assert email is not None
    assert "<img" not in email.html
    assert "&lt;img" in email.html
    assert "javascript:" not in email.html
    assert "Télécharger la facture" not in email.html


def test_receipt_needs_a_recipient() -> None:
    assert receipt_email(INVOICE | {"customer_email": None}, site_url=SITE) is None
    assert receipt_email({}, site_url=SITE) is None


class Outbox:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[Email] = []
        self.fail = fail

    async def send(self, email: Email) -> None:
        if self.fail:
            raise MailError("SMTPConnectError")
        self.sent.append(email)


class Events:
    """Seule la mémoire des évènements traités compte pour l'envoi du reçu."""

    def __init__(self) -> None:
        self.recorded: set[str] = set()

    async def is_recorded(self, event_id: str) -> bool:
        return event_id in self.recorded

    async def record_event(self, event_id: str, event_type: str) -> bool:
        self.recorded.add(event_id)
        return True


def service(mailer: Outbox | None, events: Events) -> BillingService:
    return BillingService(
        http=None,  # type: ignore[arg-type]
        repository=events,  # type: ignore[arg-type]
        geocoder=None,  # type: ignore[arg-type]
        secret_key="sk_test_x",  # noqa: S106
        webhook_secret="whsec_test",  # noqa: S106
        api_url="https://stripe.test",
        site_url=SITE,
        mailer=mailer,
    )


def paid(event_id: str = "evt_inv_1", **overrides: Any) -> dict[str, Any]:
    return {"id": event_id, "type": "invoice.paid", "data": {"object": INVOICE | overrides}}


async def test_a_paid_invoice_sends_one_receipt_even_if_delivered_twice() -> None:
    outbox, events = Outbox(), Events()
    billing = service(outbox, events)
    assert await billing.handle_event(paid()) == "receipt_sent"
    assert await billing.handle_event(paid()) == "duplicate"
    assert [email.to for email in outbox.sent] == ["client@example.org"]


async def test_a_failed_delivery_is_retried_by_the_next_event() -> None:
    outbox, events = Outbox(fail=True), Events()
    billing = service(outbox, events)
    with pytest.raises(MailError):
        await billing.handle_event(paid())
    # L'évènement n'est pas noté comme traité : la prochaine présentation renverra le reçu.
    assert events.recorded == set()
    outbox.fail = False
    assert await billing.handle_event(paid()) == "receipt_sent"


async def test_without_mail_server_or_recipient_nothing_is_sent() -> None:
    events = Events()
    assert await service(None, events).handle_event(paid()) == "email_disabled"
    outbox = Outbox()
    assert await service(outbox, events).handle_event(paid(customer_email=None)) == "ignored"
    assert outbox.sent == []


def test_one_off_purchases_ask_stripe_for_an_invoice() -> None:
    user = AuthenticatedUser(id="3f0c1f0e-6f1d-4b1e-9d59-0a1c2b3d4e5f", email="a@example.org")
    target = CheckoutTarget(47.4739, -0.5508, "49007_1350_00010", "10 Rue du Canal 49100 Angers")
    unit = checkout_params(OFFERS["unit"], user, target, site_url=SITE)
    assert unit["invoice_creation[enabled]"] == "true"
    assert unit["invoice_creation[invoice_data][metadata][label]"] == target.label
    # Un abonnement émet déjà ses factures : rien à demander de plus.
    pro = checkout_params(OFFERS["pro"], user, None, site_url=SITE)
    assert "invoice_creation[enabled]" not in pro


async def test_smtp_message_has_both_parts_and_negotiates_encryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_send(message: EmailMessage, **options: Any) -> None:
        calls.append({"message": message, **options})

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    mailer = SmtpMailer(
        host="smtp.example.org",
        port=587,
        username="user",
        password="secret",  # noqa: S106
        sender_email="bonjour@audit-immobilier.fr",
        sender_name="Audit Immobilier",
    )
    await mailer.send(Email(to="client@example.org", subject="Reçu", html="<p>x</p>", text="x"))

    message = calls[0]["message"]
    assert message["From"] == "Audit Immobilier <bonjour@audit-immobilier.fr>"
    assert message["To"] == "client@example.org"
    assert [part.get_content_type() for part in message.iter_parts()] == ["text/plain", "text/html"]
    assert (calls[0]["start_tls"], calls[0]["use_tls"]) == (True, False)

    async def refused(message: EmailMessage, **options: Any) -> None:
        raise aiosmtplib.SMTPConnectError("refusé")

    monkeypatch.setattr(aiosmtplib, "send", refused)
    with pytest.raises(MailError):
        await mailer.send(Email(to="a@b.fr", subject="x", html="x", text="x"))


def test_alert_message_quotes_the_end_of_the_log_safely() -> None:
    log = "ligne ancienne\n" * 2000 + "Erreur : sauvegarde <illisible>"
    email = alert_email("Sauvegarde en échec", log, to="exploitant@example.org", site_url=SITE)
    assert email.subject == "[Audit Immobilier] Sauvegarde en échec"
    assert email.to == "exploitant@example.org"
    # La fin du journal, là où se trouve l'erreur, est conservée et échappée.
    assert "sauvegarde &lt;illisible&gt;" in email.html
    assert len(email.text) < 7000
    assert alert_email("x", "", to="a@b.fr", site_url=SITE).text.endswith("(aucun détail)")
