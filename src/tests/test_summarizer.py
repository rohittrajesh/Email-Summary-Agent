# src/tests/test_summarizer.py

import pytest
from email_summarizer.summarizer import summarize, client

def test_summarize_empty():
    """Empty‐thread guard returns an empty string."""
    assert summarize([]) == ""

def test_summarize_nonempty(monkeypatch):
    """
    Given a list of parsed messages, summarize() should call the API
    and return the AI’s reply.
    """
    # 1) Create a _parsed_ thread: list of dicts with date, sender, body
    sample_msgs = [
        {
            "date": "Fri, 4 Jul 2025 18:51:32 +0900",
            "sender": "Rohit Aryan Rajesh <rohitaryan296@gmail.com>",
            "body": "Hello,\n\nPlease find the link to the Github repository below which contains my code for the OCR Comparison project."
        },
        # you can add more dicts here if you want to simulate multiple messages
    ]

    # 2) Stub out the API response
    class DummyMessage:
        def __init__(self, content):
            self.content = content

    class DummyChoice:
        def __init__(self, message):
            self.message = message

    class DummyResponse:
        def __init__(self, text):
            self.choices = [DummyChoice(DummyMessage(text))]

    def fake_create(*, model, messages, temperature):
        # Optionally inspect `messages` here to assert that your prompt was built correctly
        return DummyResponse("This is a test summary.")

    monkeypatch.setattr(
        client.chat.completions,
        "create",
        fake_create
    )

    # 3) Call summarize() and verify the stubbed reply comes back
    summary = summarize(sample_msgs)
    assert summary == "This is a test summary."