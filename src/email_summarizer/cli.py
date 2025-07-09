# src/email_summarizer/cli.py

import sys
import click
from googleapiclient.errors import HttpError
from email.utils       import parseaddr

from ._gmail_setup      import service
from .fetcher           import (
    fetch_thread_raw  as gmail_fetch_thread,
    fetch_message_raw as gmail_fetch_message,
)
from .outlook_fetcher   import (
    list_messages    as outlook_list_messages,
    get_message_raw  as outlook_fetch_message,
)
from .parser            import parse_email
from .summarizer        import summarize
from .classifier        import classify
from .utils             import compute_response_times, extract_signature_block
from .contact_manager   import upsert_contact


@click.group()
def cli():
    """Email Summarizer & Classifier CLI (Gmail or Outlook via device flow)."""
    pass


# ─── THREAD LISTING ─────────────────────────────────────────────────────────────

@cli.command("threads")
@click.option(
    "--provider",
    type=click.Choice(["gmail", "outlook"]),
    default="gmail",
    show_default=True,
    help="Which email provider to list thread/message IDs from."
)
@click.option(
    "-n", "--count",
    default=10,
    show_default=True,
    help="How many recent threads (Gmail) or messages (Outlook) to list."
)
def list_threads(provider, count):
    """List your most recent thread/message IDs."""
    if provider == "gmail":
        resp = service.users().threads().list(
            userId="me", maxResults=count
        ).execute()
        ids = [t["id"] for t in resp.get("threads", [])]
    else:
        msgs = outlook_list_messages(top=count)
        ids = [m["id"] for m in msgs]

    for tid in ids:
        click.echo(tid)


# ─── SUMMARIZE FILE ─────────────────────────────────────────────────────────────

@cli.command("summarize-file")
@click.argument("path", type=click.Path(exists=True))
def summarize_file(path):
    """Parse and summarize a local .eml file."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    msgs = parse_email(raw)
    click.echo(f"Parsed {len(msgs)} message(s).\n")
    click.echo("=== AI SUMMARY ===\n")
    click.echo(summarize(msgs))


# ─── SUMMARIZE THREAD/MESSAGE ───────────────────────────────────────────────────

@cli.command("summarize-thread")
@click.option(
    "--provider",
    type=click.Choice(["gmail", "outlook"]),
    default="gmail",
    show_default=True,
    help="Which email provider to fetch from."
)
@click.argument("thread_id")
def summarize_thread(provider, thread_id):
    """
    Fetch a Gmail thread or Outlook conversation/message and AI-summarize it.
    """
    if provider == "gmail":
        try:
            raws = gmail_fetch_thread(thread_id)
        except HttpError:
            click.echo("Warning: not a thread ID—fetching as single message…")
            raws = [gmail_fetch_message(thread_id)]
    else:
        try:
            metas = outlook_list_messages(
                top=50,
                filter_q=f"conversationId eq '{thread_id}'"
            )
            raws = [outlook_fetch_message(m["id"]) for m in metas]
        except Exception:
            click.echo("Warning: fetching single Outlook message…")
            raws = [outlook_fetch_message(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    click.echo(f"Fetched & parsed {len(msgs)} message(s).\n")
    click.echo("=== AI SUMMARY ===\n")
    click.echo(summarize(msgs))


# ─── SUMMARIZE + CLASSIFY + CONTACT-UPDATES ─────────────────────────────────────

@cli.command("process-thread")
@click.option(
    "--provider",
    type=click.Choice(["gmail", "outlook"]),
    default="gmail",
    show_default=True,
    help="Which email provider to fetch from."
)
@click.argument("thread_id")
@click.option(
    "--me",
    default=None,
    help="Your email address (for classification context)."
)
def process_thread(provider, thread_id, me):
    """
    Summarize a thread/message and then:
      1) extract & store contacts (Gmail only)
      2) classify the summary
    """
    # 1) Summarize
    ctx = click.get_current_context()
    ctx.invoke(summarize_thread, provider=provider, thread_id=thread_id)

    # 2) Fetch raw messages again
    if provider == "gmail":
        try:
            raws = gmail_fetch_thread(thread_id)
        except HttpError:
            raws = [gmail_fetch_message(thread_id)]
    else:
        try:
            metas = outlook_list_messages(
                top=50,
                filter_q=f"conversationId eq '{thread_id}'"
            )
            raws = [outlook_fetch_message(m["id"]) for m in metas]
        except Exception:
            raws = [outlook_fetch_message(thread_id)]

    # 3) Parse
    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    # 4) For Gmail: extract & upsert contacts
    if provider == "gmail":
        for msg in msgs:
            # parseaddr returns (display-name, email)
            name, email_addr = parseaddr(msg.get("sender", ""))
            signature = extract_signature_block(msg.get("body", ""))
            contact = upsert_contact(
                name        = name or "N/A",
                email       = email_addr or "N/A",
                signature_text = signature
            )
            click.echo(f"Saved contact: {contact.name} <{contact.email}>")

    # 5) Classify on the full summary
    label = classify(summarize(msgs))
    click.echo(f"\n=== ASSIGNED CATEGORY: {label} ===")


# ─── CLASSIFICATION ONLY ────────────────────────────────────────────────────────

@cli.command("classify-snippet")
@click.argument("snippet")
def classify_snippet(snippet):
    """Classify a short text snippet."""
    click.echo(classify(snippet))


@cli.command("classify-file")
@click.argument("path", type=click.Path(exists=True))
def classify_file(path):
    """Parse a .eml file and classify its body text."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    msgs = parse_email(raw)
    combined = "\n\n".join(
        f"{m['date']} – {m['sender']}: {m.get('body','')}"
        for m in msgs
    )
    click.echo(classify(combined))


