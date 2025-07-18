#!/usr/bin/env python3
import os
import sys
import base64
import email as py_email
from email.parser import BytesParser
from email import policy
from email.utils import parsedate_to_datetime
from typing import List, Dict
import click
from dotenv import load_dotenv

load_dotenv()

from email_summarizer.fetcher    import fetch_threads, mark_as_read, RawEmail, RawThread
from email_summarizer.parser     import parse_email, ParsedEmail
from email_summarizer.summarizer import summarize
from email_summarizer.classifier import classify
from email_summarizer.utils      import extract_fields, compute_response_times
from email_summarizer.contact_manager import upsert_contact
import email_summarizer.service as service_module


@click.group()
def cli():
    """Email Summarizer & Classifier CLI."""
    pass


@cli.command()
def run():
    """Run the long-lived MailSynchronizer (blocking)."""
    # honor the WORKER_COUNT and POLL_INTERVAL env vars
    service_module.main()


@cli.command()
@click.option("--threads",     default=4, help="Worker count for LLM calls")
@click.option("--interval",    default=1.0, help="Poll interval in seconds")
def serve(threads: int, interval: float):
    """
    Run the MailSynchronizer in-process, setting WORKER_COUNT and POLL_INTERVAL.
    """
    os.environ["WORKER_COUNT"]   = str(threads)
    os.environ["POLL_INTERVAL"]  = str(interval)
    service_module.main()


@cli.command("threads")
@click.option("-n", "--count", default=5, help="How many unread threads to list")
def list_threads(count: int):
    """List your most recent unread Gmail thread IDs."""
    for t in fetch_threads(max_threads=count):
        click.echo(t.id)


# ─── Helpers for .eml file parsing ─────────────────────────────────────────────

def _load_rawemail_from_file(path: str) -> RawThread:
    """
    Wrap a single .eml on disk as a RawThread with one RawEmail.
    """
    raw_bytes = open(path, "rb").read()
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

    headers = {h: msg[h] for h in ("Date", "From", "Subject")}
    date    = headers.get("Date", "")
    sender  = headers.get("From", "")
    subject = headers.get("Subject", "")

    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                plain = part.get_payload(decode=True).decode(errors="ignore")
            elif ct == "text/html":
                html  = part.get_payload(decode=True).decode(errors="ignore")
    else:
        body = msg.get_payload(decode=True)
        text = body.decode(errors="ignore") if body else ""
        if msg.get_content_type() == "text/html":
            html  = text
        else:
            plain = text

    return RawThread(
        thread_id=os.path.basename(path),
        messages=[RawEmail(thread_id=os.path.basename(path),
                           msg_id=os.path.basename(path),
                           date=date, sender=sender,
                           subject=subject, plain=plain, html=html)]
    )


# ─── SUMMARIZE / CLASSIFY LOCAL .eml ──────────────────────────────────────────

@cli.command("summarize-file")
@click.argument("path", type=click.Path(exists=True))
def summarize_file(path: str):
    """Parse and AI-summarize a local .eml file."""
    rt = _load_rawemail_from_file(path)
    parsed = [parse_email(msg) for msg in rt.messages]
    valid  = [p for p in parsed if p.is_valid]
    cnt_skipped = len(parsed) - len(valid)
    click.echo(f"Parsed {len(parsed)} message(s), skipped {cnt_skipped} invalid.\n")

    msg_dicts = [
        {"date": p.date, "sender": p.sender, "body": p.plain or p.html}
        for p in valid
    ]
    summary = summarize(msg_dicts)
    click.echo("=== AI-GENERATED SUMMARY ===\n")
    click.echo(summary)


