# src/email_summarizer/utils.py

from typing import List, Dict
from datetime import timedelta
from email.utils import parsedate_to_datetime, parseaddr

def compute_response_times(
    messages: List[Dict],
    me_email: str
) -> List[Dict]:
    """
    Given a chronologically ordered list of parsed messages (each having 'date' and 'sender'),
    return one record for each time `me_email` replies to someone else.

    Each record contains:
      - reply_number: int
      - from:         str    # the other party’s email or header
      - to:           str    # your address (me_email)
      - prev_at:      datetime
      - reply_at:     datetime
      - delta:        timedelta
    """
    me = me_email.lower().strip()
    timeline = []

    # 1) Build a cleaned timeline
    for m in messages:
        raw_sender = m.get("sender", "").strip()
        raw_date   = m.get("date", "").strip()
        if not raw_sender or not raw_date:
            continue

        # parse the RFC‐822 date, skip if invalid
        try:
            dt = parsedate_to_datetime(raw_date)
        except Exception:
            continue

        # pull out the pure email address (may be empty)
        _, addr = parseaddr(raw_sender)
        addr = addr.lower().strip()

        # also keep the lowercase full header for a fallback match
        hdr_lower = raw_sender.lower()

        timeline.append({
            "addr":   addr,       # e.g. "you@example.com"
            "hdr":    hdr_lower,  # e.g. "Your Name <you@example.com>"
            "dt":     dt
        })

    # 2) Walk the timeline, find each time *you* reply to someone else
    records: List[Dict] = []
    for i, entry in enumerate(timeline):
        am_me = (entry["addr"] == me) or (me in entry["hdr"])
        if am_me:
            # look backward for the last non‐me entry
            j = i - 1
            while j >= 0:
                prev = timeline[j]
                prev_is_me = (prev["addr"] == me) or (me in prev["hdr"])
                if not prev_is_me:
                    break
                j -= 1

            if j >= 0:
                prev = timeline[j]
                delta = entry["dt"] - prev["dt"]
                records.append({
                    "reply_number": len(records) + 1,
                    "from":         prev["addr"] or prev["hdr"],
                    "to":           me,
                    "prev_at":      prev["dt"],
                    "reply_at":     entry["dt"],
                    "delta":        delta
                })

    return records