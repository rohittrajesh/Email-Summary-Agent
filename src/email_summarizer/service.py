#!/usr/bin/env python3
# src/email_summarizer/service.py

import os
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor, as_completed

from .db              import init_db, SessionLocal
from .models          import Mail, SkippedMail, MailContent
from .fetcher         import fetch_threads, mark_as_read
from .parser          import parse_email
from .utils           import extract_fields, compute_response_times
from .summarizer      import summarize
from .classifier      import classify
from .contact_manager import upsert_contact

LOG           = logging.getLogger(__name__)
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))
WORKERS       = int(os.getenv("WORKER_COUNT",   "4"))
MAX_THREADS   = int(os.getenv("MAX_THREADS",    "10"))


def process_thread(raw_thread):
    """
    Full pipeline for a single new thread:
      • Insert Mail record
      • Parse each message
      • Record any SkippedMail
      • Extract tabular fields into MailContent
      • Summarize, classify, compute response times
      • Upsert contact info
      • Mark it COMPLETED (or FAILED, if anything blew up)
      • Finally: mark each message READ so Gmail won’t give it again
    """
    session = SessionLocal()
    thread_rec = None

    try:
        # 1) Skip if somehow already in the database
        if session.query(Mail).filter_by(message_id=raw_thread.id).first():
            return

        # 2) Create the Mail row
        last = raw_thread.messages[-1]
        thread_rec = Mail(
            message_id = raw_thread.id,
            sender     = last.sender,
            subject    = last.subject,
            body_plain = last.plain,
            body_html  = last.html,
            status     = "pending",
        )
        session.add(thread_rec)
        session.commit()
        session.refresh(thread_rec)

        # 3) Parse every message
        parsed = []
        for msg in raw_thread.messages:
            # parse_email expects the full raw text of one message;
            # if you only have plain/html, you may need to tweak this.
            # Here we assume parse_email can consume plain text ok:
            parsed.extend(parse_email(msg.plain or msg.html))

        # 4) Record any invalid-message skips
        for p in parsed:
            if not p.is_valid:
                session.add(SkippedMail(
                    mail_id = thread_rec.id,
                    reason  = p.validation_error
                ))
        session.commit()

        # 5) Extract table fields from valid messages
        for p in parsed:
            if not p.is_valid:
                continue
            for f in extract_fields(p):
                session.add(MailContent(
                    mail_id = thread_rec.id,
                    name    = f["name"],
                    value   = f["value"],
                    message = f.get("message", "")
                ))
        session.commit()

        # 6) Summarize, classify, compute reply times
        msg_dicts = []
        for p in parsed:
            if p.is_valid:
                msg_dicts.append({
                    "date":   p.date,
                    "sender": p.sender,
                    "body":   (p.plain or p.html or "")
                })

        thread_rec.summary        = summarize(msg_dicts)
        thread_rec.category       = classify(msg_dicts)
        thread_rec.response_times = compute_response_times(msg_dicts)
        session.commit()

        # 7) Upsert the sender as a Contact
        upsert_contact(parsed)

        # 8) Mark success
        thread_rec.status = "completed"
        session.commit()

    except Exception as e:
        session.rollback()
        LOG.exception("Error processing thread %s", raw_thread.id)
        if thread_rec:
            thread_rec.status         = "failed"
            thread_rec.failure_reason = str(e)
            session.add(thread_rec)
            session.commit()

    finally:
        session.close()
        # 9) Acknowledge (mark READ) so Gmail won’t return it again
        for m in raw_thread.messages:
            try:
                mark_as_read(m)
            except Exception:
                pass


def main():
    logging.basicConfig(level=logging.INFO)
    init_db()

    # Record the moment we started: anything before this is “old” and never touched.
    start_dt = datetime.now(timezone.utc)
    LOG.info(
        "MailSynchronizer starting at %s UTC — will only process threads whose last message arrives after this point",
        start_dt.isoformat()
    )

    seen_threads = set()

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = set()

        while True:
            # 1) Fetch up to MAX_THREADS *unread* threads, sorted by recency
            for raw in fetch_threads(MAX_THREADS):
                if raw.id in seen_threads:
                    # we’ve already either processed it or explicitly skipped it
                    continue
                seen_threads.add(raw.id)

                # parse the timestamp of the **last** message in this thread
                try:
                    dt = parsedate_to_datetime(raw.messages[-1].date)
                    dt_utc = dt.astimezone(timezone.utc)
                except Exception:
                    # if we can’t parse its date, skip it too
                    continue

                # ignore anything before startup
                if dt_utc < start_dt:
                    continue

                # schedule it for full processing
                futures.add(pool.submit(process_thread, raw))

            # 2) wait up to POLL_INTERVAL seconds for any to finish
            try:
                for _ in as_completed(futures, timeout=POLL_INTERVAL):
                    pass
            except concurrent.futures.TimeoutError:
                pass

            # 3) drop the done ones, keep the rest
            futures = {f for f in futures if not f.done()}


if __name__ == "__main__":
    main()
