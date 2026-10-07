import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

from app.config import Settings
from app.errors import UserError
from app.logging_setup import log_event
from app.metrics import metrics


class Mailer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="datapilot-mail")

    @property
    def enabled(self) -> bool:
        return self.settings.email_enabled()

    def build(self, to: str, subject: str, body: str) -> EmailMessage:
        if any(ch in to + subject for ch in "\r\n"):
            raise UserError("Invalid email header.", "invalid_email", 422)
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        return message

    def deliver(self, message: EmailMessage) -> None:
        s = self.settings
        if s.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        with client:
            if s.smtp_security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                client.login(s.smtp_user, s.smtp_password)
            client.send_message(message)

    def send_now(self, to: str, subject: str, body: str) -> bool:
        if not self.enabled:
            return False
        try:
            self.deliver(self.build(to, subject, body))
            metrics.inc("datapilot_emails_total", status="sent")
            log_event("email_sent", subject=subject[:60])
            return True
        except Exception:
            metrics.inc("datapilot_emails_total", status="failed")
            log_event("email_failed", subject=subject[:60], exc_info=True)
            return False

    def send(self, to: str, subject: str, body: str) -> None:
        if self.enabled:
            self.pool.submit(self.send_now, to, subject, body)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
