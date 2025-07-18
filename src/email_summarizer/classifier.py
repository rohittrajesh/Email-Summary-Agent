# src/email_summarizer/classifier.py

import os
from typing import List
from dotenv import load_dotenv
import openai

# ─── Load API Key ───────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("Please set OPENAI_API_KEY in your environment")

# ─── Your business categories ────────────────────────────────────────────────────
CATEGORIES: List[str] = [
    "Quotation",
    "Order Management",
    "Delivery",
    "Invoice/Tax",
    "Quality Control",
    "Technical Support",
    "Others"
]

def classify(text: str) -> str:
    """
    Classify the given text into exactly one of CATEGORIES via an LLM call.
    Returns just the category name.
    """
    # empty‐text guard
    if not text or not text.strip():
        return "Others"

    prompt = (
        "Please classify the following content into exactly one of these categories:\n"
        f"{', '.join(CATEGORIES)}\n\n"
        f"Content:\n{text}\n\n"
        "Respond with the single category name only."
    )

    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role":"user", "content":prompt}],
        temperature=0.0,
    )

    # sanitize model output
    label = resp.choices[0].message.content.strip()
    return label.strip('"').strip("'").strip()
