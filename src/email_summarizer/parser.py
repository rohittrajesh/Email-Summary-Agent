import re
from typing import List, Dict
import email
from email import policy
from email.parser import BytesParser
from html import unescape

# src/email_summarizer/parser.py

import email
from email import policy
from email.parser import BytesParser
from typing import List, Dict
from html import unescape
import re

def _get_body(msg: email.message.Message) -> str:
    """
    Return the text content of an email.message.Message.
    1) Try text/plain parts first
    2) If none, fall back to text/html and strip tags
    """
    # walk multipart
    if msg.is_multipart():
        # first pass: look for text/plain
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="ignore").strip()
                except Exception:
                    continue

        # second pass: look for text/html
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    html = payload.decode(charset, errors="ignore")
                    # strip tags
                    text = re.sub(r"<[^>]+>", "", html)
                    return unescape(text).strip()
                except Exception:
                    continue

        return ""

    # not multipart: single part
    ctype = msg.get_content_type()
    payload = msg.get_payload(decode=True)
    charset = msg.get_content_charset() or "utf-8"
    try:
        raw = payload.decode(charset, errors="ignore")
    except Exception:
        raw = payload.decode("utf-8", errors="ignore")

    if ctype == "text/plain":
        return raw.strip()
    if ctype == "text/html":
        text = re.sub(r"<[^>]+>", "", raw)
        return unescape(text).strip()

    return ""


def parse_email(raw: str) -> List[Dict]:
    """
    Given a full raw email (with headers, MIME parts, etc) 
    return a list of dicts: one per message in the thread,
    each dict has keys: date, sender, body.
    """
    # first, parse into a top-level Message
    msg: email.message.Message = BytesParser(policy=policy.default).parsebytes(raw.encode("utf-8", errors="ignore"))

    # if it's a thread, Gmail wraps multiple parts under a single multipart,
    # but for now we assume raw is one message; if you want to split threads
    # you can feed each part in reverse-chron order, etc.
    # Here we just return a single‐element list.
    return [{
        "date": msg["Date"] or "",
        "sender": msg["From"] or "",
        "body": _get_body(msg),
    }]


def parse_linkedin(html: str) -> str:
    """
    Very basic HTML→text conversion: strip tags and collapse whitespace.
    You can swap in html2text or BeautifulSoup later if needed.
    """
    # strip tags
    text = re.sub(r"<[^>]+>", "", html)
    # collapse multiple spaces/newlines
    text = re.sub(r"\s+", " ", text).strip()
    return text