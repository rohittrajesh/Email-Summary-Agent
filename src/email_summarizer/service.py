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
from .parser          import parse_email, ParsedEmail
from .utils           import extract_fields, compute_response_times
from .summarizer      import summarize
from .classifier      import classify
from .contact_manager import upsert_contact


LOG           = logging.getLogger(__name__)
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))
WORKERS       = int(os.getenv("WORKER_COUNT",   "4"))
MAX_THREADS   = int(os.getenv("MAX_THREADS",    "10"))


def process_thread(raw_thread):
    session = SessionLocal()
    thread_rec = None

    try:
        # 0) skip if we already saw this thread
        if session.query(Mail).filter_by(message_id=raw_thread.id).first():
            return

        # 1) create the Mail record
        thread_rec = Mail(
            message_id=raw_thread.id,
            sender    = raw_thread.messages[0].sender,
            subject   = raw_thread.messages[0].subject,
            body_plain= raw_thread.messages[0].plain,
            body_html = raw_thread.messages[0].html,
            status    = "pending",
        )
        session.add(thread_rec)
        session.commit()

        # 2) parse every message
        parsed: list[ParsedEmail] = []
        for raw_msg in raw_thread.messages:
            parsed.append(parse_email(raw_msg))

        # 3) record skips
        for p in parsed:
            if not p.is_valid:
                session.add(SkippedMail(
                    mail_id = thread_rec.id,
                    reason  = p.validation_error
                ))
        session.commit()

        # 4) extract structured fields
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

        # 5) build the dicts for summarization/classification
        msg_dicts = []
        for p in parsed:
            if not p.is_valid:
                continue
            msg_dicts.append({
                "date":   p.date,
                "sender": p.sender,
                "body":   p.plain or p.html
            })

        # 6) summarize, classify, compute reply times
        thread_rec.summary        = summarize(msg_dicts)
        thread_rec.category       = classify(thread_rec.summary)
        thread_rec.response_times = compute_response_times(msg_dicts)
        session.commit()

        # 7) upsert contact
        upsert_contact(parsed)

        # 8) mark success
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
        # 9) ack all messages so they won’t return as UNREAD
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
