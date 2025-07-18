# src/email_summarizer/parser.py

from typing import Optional
from bs4 import BeautifulSoup

class ParsedEmail:
    """
    Encapsulates a fetched email plus validation state.
    """
    def __init__(self, raw_email):
        # copy over the basic fields
        self.id      = raw_email.id
        self.date    = getattr(raw_email, "date", "")    # <-- store the raw date string
        self.sender  = raw_email.sender
        self.subject = raw_email.subject
        self.plain   = raw_email.plain   or ""
        self.html    = raw_email.html    or ""

        # validation status / reason
        self.is_valid         = True
        self.validation_error: Optional[str] = None

        # parsed HTML soup for downstream, if any
        self.soup: Optional[BeautifulSoup] = None

def parse_email(raw_email) -> ParsedEmail:
    """
    Validate and normalize a RawEmail into a ParsedEmail.

    Accepts emails with either HTML or plain-text bodies.
    For HTML content, it parses with BeautifulSoup.
    """
    parsed = ParsedEmail(raw_email)

    # 1) If HTML is present, attempt to parse it
    if parsed.html.strip():
        try:
            parsed.soup = BeautifulSoup(parsed.html, "html.parser")
        except Exception as e:
            parsed.is_valid = False
            parsed.validation_error = f"HTML parse error: {e}"
            return parsed

    # 2) Otherwise, if only plain text is present, that's valid
    elif parsed.plain.strip():
        # nothing else to do
        pass

    # 3) If no content at all, mark invalid
    else:
        parsed.is_valid = False
        parsed.validation_error = "Email has no content"
        return parsed

    return parsed