@cli.command("classify-thread")
@click.option(
    "--provider",
    type=click.Choice(["gmail", "outlook"]),
    default="gmail",
    show_default=True,
    help="Which email provider to fetch from."
)
@click.argument("thread_id")
def classify_thread(provider, thread_id):
    """Fetch a thread/message and classify it."""
    if provider == "gmail":
        try:
            raws = gmail_fetch_thread(thread_id)
        except HttpError:
            click.echo("Warning: not a thread ID—fetching single message…")
            raws = [gmail_fetch_message(thread_id)]
    else:
        try:
            metas = outlook_list_messages(
                top=50,
                filter_q=f"conversationId eq '{thread_id}'"
            )
            raws = [outlook_fetch_message(m["id"]) for m in metas]
        except Exception:
            raws = [outlook_fetch_message(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    combined = "\n\n".join(
        f"{m['date']} – {m['sender']}: {m.get('body','')}"
        for m in msgs
    )
    click.echo(classify(combined))


# ─── REPLY TIMES ────────────────────────────────────────────────────────────────

@cli.command("reply-times")
@click.option(
    "--provider",
    type=click.Choice(["gmail", "outlook"]),
    default="gmail",
    show_default=True,
    help="Which email provider to fetch from."
)
@click.argument("thread_id")
@click.option(
    "--me",
    required=True,
    help="Your email address to measure replies."
)
def reply_times(provider, thread_id, me):
    """Compute how long it took you to reply in a thread/message."""
    if provider == "gmail":
        try:
            raws = gmail_fetch_thread(thread_id)
        except HttpError:
            click.echo("Warning: not a thread ID—fetching single message…")
            raws = [gmail_fetch_message(thread_id)]
    else:
        try:
            metas = outlook_list_messages(
                top=50,
                filter_q=f"conversationId eq '{thread_id}'"
            )
            raws = [outlook_fetch_message(m["id"]) for m in metas]
        except Exception:
            raws = [outlook_fetch_message(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    click.echo(f"Fetched & parsed {len(msgs)} message(s).\n")
    recs = compute_response_times(msgs, me)
    if not recs:
        click.echo(f"No replies by {me} found in this thread.")
    else:
        for r in recs:
            hours = r["delta"].total_seconds() / 3600
            click.echo(
                f"{r['reply_number']}. reply to {r['from']} — {hours:.2f} h "
                f"(at {r['reply_at']:%Y-%m-%d %H:%M})"
            )

@cli.command("list-contacts")
def list_contacts():
     """
     List all contacts we’ve upserted, including company/address/phone/title.
     """
     from sqlalchemy.orm import Session
     from .contact_manager import Contact, _engine

     with Session(_engine) as sess:
         for c in sess.query(Contact).order_by(Contact.name):
             click.echo(
                f"{c.name} <{c.email}>"
                f"{c.name} <{c.email}>  |  "
                f"Company: {c.company}  |  "
                f"Address: {c.address}  |  "
                f"Phone: {c.phone}  |  "
                f"Title: {c.job_title}"
             )


def main():
    cli()


if __name__ == "__main__":
    sys.exit(main())