# src/email_summarizer/orchestrator.py

import threading
import queue
import logging

from .fetcher         import fetch_emails
from .parser          import parse_email
from .classifier      import classify
from .summarizer      import summarize
from .utils           import compute_response_times
from .contact_manager import upsert_contact

# Configure logging to show INFO messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# Default number of worker threads; override from CLI
WORKER_COUNT = 4


def receiver(in_q: queue.Queue, fetch_count: int):
    """
    Receiver thread: fetches 'fetch_count' raw email threads and enqueues them.
    Each item is a list of raw MIME strings (one per message).
    """
    for raw_thread in fetch_emails(thread_count=fetch_count):
        in_q.put(raw_thread)
    # Signal shutdown to workers
    for _ in range(WORKER_COUNT):
        in_q.put(None)


def worker(in_q: queue.Queue, out_q: queue.Queue, me: str):
    """
    Worker thread: parse → compute reply times → summarize → classify →
                   upsert → enqueue results.
    """
    while True:
        raw_thread = in_q.get()
        if raw_thread is None:
            out_q.put(None)
            break

        try:
            # parse
            msgs = []
            for raw in raw_thread:
                msgs.extend(parse_email(raw))

            # reply-times
            reply_times = compute_response_times(msgs, me)

            # summarization & classification
            summary  = summarize(msgs)
            category = classify(summary)

            # upsert contact
            last = msgs[-1]
            contact = upsert_contact(
                name=           last.get("sender", ""),
                email=          last.get("sender", ""),
                signature_text= last.get("body", ""),
                subject=        last.get("subject", ""),
                body=           last.get("body", ""),
                to_addrs=       last.get("to", ""),
                cc_addrs=       last.get("cc", ""),
            )

            # hand off
            out_q.put({
                "contact_name":  contact.name,
                "contact_email": contact.email,
                "importance":    getattr(contact, "importance", None),
                "category":      category,
                "reply_times":   reply_times,
                "summary":       summary,
            })

        except Exception:
            logging.exception("Error processing thread")


def sender(out_q: queue.Queue):
    """
    Sender thread: consumes processed results and prints them.
    """
    done_signals = 0
    while True:
        item = out_q.get()
        if item is None:
            done_signals += 1
            if done_signals >= WORKER_COUNT:
                break
            continue

        # Display the full pipeline results for this thread
        print("=== THREAD RESULTS ===")
        print(f"Contact: {item['contact_name']} <{item['contact_email']}> | Importance: {item['importance']}")
        print(f"Category: {item['category']}")
        print("Reply Times:")
        for r in item["reply_times"]:
            hrs = r["delta"].total_seconds() / 3600
            print(f"  {r['reply_number']}. to {r['from']} — {hrs:.2f}h")
        print("\nAI Summary:\n", item["summary"], "\n")


def serve_multithreaded(me: str, fetch_count: int):
    """
    Orchestrates the multithreaded pipeline end-to-end.

    Args:
        me: Your email address for computing reply times.
        fetch_count: How many threads to fetch and process.
    """
    logging.info(f"Starting pipeline: fetching {fetch_count} threads with {WORKER_COUNT} workers…")
    in_q  = queue.Queue(maxsize=WORKER_COUNT * 2)
    out_q = queue.Queue(maxsize=WORKER_COUNT * 2)

    # Launch receiver thread (now passing fetch_count)
    threading.Thread(target=receiver, args=(in_q, fetch_count), daemon=True).start()

    # Launch worker threads
    for _ in range(WORKER_COUNT):
        threading.Thread(target=worker, args=(in_q, out_q, me), daemon=True).start()

    # Run sender in the foreground
    sender(out_q)