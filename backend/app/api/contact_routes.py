from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.accounts import EMAIL_PATTERN
from app.api.deps import settings_of
from app.api.security import client_ip
from app.errors import UserError
from app.logging_setup import log_event
from app.metrics import metrics

public = APIRouter(prefix="/api")

TOPICS = {"general": "General question", "sales": "Sales and teams", "support": "Product support", "security": "Security report", "privacy": "Privacy request"}


class ContactRequest(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    topic: Literal["general", "sales", "support", "security", "privacy"] = "general"
    message: str = Field(max_length=4000)
    website: str = Field("", max_length=200)


class ContactResponse(BaseModel):
    sent: bool


def invalid(message: str, field: str) -> UserError:
    return UserError(message, f"invalid_{field}", 422)


@public.post("/contact")
def send_contact(request: Request, body: ContactRequest) -> ContactResponse:
    settings = settings_of(request)
    mailer = request.app.state.mailer
    if not settings.contact_email or not mailer.enabled:
        raise UserError("The contact form is not available on this server. Please email us instead.", "contact_disabled", 404)
    request.app.state.limiter.check("contact", client_ip(request), settings.contact_per_hour, 3600)
    name = " ".join(body.name.split())
    email = body.email.strip()
    message = body.message.strip()
    if not name:
        raise invalid("Enter your name.", "name")
    if not EMAIL_PATTERN.match(email):
        raise invalid("Enter a valid email address so we can reply.", "email")
    if len(message) < 20:
        raise invalid("Tell us a little more. The message needs at least 20 characters.", "message")
    if body.website:
        metrics.inc("datapilot_contact_total", status="spam")
        return ContactResponse(sent=True)
    text = f"Name: {name}\nEmail: {email}\nTopic: {TOPICS[body.topic]}\n\n{message}\n"
    mailer.send(settings.contact_email, f"[DataPilot] {TOPICS[body.topic]} from {name}", text, reply_to=email)
    metrics.inc("datapilot_contact_total", status="accepted")
    log_event("contact_received", topic=body.topic)
    return ContactResponse(sent=True)
