# src/tests/test_classifier.py

import pytest
from email_summarizer.classifier import classify, client

def test_classify_empty():
    assert classify("") == "Others"
    assert classify("   ") == "Others"

def test_classify_monkeypatched(monkeypatch):
    # Stub out the API
    class DummyMessage:
        def __init__(self, content):
            self.content = content

    class DummyChoice:
        def __init__(self, msg):
            self.message = msg

    class DummyResponse:
        def __init__(self, text):
            self.choices = [DummyChoice(DummyMessage(text))]

    def fake_create(*, model, messages, temperature):
        # You could assert on messages[0]['content'] here if you like
        return DummyResponse("Invoice/Tax")

    monkeypatch.setattr(
        client.chat.completions,
        "create",
        fake_create
    )

    result = classify("Here is my invoice. Please update billing.")
    assert result == "Invoice/Tax"