# src/email_summarizer/utils.py

import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any
from .parser import ParsedEmail

# your own address, for reply-time logic
SELF_EMAIL = os.getenv("IMAP_USER", "").lower()


def extract_fields(parsed: ParsedEmail) -> List[Dict[str, Any]]:
    """
    Walk the parsed.soup (BeautifulSoup) of a ParsedEmail and pull out each
    cell (<td> or <th>) in the first <table>, returning a list of dicts:
      [{"name": <str>, "value": <str>, "message": <str>}, ...]
    """
    fields: List[Dict[str, Any]] = []
    if not parsed.soup:
        return fields

    table = parsed.soup.find("table")
    if not table:
        return fields

    for row in table.find_all("tr"):
        for cell in row.find_all(["td", "th"]):
            name  = cell.get("data-name", "value")
            value = cell.get_text(strip=True)
            fields.append({
                "name":    name,
                "value":   value,
                "message": ""               # or extra context
            })

    return fields


def compute_response_times(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Given a list of dicts each with 'date' (string) and 'sender':
      - Identify incoming messages (sender != SELF_EMAIL)
      - Then the next SELF_EMAIL message is your reply
      - Compute reply delta in seconds

    Returns a list of:
      {
        "reply_number":  int,
        "from":          str,     # who you replied to
        "delta_seconds": float,   # reply latency
        "reply_at":      str,     # ISO timestamp of reply
      }
    """
    recs = []
    last_received = None
    reply_count = 0

    for msg in messages:
        raw_date = msg.get("date", "")
        try:
            dt = parsedate_to_datetime(raw_date)
        except Exception:
            continue

        sender = msg.get("sender", "").lower()
        if SELF_EMAIL and SELF_EMAIL not in sender:
            # someone else → mark incoming
            last_received = {"from": msg.get("sender",""), "when": dt}
        else:
            # it's you replying
            if last_received:
                delta = dt - last_received["when"]
                reply_count += 1
                recs.append({
                    "reply_number":  reply_count,
                    "from":          last_received["from"],
                    "delta_seconds": delta.total_seconds(),
                    "reply_at":      dt.isoformat(),
                })
                last_received = None

    return recs


def extract_signature_block(body: str) -> str:
    """
    Heuristically pull out the “signature” portion at the end of an email body.
    Looks for common delimiters (`-- `, “Best regards,”, etc.). If none found,
    returns the last five non-empty lines.
    """
    delimiters = [
        r"(?m)^\s*--\s*$",                       # line with just “-- ”
        r"(?mi)^(best|cheers|regards|sincerely)[\s,]*$",  # “Best…” etc.
        r"(?m)^Sent from my .*$",               # mobile signature
    ]

    for delim in delimiters:
        parts = re.split(delim, body)
        if len(parts) > 1:
            return parts[-1].strip()

    # fallback: last 5 non-empty lines
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return "\n".join(lines[-5:]).strip()