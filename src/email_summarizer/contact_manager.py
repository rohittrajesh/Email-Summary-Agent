import os
import json
from sqlalchemy import (
    Column, Integer, String, create_engine, select
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
import openai

Base = declarative_base()

class Contact(Base):
    __tablename__ = "contacts"

    id          = Column(Integer, primary_key=True)
    name        = Column(String,  nullable=False)
    email       = Column(String,  nullable=False, unique=True)
    company     = Column(String,  default="N/A")
    address     = Column(String,  default="N/A")
    phone       = Column(String,  default="N/A")            # ← added
    job_title   = Column(String,  default="N/A")
    importance  = Column(
        String,
        default="LESS IMPORTANT",
        nullable=False,
        doc="‘HIGHLY IMPORTANT’ or ‘LESS IMPORTANT’"
    )

_engine = create_engine("sqlite:///contacts.db", echo=False)
Base.metadata.create_all(_engine)

# ─── OpenAI init ────────────────────────────────────────────────────────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in your environment")
openai.api_key = OPENAI_KEY

# ─── AI helpers ─────────────────────────────────────────────────────────────────

def parse_signature_with_ai(sig_text: str) -> dict:
    """
    Ask the model to extract: name, company, address, phone, job_title.
    Returns a dict with those keys (values or "N/A").
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
            {"role": "system",  "content": system},
            {"role": "user",    "content": user},
        ],
        temperature=0.0,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
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
    Return exactly one of those two strings.
    """
    system = (
        "You are an email‐importance classifier. "
        "Given the sender, subject line, body, To and Cc headers, "
        "decide whether this message is 'HIGHLY IMPORTANT' or 'LESS IMPORTANT'. "
        "You must reply with exactly one of those two."
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
            {"role":"user",   "content": user}
        ],
        temperature=0.0,
    )
    ans = resp.choices[0].message.content.strip()
    return ans if ans in {"HIGHLY IMPORTANT","LESS IMPORTANT"} else "LESS IMPORTANT"


def upsert_contact(
    name:           str,
    email:          str,
    signature_text: str,
    subject:        str,
    body:           str,
    to_addrs:       str,
    cc_addrs:       str
) -> Contact:
    """
    1) Parse the signature fields via AI
    2) Classify importance via AI
    3) Insert or update the Contact record
    """
    sig_text = signature_text or ""
    if not sig_text.strip():
        sig_text = body
    sig_details = parse_signature_with_ai(signature_text)
    importance  = classify_importance_with_ai(
        sender=   email,
        subject=  subject,
        body=     body,
        to_addrs= to_addrs,
        cc_addrs= cc_addrs,
    )

    details = {
        "name":       name  or sig_details["name"]   or "N/A",
        "email":      email or "N/A",
        "company":    sig_details["company"],
        "address":    sig_details["address"],
        "phone":      sig_details["phone"],
        "job_title":  sig_details["job_title"],
        "importance": importance,
    }

    with Session(_engine) as sess:
        stmt     = select(Contact).where(Contact.email == details["email"])
        existing = sess.scalars(stmt).first()

        if existing:
            for k,v in details.items():
                setattr(existing, k, v)
            contact = existing
        else:
            contact = Contact(**details)
            sess.add(contact)

        sess.commit()
        sess.refresh(contact)

    return contact