"""Envoi d'e-mails par SMTP, asynchrone."""

import logging
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

import aiosmtplib

logger = logging.getLogger(__name__)

_TIMEOUT_S = 10
_SUBMISSION_PORT = 587
_IMPLICIT_TLS_PORT = 465


class MailError(Exception):
    """Le message n'a pas pu être remis au serveur d'envoi."""


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    html: str
    # Version texte : lue par les clients qui n'affichent pas le HTML, et par les filtres antispam.
    text: str


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender_email: str,
        sender_name: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username or None
        self._password = password or None
        self._sender = formataddr((sender_name, sender_email))

    async def send(self, email: Email) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.text)
        message.add_alternative(email.html, subtype="html")
        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                # 587 : chiffrement négocié (STARTTLS) ; 465 : TLS dès la connexion.
                start_tls=self._port == _SUBMISSION_PORT,
                use_tls=self._port == _IMPLICIT_TLS_PORT,
                timeout=_TIMEOUT_S,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise MailError(type(exc).__name__) from exc
