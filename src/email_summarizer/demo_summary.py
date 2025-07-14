#!/usr/bin/env python3
import os
import sys
import argparse

# ─── Make “src/” importable ────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# ─── Load .env for OPENAI_API_KEY ─────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ─── Bring in our modules ─────────────────────────────────────────────────────
from googleapiclient.errors import HttpError

from email_summarizer.parser     import parse_email
from email_summarizer.summarizer import summarize
from email_summarizer.classifier import classify
from email_summarizer.fetcher    import (
    fetch_thread_raw,
    fetch_message_raw,
    list_recent_threads
)

def do_summarize(path: str):
    raw = open(path, encoding="utf-8").read()
    msgs = parse_email(raw)
    print(f"Parsed {len(msgs)} message(s).\n")
    summary = summarize(msgs)
    print("=== AI-GENERATED SUMMARY ===\n")
    print(summary)
    return summary

def do_classify(text: str):
    label = classify(text)
    print(f"\n=== ASSIGNED CATEGORY: {label} ===")

def do_gmail(thread_or_msg_id: str):
    # Try thread first; if that fails, fall back to single message
    try:
        raw = fetch_thread_raw(thread_or_msg_id)
    except HttpError:
        print("Warning: not a thread ID—fetching as a single message…")
        raw = fetch_message_raw(thread_or_msg_id)

    msgs = parse_email(raw)
    print(f"Fetched & parsed {len(msgs)} message(s).\n")
    summary = summarize(msgs)
    print("=== AI SUMMARY ===\n")
    print(summary, "\n")
    do_classify(summary)

def do_threads(count: int):
    ids = list_recent_threads(count)
    print(f"Recent {count} thread IDs:")
    for tid in ids:
        print(" ", tid)

def main():
    parser = argparse.ArgumentParser(
        description="Email Summarizer & Classifier CLI"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("summarize", help="Summarize a raw .eml file")
    p1.add_argument("file", help="Path to a raw email (.eml) file")

    p2 = sub.add_parser("classify", help="Summarize + classify a raw .eml file")
    p2.add_argument("file", help="Path to a raw email (.eml) file")

    p3 = sub.add_parser("gmail", help="Fetch, summarize & classify by Gmail ID")
    p3.add_argument("thread_id", help="Gmail thread ID or message ID")

    p4 = sub.add_parser("threads", help="List your recent Gmail thread IDs")
    p4.add_argument(
        "-n", "--count", type=int, default=5,
        help="How many recent thread IDs to show (default: 5)"
    )

    args = parser.parse_args()

    if args.cmd == "summarize":
        do_summarize(args.file)
    elif args.cmd == "classify":
        summary = do_summarize(args.file)
        do_classify(summary)
    elif args.cmd == "gmail":
        do_gmail(args.thread_id)
    elif args.cmd == "threads":
        do_threads(args.count)

if __name__ == "__main__":
    main()