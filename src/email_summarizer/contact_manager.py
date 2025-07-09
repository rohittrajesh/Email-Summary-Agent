# src/email_summarizer/contact_manager.py

import os, re, json
from sqlalchemy import (
    Column, Integer, String, create_engine, select
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
import openai

# ─── Database setup (unchanged) ────────────────────────────────────────────────

Base = declarative_base()

class Contact(Base):
    __tablename__ = "contacts"
    id        = Column(Integer, primary_key=True)
    name      = Column(String, nullable=False)
    email     = Column(String, nullable=False, unique=True)
    company   = Column(String, default="N/A")
    address   = Column(String, default="N/A")
    phone     = Column(String, default="N/A")
    job_title = Column(String, default="N/A")

_engine = create_engine("sqlite:///contacts.db", echo=False)
Base.metadata.create_all(_engine)

# ─── OpenAI client init ────────────────────────────────────────────────────────

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in your environment")
openai.api_key = OPENAI_KEY

# ─── AI‐powered signature parser ────────────────────────────────────────────────

def parse_signature_with_ai(sig_text: str) -> dict:
    """
    Ask the model to extract: name, company, address, phone, job_title
    from a free-form signature block, returning a JSON dict.
    """
    system = (
        "You are a parser that extracts contact signature info. "
        "Given a signature block from an email, reply ONLY with a JSON object "
        "with the keys: name, company, address, phone, job_title. "
        "If any field is not present, set its value to \"N/A\"."
    )
    user = f"Signature text:\n```\n{sig_text}\n```"

    # <<< UPDATED to the new v1.0+ SDK interface >>>
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.0,
    )

    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {k: "N/A" for k in ("name","company","address","phone","job_title")}
    return {k: data.get(k, "N/A") or "N/A" for k in data}


# ─── Upsert contact (with AI) ──────────────────────────────────────────────────

def upsert_contact(name: str, email: str, signature_text: str) -> Contact:
    """
    Insert or update a Contact. Uses the AI to parse the signature.
    If the AI fails or mis-formats, we default back to N/A.
    """
    # 1) Let the model parse the signature
    details = parse_signature_with_ai(signature_text)

    # 2) Override name & email from headers
    details["name"]  = name or details["name"] or "N/A"
    details["email"] = email or "N/A"

    # 3) Write into the SQLite DB
    with Session(_engine) as sess:
        stmt = select(Contact).where(Contact.email == details["email"])
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