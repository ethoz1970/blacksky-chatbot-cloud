"""
Tests for user information extraction functions.
Run with: pytest tests/test_extraction.py -v
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import from utils
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.extraction import (
    extract_user_name,
    extract_user_email,
    extract_user_phone,
    extract_user_company,
    calculate_lead_score
)


# Helper to create message list
def msg(content: str, role: str = "user") -> list:
    """Create a single-message list for testing."""
    return [{"role": role, "content": content}]


def msgs(*contents: str) -> list:
    """Create a multi-message conversation (alternating user/assistant)."""
    messages = []
    for i, content in enumerate(contents):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": content})
    return messages


# ============================================================
# extract_user_name tests
# ============================================================

class TestExtractUserName:
    """Tests for extract_user_name function."""

    # Basic patterns
    def test_my_name_is(self):
        assert extract_user_name(msg("My name is John")) == "John"

    def test_my_name_is_full(self):
        assert extract_user_name(msg("My name is John Smith")) == "John Smith"

    def test_im_name(self):
        assert extract_user_name(msg("I'm Sarah")) == "Sarah"

    def test_i_am_name(self):
        assert extract_user_name(msg("I am Michael")) == "Michael"

    def test_call_me(self):
        assert extract_user_name(msg("Call me Dave")) == "Dave"

    def test_this_is(self):
        assert extract_user_name(msg("This is Maria")) == "Maria"

    # Case handling
    def test_lowercase_name(self):
        assert extract_user_name(msg("my name is john")) == "John"

    def test_mixed_case(self):
        assert extract_user_name(msg("My name is JOHN SMITH")) == "John Smith"

    # Three-part names
    def test_three_part_name(self):
        assert extract_user_name(msg("My name is Mary Jane Watson")) == "Mary Jane Watson"

    # Stop words
    def test_stops_at_and(self):
        assert extract_user_name(msg("My name is John and I work at Google")) == "John"

    def test_stops_at_my(self):
        assert extract_user_name(msg("My name is Sarah my email is test@test.com")) == "Sarah"

    def test_stops_at_from(self):
        assert extract_user_name(msg("I'm Mike from Acme Corp")) == "Mike"

    # Edge cases
    def test_no_name(self):
        assert extract_user_name(msg("Hello, how are you?")) is None

    def test_assistant_message_ignored(self):
        assert extract_user_name([{"role": "assistant", "content": "My name is Maurice"}]) is None

    def test_name_too_short(self):
        assert extract_user_name(msg("My name is X")) is None

    def test_name_with_numbers_extracts_clean_part(self):
        # Numbers get stripped, leaving valid name
        assert extract_user_name(msg("My name is John123")) == "John"

    def test_finds_name_in_later_message(self):
        messages = msgs(
            "Hello there!",
            "Hello! How can I help?",
            "My name is Jessica"
        )
        assert extract_user_name(messages) == "Jessica"

    def test_standalone_greeting_not_matched(self):
        # "Hello" should not be matched as a name (regression test)
        assert extract_user_name(msg("Hello")) is None
        assert extract_user_name(msg("Hi There")) is None
        assert extract_user_name(msg("Good morning")) is None

    def test_common_phrases_not_matched_as_names(self):
        # "I'm not/interested/curious" should not match as names
        assert extract_user_name(msg("I'm not sure about that")) is None
        assert extract_user_name(msg("I'm interested in your services")) is None
        assert extract_user_name(msg("I'm curious how this works")) is None
        assert extract_user_name(msg("I'm looking for a consultant")) is None
        assert extract_user_name(msg("I'm working on a project")) is None
        assert extract_user_name(msg("I'm just browsing")) is None

    def test_capitalized_name_after_im(self):
        # Only properly capitalized names should match after I'm
        assert extract_user_name(msg("I'm John")) == "John"
        assert extract_user_name(msg("I'm Sarah Smith")) == "Sarah Smith"


# ============================================================
# extract_user_email tests
# ============================================================

class TestExtractUserEmail:
    """Tests for extract_user_email function."""

    # Basic patterns
    def test_simple_email(self):
        assert extract_user_email(msg("my email is john@example.com")) == "john@example.com"

    def test_email_in_sentence(self):
        assert extract_user_email(msg("You can reach me at sarah@company.org")) == "sarah@company.org"

    def test_email_with_dots(self):
        assert extract_user_email(msg("john.smith@example.com")) == "john.smith@example.com"

    def test_email_with_plus(self):
        assert extract_user_email(msg("test+label@gmail.com")) == "test+label@gmail.com"

    def test_email_with_numbers(self):
        assert extract_user_email(msg("user123@test.io")) == "user123@test.io"

    # Case handling
    def test_uppercase_email_lowercased(self):
        assert extract_user_email(msg("JOHN@EXAMPLE.COM")) == "john@example.com"

    def test_mixed_case_lowercased(self):
        assert extract_user_email(msg("John.Smith@Company.COM")) == "john.smith@company.com"

    # Edge cases
    def test_no_email(self):
        assert extract_user_email(msg("I don't have an email")) is None

    def test_invalid_email_no_at(self):
        assert extract_user_email(msg("my email is johnexample.com")) is None

    def test_invalid_email_no_domain(self):
        assert extract_user_email(msg("my email is john@")) is None

    def test_assistant_message_ignored(self):
        assert extract_user_email([{"role": "assistant", "content": "Email me at bot@ai.com"}]) is None

    def test_finds_email_in_conversation(self):
        messages = msgs(
            "I need help with a project",
            "Sure! What's your email?",
            "It's mike@startup.io"
        )
        assert extract_user_email(messages) == "mike@startup.io"


# ============================================================
# extract_user_phone tests
# ============================================================

class TestExtractUserPhone:
    """Tests for extract_user_phone function."""

    # Basic US formats
    def test_simple_10_digit(self):
        result = extract_user_phone(msg("My phone is 5551234567"))
        assert result == "5551234567"

    def test_dashed_format(self):
        result = extract_user_phone(msg("Call me at 555-123-4567"))
        assert result == "5551234567"

    def test_dotted_format(self):
        result = extract_user_phone(msg("555.123.4567"))
        assert result == "5551234567"

    def test_parentheses_format(self):
        result = extract_user_phone(msg("(555) 123-4567"))
        assert result == "5551234567"

    def test_with_country_code(self):
        result = extract_user_phone(msg("+1 555-123-4567"))
        assert result == "+15551234567" or result == "15551234567"

    # Contextual patterns
    def test_my_phone_is(self):
        result = extract_user_phone(msg("My phone is 555-123-4567"))
        assert result == "5551234567"

    def test_my_number_is(self):
        result = extract_user_phone(msg("My number is 555-123-4567"))
        assert result == "5551234567"

    def test_call_me_at(self):
        result = extract_user_phone(msg("Call me at 555-123-4567"))
        assert result == "5551234567"

    def test_reach_me_at(self):
        result = extract_user_phone(msg("Reach me at 555-123-4567"))
        assert result == "5551234567"

    # Edge cases
    def test_no_phone(self):
        assert extract_user_phone(msg("I don't have a phone")) is None

    def test_too_short(self):
        assert extract_user_phone(msg("Call 555-1234")) is None

    def test_assistant_message_ignored(self):
        assert extract_user_phone([{"role": "assistant", "content": "Call 555-123-4567"}]) is None

    def test_finds_phone_in_conversation(self):
        messages = msgs(
            "I want to discuss a project",
            "Great! What's your phone number?",
            "It's 555-867-5309"
        )
        result = extract_user_phone(messages)
        assert result == "5558675309"


# ============================================================
# extract_user_company tests
# ============================================================

class TestExtractUserCompany:
    """Tests for extract_user_company function."""

    # Basic patterns
    def test_i_work_at(self):
        assert extract_user_company(msg("I work at Google")) == "Google"

    def test_i_work_for(self):
        assert extract_user_company(msg("I work for Microsoft")) == "Microsoft"

    def test_im_at(self):
        assert extract_user_company(msg("I'm at Amazon")) == "Amazon"

    def test_im_with(self):
        assert extract_user_company(msg("I'm with Tesla")) == "Tesla"

    def test_im_from(self):
        assert extract_user_company(msg("I'm from Apple")) == "Apple"

    def test_my_company_is(self):
        assert extract_user_company(msg("My company is Blacksky")) == "Blacksky"

    def test_from_company(self):
        # "I'm from" pattern for company
        assert extract_user_company(msg("I'm from Acme Corp")) == "Acme Corp"

    # Multi-word companies
    def test_multi_word_company(self):
        assert extract_user_company(msg("I work at General Electric")) == "General Electric"

    def test_company_with_ampersand(self):
        result = extract_user_company(msg("I work at Johnson & Johnson"))
        assert "Johnson" in result

    # Case handling
    def test_lowercase_company_titlecased(self):
        assert extract_user_company(msg("I work at google")) == "Google"

    # Edge cases
    def test_no_company(self):
        assert extract_user_company(msg("Hello, I need help")) is None

    def test_assistant_message_ignored(self):
        assert extract_user_company([{"role": "assistant", "content": "I work at Blacksky"}]) is None

    def test_stops_at_and(self):
        result = extract_user_company(msg("I work at Acme and I love it"))
        assert result == "Acme"

    def test_stops_at_my(self):
        result = extract_user_company(msg("I work at Acme my email is test@test.com"))
        assert result == "Acme"

    def test_finds_company_in_conversation(self):
        messages = msgs(
            "We're looking for a consultant",
            "What company are you with?",
            "I work for SpaceX"
        )
        assert extract_user_company(messages) == "Spacex"


# ============================================================
# Integration tests - multiple extractions from one conversation
# ============================================================

class TestMultipleExtractions:
    """Test extracting multiple pieces of info from a conversation."""

    def test_extract_name_and_email(self):
        messages = msgs(
            "Hi, I need help with a project",
            "Sure! What's your name?",
            "I'm John Smith, my email is john@company.com"
        )
        assert extract_user_name(messages) == "John Smith"
        assert extract_user_email(messages) == "john@company.com"

    def test_extract_all_info(self):
        messages = [
            {"role": "user", "content": "Hello there!"},
            {"role": "assistant", "content": "Hello! How can I help?"},
            {"role": "user", "content": "My name is Sarah Jones"},
            {"role": "assistant", "content": "Nice to meet you Sarah!"},
            {"role": "user", "content": "I work at Acme Corp, my email is sarah@acme.com and my phone is 555-123-4567"}
        ]
        assert extract_user_name(messages) == "Sarah Jones"
        assert extract_user_email(messages) == "sarah@acme.com"
        assert extract_user_phone(messages) == "5551234567"
        assert extract_user_company(messages) == "Acme Corp"


# ============================================================
# calculate_lead_score tests
# ============================================================

class TestCalculateLeadScore:
    """Tests for calculate_lead_score function."""

    def test_casual_browsing_score_1(self):
        messages = msg("Hello, just looking around")
        assert calculate_lead_score(messages) == 1

    def test_medium_intent_score_2(self):
        messages = msg("I need help with a project")
        assert calculate_lead_score(messages) >= 2

    def test_high_intent_pricing_score_3(self):
        messages = msg("What's your pricing for consulting?")
        assert calculate_lead_score(messages) >= 3

    def test_high_intent_hire_score_3(self):
        messages = msg("I want to hire someone for development")
        assert calculate_lead_score(messages) >= 3

    def test_high_intent_quote_score_3(self):
        messages = msg("Can I get a quote for this project?")
        assert calculate_lead_score(messages) >= 3

    def test_multiple_high_signals_higher_score(self):
        messages = msg("I need pricing and want to schedule a meeting to discuss a contract")
        score = calculate_lead_score(messages)
        assert score >= 4

    def test_contact_info_bonus(self):
        # Without contact info
        messages1 = msg("What's your pricing?")
        score1 = calculate_lead_score(messages1)

        # With contact info
        messages2 = msgs(
            "What's your pricing?",
            "Here's our rates...",
            "Great, my email is test@example.com"
        )
        score2 = calculate_lead_score(messages2)

        assert score2 > score1

    def test_max_score_is_5(self):
        messages = msgs(
            "I need pricing and a quote for a contract",
            "Sure!",
            "Let's schedule a call to discuss budget and timeline. My email is ceo@bigcorp.com"
        )
        score = calculate_lead_score(messages)
        assert score <= 5