@cli.command("classify-file")
@click.argument("path", type=click.Path(exists=True))
def classify_file(path: str):
    """Parse a .eml file and classify its content."""
    rt = _load_rawemail_from_file(path)
    parsed = [parse_email(msg) for msg in rt.messages]
    valid  = [p for p in parsed if p.is_valid]
    msg_dicts = [
        {"date": p.date, "sender": p.sender, "body": p.plain or p.html}
        for p in valid
    ]
    label = classify(msg_dicts)
    click.echo(f"Assigned category: {label}")


# ─── SUMMARIZE / CLASSIFY THREAD ───────────────────────────────────────────────

@cli.command("summarize-thread")
@click.argument("thread_id")
def summarize_thread(thread_id: str):
    """Fetch & AI-summarize an unread Gmail thread."""
    for rt in fetch_threads(max_threads=20):
        if rt.id == thread_id:
            raw_thread = rt
            break
    else:
        click.echo(f"Thread {thread_id!r} not found.")
        return

    parsed = [parse_email(msg) for msg in raw_thread.messages]
    valid  = [p for p in parsed if p.is_valid]
    skipped = len(parsed) - len(valid)
    click.echo(f"Fetched {len(parsed)} msg(s), skipped {skipped} invalid.\n")

    msg_dicts = [
        {"date": p.date, "sender": p.sender, "body": p.plain or p.html}
        for p in valid
    ]
    summary = summarize(msg_dicts)
    click.echo("=== AI SUMMARY ===\n")
    click.echo(summary)
    category = classify(msg_dicts)
    click.echo(f"\n=== ASSIGNED CATEGORY ===\n{category}")


@cli.command("process-thread")
@click.argument("thread_id")
def process_thread(thread_id: str):
    """
    Summarize, classify & save contact info for the last message in a thread.
    """
    # Summarize & classify
    ctx = click.get_current_context()
    ctx.invoke(summarize_thread, thread_id=thread_id)

    # Re-fetch for contact upsert
    for rt in fetch_threads(max_threads=20):
        if rt.id == thread_id:
            raw_thread = rt
            break
    else:
        return

    parsed = [parse_email(msg) for msg in raw_thread.messages]
    valid  = [p for p in parsed if p.is_valid]
    if not valid:
        click.echo("No valid messages to upsert contact.")
        return

    last = valid[-1]
    contact = upsert_contact([p for p in parsed])
    click.echo(f"\nSaved contact: {contact.name} <{contact.email}>  (Importance: {contact.importance})")


# ─── REPLY TIMES ────────────────────────────────────────────────────────────────

@cli.command("reply-times")
@click.argument("thread_id")
@click.option("--me", required=True, help="Your email address for reply-time calc")
def reply_times(thread_id: str, me: str):
    """Compute how long it took you to reply in a thread."""
    for rt in fetch_threads(max_threads=20):
        if rt.id == thread_id:
            raw_thread = rt
            break
    else:
        click.echo(f"Thread {thread_id!r} not found.")
        return

    parsed = [parse_email(msg) for msg in raw_thread.messages]
    valid  = [p for p in parsed if p.is_valid]

    msg_dicts = [
        {"date": p.date, "sender": p.sender, "body": p.plain or p.html}
        for p in valid
    ]
    recs = compute_response_times(msg_dicts)
    if not recs:
        click.echo(f"No replies by {me} found.")
    else:
        for r in recs:
            hrs = r["delta_seconds"] / 3600
            click.echo(f"{r['reply_number']}. reply to {r['from']} — {hrs:.2f}h at {r['reply_at']}")


# ─── LIST SAVED CONTACTS ───────────────────────────────────────────────────────

@cli.command("list-contacts")
def list_contacts():
    """List all contacts saved in the database."""
    from email_summarizer.db import SessionLocal
    from email_summarizer.models import Contact

    sess = SessionLocal()
    for c in sess.query(Contact).all():
        click.echo(
            f"{c.name} <{c.email}> | {c.company} | {c.address} "
            f"| {c.phone} | {c.job_title} | Importance: {c.importance}"
        )
    sess.close()


if __name__ == "__main__":
    cli()