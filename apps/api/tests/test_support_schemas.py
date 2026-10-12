import pytest
from pydantic import ValidationError

from app.support.schemas import TicketAdminPatch, TicketCreate, TicketMessageCreate


def test_support_ticket_payloads_validate_and_reject_extra_fields():
    ticket = TicketCreate(category="booking", subject="Booking confirmation", message="Please help with my booking.")
    assert ticket.category == "booking"
    with pytest.raises(ValidationError):
        TicketCreate(category="unknown", subject="Help request", message="A long enough support message", is_admin=True)
    with pytest.raises(ValidationError):
        TicketMessageCreate(message=" ")


def test_admin_support_changes_require_reason_and_valid_state():
    patch = TicketAdminPatch(status="in_progress", reason="Agent picked up this customer ticket")
    assert patch.status == "in_progress"
    with pytest.raises(ValidationError):
        TicketAdminPatch(status="anything", reason="too short")
