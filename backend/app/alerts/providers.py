"""Alert providers (techspec §2 "Alerts", task 7.2/7.3).

`AlertProvider.send(recipient, message)` returns None on success or raises `AlertError`.
Console is always available and writes to the application log; Telegram and SMTP e-mail are
optional and use only the standard library (urllib, smtplib) so no new dependency is needed.
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger("app.alerts")

TIMEOUT_S = 10.0


class AlertError(RuntimeError):
    """Delivery failed for a reason worth storing in `alerts.last_error`."""


@dataclass(frozen=True)
class AlertMessage:
    subject: str
    text: str
    link: str | None = None

    def plain(self) -> str:
        return f"{self.subject}\n\n{self.text}" + (f"\n{self.link}" if self.link else "")


class AlertProvider(Protocol):
    name: str

    def send(self, recipient: str, message: AlertMessage) -> None: ...


class ConsoleProvider:
    name = "console"

    def send(self, recipient: str, message: AlertMessage) -> None:
        logger.info(
            "ALERT %s → %s: %s", message.subject, recipient, message.text.replace("\n", " | ")
        )


class TelegramProvider:
    """Telegram Bot API `sendMessage`; recipient = chat id (user or group)."""

    name = "telegram"

    def __init__(self, bot_token: str) -> None:
        if not bot_token:
            raise AlertError("TELEGRAM_BOT_TOKEN is not set")
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, recipient: str, message: AlertMessage) -> None:
        body = urllib.parse.urlencode(
            {"chat_id": recipient, "text": message.plain(), "disable_web_page_preview": "true"}
        ).encode()
        req = urllib.request.Request(self._url, data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 - fixed https host
                payload = json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise AlertError(f"telegram http {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AlertError(f"telegram unreachable: {exc}") from exc
        if not payload.get("ok", False):
            raise AlertError(f"telegram rejected: {payload.get('description', 'unknown')}")


class EmailProvider:
    """SMTP with STARTTLS (port 587) or implicit TLS (465); recipient = e-mail address."""

    name = "email"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str) -> None:
        if not host or not sender:
            raise AlertError("SMTP_HOST and SMTP_FROM must be set")
        self.host, self.port, self.user, self.password, self.sender = (
            host,
            port,
            user,
            password,
            sender,
        )

    def send(self, recipient: str, message: AlertMessage) -> None:
        msg = EmailMessage()
        msg["Subject"] = message.subject
        msg["From"] = self.sender
        msg["To"] = recipient
        msg.set_content(message.plain())
        try:
            if self.port == 465:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=TIMEOUT_S) as s:
                    if self.user:
                        s.login(self.user, self.password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=TIMEOUT_S) as s:
                    s.starttls()
                    if self.user:
                        s.login(self.user, self.password)
                    s.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise AlertError(f"smtp: {exc}") from exc


def build_provider(name: str, settings: Settings) -> AlertProvider:
    if name == "console":
        return ConsoleProvider()
    if name == "telegram":
        return TelegramProvider(settings.telegram_bot_token.get_secret_value())
    if name == "email":
        return EmailProvider(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password.get_secret_value(),
            settings.smtp_from,
        )
    raise AlertError(f"unknown alert provider '{name}'")
