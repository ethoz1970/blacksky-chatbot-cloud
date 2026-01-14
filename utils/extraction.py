"""
Pure utility functions for extracting user information from messages.
These have no external dependencies and are easily testable.
"""
import re
from typing import Optional


def extract_user_name(messages: list) -> Optional[str]:
    """Extract user's name from conversation messages.

    Only matches explicit name declarations to avoid false positives.
    """
    # Common words that follow "I'm" but aren't names
    not_names = {
        'not', 'just', 'very', 'so', 'really', 'quite', 'pretty', 'too',
        'looking', 'interested', 'curious', 'wondering', 'trying', 'hoping',
        'here', 'back', 'new', 'happy', 'glad', 'sorry', 'sure', 'fine',
        'good', 'great', 'okay', 'ok', 'well', 'busy', 'free', 'available',
        'calling', 'writing', 'reaching', 'contacting', 'asking', 'inquiring',
        'a', 'an', 'the', 'your', 'their', 'his', 'her', 'our', 'my',
        'working', 'using', 'building', 'developing', 'creating', 'running'
    }

    # Only match explicit name patterns
    name_patterns = [
        r"(?:my name is|i'm|i am|call me|this is)\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
    ]

    # Words that signal end of name
    stop_words = {'and', 'my', 'email', 'at', 'from', 'with', 'the', 'i', 'work', 'company'}

    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            for pattern in name_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    name_part = match.group(1).strip()
                    words = name_part.split()

                    # Check if first word is a common non-name
                    if words and words[0].lower() in not_names:
                        continue

                    clean_words = []
                    for word in words:
                        if word.lower() in stop_words:
                            break
                        clean_words.append(word)

                    name = ' '.join(clean_words)
                    if 2 <= len(name) <= 50 and not any(c.isdigit() for c in name) and len(clean_words) <= 3:
                        return name.title()
    return None


def extract_user_email(messages: list) -> Optional[str]:
    """Extract user's email from conversation if they provided it."""
    # Standard email regex
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")
        match = re.search(email_pattern, text)
        if match:
            return match.group(0).lower()

    return None


def extract_user_company(messages: list) -> Optional[str]:
    """Extract user's company from conversation if they provided it."""
    # Words that aren't company names
    not_companies = {
        'a', 'an', 'the', 'here', 'there', 'home', 'work', 'school',
        'looking', 'interested', 'curious', 'wondering', 'asking',
        'legacy', 'new', 'old', 'small', 'large', 'big', 'local'
    }

    company_patterns = [
        r"(?:i work (?:at|for)|i'm (?:at|with|from)|my company is)\s+([A-Za-z0-9][\w\s&.,'-]*?)(?:\s*[,.]|\s+and\s|\s+my\s|\s+email|$)",
        r"company[:\s]+([A-Za-z0-9][\w\s&.,'-]+?)(?:\s*[,.]|\s+and\s|\s+my\s|$)",
    ]

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")

        for pattern in company_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                company = match.group(1).strip().rstrip('.,')
                words = company.split()

                # Skip if first word is a common non-company word
                if words and words[0].lower() in not_companies:
                    continue

                # Limit to max 4 words for a company name
                if len(words) > 4:
                    continue

                if 2 <= len(company) <= 50:
                    return company.title()

    return None


def extract_user_phone(messages: list) -> Optional[str]:
    """Extract user's phone number from conversation if they provided it."""
    # Common phone patterns for US/international
    phone_patterns = [
        r"(?:my (?:phone|number|cell|mobile)(?: number)? is|phone[:\s]+|call me at|reach me at)\s*([\d\s\-\(\)\+\.]+)",
        r"(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",  # US format
        r"(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})",  # Simple 10 digit
    ]

    for msg in messages:
        if msg.get("role") != "user":
            continue

        text = msg.get("content", "")

        for pattern in phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                phone = re.sub(r'[^\d+]', '', match.group(1))  # Keep only digits and +
                if 10 <= len(phone) <= 15:  # Valid phone length
                    return phone

    return None


def calculate_lead_score(messages: list) -> int:
    """
    Calculate lead score (1-5) based on intent signals in messages.

    1 = Low intent (casual browsing)
    2 = Medium intent (asking about services)
    3 = High intent (pricing, hiring, projects)
    4 = Very high intent (multiple high signals)
    5 = Extremely high intent (ready to buy)
    """
    # High intent keywords
    high_intent = [
        "pricing", "cost", "quote", "hire", "contract", "proposal",
        "budget", "timeline", "availability", "rates", "how much",
        "schedule a call", "set up a meeting"
    ]

    medium_intent = [
        "project", "help", "need", "looking for", "interested",
        "services", "capabilities", "experience", "portfolio",
        "can you", "do you do"
    ]

    # Combine all user messages
    all_text = " ".join([
        m.get("content", "").lower()
        for m in messages
        if m.get("role") == "user"
    ])

    score = 1
    high_count = 0
    medium_count = 0

    # Count matches
    for keyword in high_intent:
        if keyword in all_text:
            high_count += 1

    for keyword in medium_intent:
        if keyword in all_text:
            medium_count += 1

    # Calculate score
    if high_count >= 3:
        score = 5
    elif high_count >= 2:
        score = 4
    elif high_count >= 1:
        score = 3
    elif medium_count >= 2:
        score = 2
    elif medium_count >= 1:
        score = 2

    # Bonus for providing contact info
    if extract_user_email(messages) or extract_user_phone(messages):
        score = min(score + 1, 5)

    return score
