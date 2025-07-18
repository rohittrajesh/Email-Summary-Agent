# src/email_summarizer/contact_manager.py

import os
import json
from sqlalchemy import select
from .db        import SessionLocal
from .models    import Contact
import openai
from .utils     import extract_signature_block

# ─── OpenAI init ────────────────────────────────────────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in your environment")
openai.api_key = OPENAI_KEY


def parse_signature_with_ai(sig_text: str) -> dict:
    """
    Ask the model to extract: name, company, address, phone, job_title.
    Returns a dict with those keys.
    """
    system = (
        "You are a parser that extracts contact signature info. "
        "Given a signature block from an email, reply ONLY with a JSON object "
        "with the keys: name, company, address, phone, job_title. "
        "If any field is not present, set its value to \"N/A\"."
    )
    user = f"Signature text:\n```\n{sig_text}\n```"

    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.0,
    )
    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        data = {k: "N/A" for k in ("name","company","address","phone","job_title")}

    return {k: data.get(k, "N/A") or "N/A"
            for k in ("name","company","address","phone","job_title")}


def classify_importance_with_ai(
    sender:  str,
    subject: str,
    body:    str,
    to_addrs:str,
    cc_addrs:str
) -> str:
    """
    Ask the model: is this email HIGHLY IMPORTANT or LESS IMPORTANT?
    """
    system = (
        "You are an email‐importance classifier. "
        "Given the sender, subject line, body, To and Cc headers, "
        "decide whether this message is 'HIGHLY IMPORTANT' or 'LESS IMPORTANT'. "
        "Reply with exactly one of those two."
    )
    user = (
        f"Sender: {sender}\n"
        f"Subject: {subject}\n"
        f"To: {to_addrs}\n"
        f"Cc: {cc_addrs}\n\n"
        f"Body:\n```\n{body}\n```"
    )
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system", "content": system},
            {"role":"user",   "content": user},
        ],
        temperature=0.0,
    )
    ans = resp.choices[0].message.content.strip()
    return ans if ans in {"HIGHLY IMPORTANT","LESS IMPORTANT"} else "LESS IMPORTANT"


def upsert_contact(parsed):
    """
    Given a ParsedEmail instance or list thereof, extract a signature snippet,
    classify importance, then insert or update a Contact.
    """
    # pick the last message in the thread (or the only one)
    last = parsed[-1] if isinstance(parsed, (list, tuple)) else parsed

    # 1) pull out just the signature block (or final lines) from plain/html
    raw_sig = (getattr(last, "plain", "") or getattr(last, "html", "") or "")
    sig_text = extract_signature_block(raw_sig)

    # 2) truncate to ~2k chars to stay under context limits
    if len(sig_text) > 2000:
        sig_text = sig_text[-2000:]

    sig_details = parse_signature_with_ai(sig_text)

    # 3) classify importance on that same snippet
    importance  = classify_importance_with_ai(
        sender=   last.sender,
        subject=  last.subject,
        body=     sig_text,
        to_addrs= getattr(last, "to", ""),
        cc_addrs=getattr(last, "cc", ""),
    )

    # 4) assemble upsert details
    details = {
        "name":       sig_details["name"],
        "email":      last.sender,
        "company":    sig_details["company"],
        "address":    sig_details["address"],
        "phone":      sig_details["phone"],
        "job_title":  sig_details["job_title"],
        "importance": importance,
    }

    # 5) insert or update the contacts table
    session = SessionLocal()
    try:
        existing = session.scalar(
            select(Contact).where(Contact.email == details["email"])
        )
        if existing:
            for k, v in details.items():
                setattr(existing, k, v)
            contact = existing
        else:
            contact = Contact(**details)
            session.add(contact)

        session.commit()
        session.refresh(contact)
    finally:
        session.close()

    return contact