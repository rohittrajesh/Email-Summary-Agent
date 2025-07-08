# src/backend/classifier.py

import os
from typing import List
from dotenv import load_dotenv
from openai import OpenAI

# 1) Load your .env (must contain OPENAI_API_KEY)
load_dotenv()

# 2) Instantiate the OpenAI client
client = OpenAI()

# 3) Your category set
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
    Classify the given text into one of CATEGORIES via an LLM call.
    """
    # 1) Empty‐text guard
    if not text or not text.strip():
        return "Others"

    # 2) Build the prompt
    prompt = (
        "Please classify the following content into exactly one of these categories:\n"
        f"{', '.join(CATEGORIES)}\n\n"
        f"Content:\n{text}\n\n"
        "Respond with the single category name only."
    )

    # 3) Call the API
    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    # 4) Extract and clean up the response
    label = resp.choices[0].message.content.strip()
    # Sometimes the model returns quotes or extra whitespace—sanitize:
    return label.strip('"').strip("'").strip()
