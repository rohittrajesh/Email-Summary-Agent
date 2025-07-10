# src/email_summarizer/parser.py

import re
import email
from email import policy
from email.parser import BytesParser
from typing import List, Dict
from html import unescape

def _get_body(msg: email.message.Message) -> str:
    # (unchanged)
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="ignore").strip()
                except Exception:
                    continue
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    html = payload.decode(charset, errors="ignore")
                    text = re.sub(r"<[^>]+>", "", html)
                    return unescape(text).strip()
                except Exception:
                    continue
        return ""
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
    Given one full raw MIME string, return a single‐element list with:
      date, sender, subject, to, cc, body
    """
    msg = BytesParser(policy=policy.default).parsebytes(
        raw.encode("utf-8", errors="ignore")
    )
    return [{
        "date":    msg["Date"]    or "",
        "sender":  msg["From"]    or "",
        "subject": msg["Subject"] or "",
        "to":      msg.get("To", "")  or "",
        "cc":      msg.get("Cc", "")  or "",
        "body":    _get_body(msg),
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