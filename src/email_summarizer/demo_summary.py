#!/usr/bin/env python3
import os
import sys
import argparse

# ─── Make “src/” importable ────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# ─── Load .env for OPENAI_API_KEY and IMAP_USER ───────────────────────────────
from dotenv import load_dotenv
load_dotenv()

from googleapiclient.errors import HttpError

from email_summarizer.fetcher    import fetch_threads
from email_summarizer.parser     import parse_email, ParsedEmail
from email_summarizer.summarizer import summarize
from email_summarizer.classifier import classify

def list_threads(count: int):
    print(f"Recent {count} unread threads:")
    for t in fetch_threads(max_threads=count):
        print(" ", t.id)

def do_gmail(thread_id: str):
    # Fetch up to 20 threads and look for a match
    for raw_thread in fetch_threads(max_threads=20):
        if raw_thread.id == thread_id:
            break
    else:
        print(f"Thread {thread_id!r} not found among the most recent 20.")
        return

    # Parse and validate each message
    parsed = [parse_email(msg) for msg in raw_thread.messages]
    valid   = [p for p in parsed if p.is_valid]
    skipped = [p for p in parsed if not p.is_valid]

    print(f"Fetched {len(parsed)} message(s), {len(skipped)} skipped.\n")

    # Build the list-of-dicts for summarization/classification
    msg_dicts = [
        {"date":   p.date,
         "sender": p.sender,
         "body":   p.plain or p.html}
        for p in valid
    ]

    # AI Summary
    summary = summarize(msg_dicts)
    print("=== AI-GENERATED SUMMARY ===\n")
    print(summary, "\n")

    # Category
    category = classify(msg_dicts)
    print("=== ASSIGNED CATEGORY ===\n")
    print(category)

def main():
    parser = argparse.ArgumentParser(
        description="Email Thread Summarizer & Classifier CLI"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("threads", help="List your recent unread thread IDs")
    p1.add_argument(
        "-n", "--count", type=int, default=5,
        help="How many threads to list (default: 5)"
    )

    p2 = sub.add_parser("gmail", help="Fetch, summarize & classify a Gmail thread")
    p2.add_argument("thread_id", help="Gmail thread ID")

    args = parser.parse_args()

    if args.cmd == "threads":
        list_threads(args.count)
    elif args.cmd == "gmail":
        do_gmail(args.thread_id)

if __name__ == "__main__":
    main()