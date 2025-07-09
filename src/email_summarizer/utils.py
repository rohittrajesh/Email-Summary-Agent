# src/email_summarizer/utils.py

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Dict

def compute_response_times(msgs: List[Dict], me: str) -> List[Dict]:
    """
    Given a list of parsed messages (each with 'date' and 'sender')
    and your own email address `me`, compute how long it took you to reply
    each time someone else sent you a message.
    Returns a list of records:
      {
        'reply_number': int,
        'from': str,            # who you were replying to
        'delta': timedelta,     # how long after their message
        'reply_at': datetime,   # when you replied
      }
    """
    recs = []
    last_received = None
    reply_count = 0

    for msg in msgs:
        raw_date = msg.get("date", "")
        try:
            dt = parsedate_to_datetime(raw_date)
        except Exception:
            continue

        sender = msg.get("sender", "")
        # Normalize to lowercase for comparison
        if me.lower() not in sender.lower():
            # Incoming message
            last_received = {"from": sender, "received_at": dt}
        else:
            # Your reply
            if last_received:
                delta = dt - last_received["received_at"]
                reply_count += 1
                recs.append({
                    "reply_number": reply_count,
                    "from": last_received["from"],
                    "delta": delta,
                    "reply_at": dt,
                })
                last_received = None

    return recs


def extract_signature_block(body: str) -> str:
    """
    Heuristically pull out the “signature” portion at the end of an email body.
    Looks for common delimiters like:
      -- 
      Cheers,
      Best regards,
      Sent from my …
    If none are found, returns the last five lines as a fallback.
    """
    # Common signature delimiters (regexes)
    delimiters = [
        r"(?m)^\s*--\s*$",                       # line with just “-- ”
        r"(?mi)^(best|cheers|regards|sincerely)[\s,]*$",  # “Best regards,” etc.
        r"(?m)^Sent from my .*$",               # mobile signature
    ]

    for delim in delimiters:
        parts = re.split(delim, body)
        if len(parts) > 1:
            return parts[-1].strip()

    # Fallback: last 5 non-empty lines
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return "\n".join(lines[-5:]).strip()
