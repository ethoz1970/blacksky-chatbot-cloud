"""
Tests for Maurice prompt rules.
Verifies that prompts contain required lead capture and action limitation rules.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from prompts import SYSTEM_PROMPT


class TestHighIntentSignalRules:
    """Tests for HIGH-INTENT SIGNALS prompt rules."""

    def test_requires_contact_info_before_scheduling(self):
        """Prompt requires name and email before offering to schedule calls."""
        assert "MUST have the user's name and email" in SYSTEM_PROMPT

    def test_no_direct_scheduling_claims(self):
        """Prompt forbids claiming to schedule meetings directly."""
        assert "NEVER claim to send calendar invites" in SYSTEM_PROMPT
        assert "schedule meetings" in SYSTEM_PROMPT

    def test_offers_to_pass_info_to_mario(self):
        """Prompt instructs to pass info to Mario instead of scheduling."""
        assert "pass your info to Mario" in SYSTEM_PROMPT or "pass your details to Mario" in SYSTEM_PROMPT


class TestActionLimitationRules:
    """Tests for ACTION LIMITATIONS prompt rules."""

    def test_cannot_send_emails(self):
        """Prompt states Maurice cannot send emails."""
        assert "CANNOT send emails" in SYSTEM_PROMPT

    def test_cannot_send_calendar_invites(self):
        """Prompt states Maurice cannot send calendar invites."""
        assert "CANNOT send" in SYSTEM_PROMPT and "calendar invites" in SYSTEM_PROMPT

    def test_cannot_schedule_directly(self):
        """Prompt states Maurice cannot schedule anything directly."""
        assert "CANNOT" in SYSTEM_PROMPT and "schedule anything directly" in SYSTEM_PROMPT

    def test_can_collect_information(self):
        """Prompt states Maurice CAN collect user information."""
        assert "CAN collect information" in SYSTEM_PROMPT

    def test_honest_about_limitations(self):
        """Prompt requires honesty about capabilities."""
        assert "Always be honest about what you can and cannot do" in SYSTEM_PROMPT

    def test_alternative_phrasing_for_scheduling(self):
        """Prompt provides alternative phrasing for scheduling requests."""
        assert "I'll pass your details to Mario" in SYSTEM_PROMPT

    def test_alternative_phrasing_for_invites(self):
        """Prompt provides alternative phrasing for calendar invites."""
        assert "I've noted your interest" in SYSTEM_PROMPT or "Mario will follow up" in SYSTEM_PROMPT
