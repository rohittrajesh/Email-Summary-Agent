# src/email_summarizer/cli.py

import os
import sys
import base64
import click
from googleapiclient.errors import HttpError

from .fetcher    import fetch_thread_raw, fetch_message_raw
from .parser     import parse_email
from .summarizer import summarize
from .classifier import classify
from .utils      import compute_response_times, parsedate_to_datetime
from ._gmail_setup import service

@click.group()
def cli():
    """Email Summarizer & Classifier CLI."""
    pass


# ─── THREAD LISTING ─────────────────────────────────────────────────────────────

@cli.command("threads")
@click.option("-n", "--count", default=10, show_default=True,
              help="How many recent Gmail thread IDs to list.")
def list_threads_gmail(count):
    """List your most recent Gmail thread IDs."""
    threads_resp = service.users().threads().list(userId="me", maxResults=count).execute()
    for t in threads_resp.get("threads", []):
        click.echo(t["id"])


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


# ─── SUMMARIZE GMAIL ────────────────────────────────────────────────────────────

@cli.command("summarize-gmail")
@click.argument("thread_id")
def summarize_gmail(thread_id):
    """Fetch a Gmail thread by ID and AI-summarize it."""
    try:
        raws = fetch_thread_raw(thread_id)
    except HttpError:
        click.echo("Warning: not a thread ID—fetching as single message…")
        raws = [fetch_message_raw(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    click.echo(f"Fetched & parsed {len(msgs)} message(s).\n")
    click.echo("=== AI SUMMARY ===\n")
    click.echo(summarize(msgs))


# ─── GMAIL (alias for summarize+classify) ───────────────────────────────────────

@cli.command("gmail")
@click.argument("thread_id")
@click.option("--me", default=None, help="Your email address (for classification).")
def gmail(thread_id, me):
    """
    Summarize a Gmail thread and then classify it in one go.

    If you pass --me, we’ll label the summary based on your address.
    """
    # Reuse summarize-gmail under the hood:
    ctx = click.get_current_context()
    ctx.invoke(summarize_gmail, thread_id=thread_id)

    # Classification step:
    # We classify either on the summary text or on the full thread text—
    # here we’ll classify on the summary itself.
    summary_text = summarize(  # note: second call is cheap if we cached internally
        [m for r in fetch_thread_raw(thread_id) for m in parse_email(r)]
    )
    label = classify(summary_text)
    click.echo(f"\n=== ASSIGNED CATEGORY: {label} ===")


# ─── CLASSIFY SNIPPET ───────────────────────────────────────────────────────────

@cli.command("classify")
@click.argument("snippet")
def classify_snippet(snippet):
    """Classify a short text snippet into one of the pre-defined categories."""
    label = classify(snippet)
    click.echo(label)


@cli.command("classify-file")
@click.argument("path", type=click.Path(exists=True))
def classify_file(path):
    """Parse a .eml file and classify its body text."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    msgs = parse_email(raw)
    combined = "\n\n".join(f"{m['date']} – {m['sender']}: {m.get('body','')}" for m in msgs)
    click.echo(classify(combined))


@cli.command("classify-gmail")
@click.argument("thread_id")
def classify_gmail(thread_id):
    """Fetch a Gmail thread and classify the entire thread text."""
    try:
        raws = fetch_thread_raw(thread_id)
    except HttpError:
        click.echo("Warning: not a thread ID—fetching single message…")
        raws = [fetch_message_raw(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    combined = "\n\n".join(f"{m['date']} – {m['sender']}: {m.get('body','')}" for m in msgs)
    click.echo(classify(combined))


# ─── REPLY TIMES (GMAIL) ────────────────────────────────────────────────────────

@cli.command("reply-times-gmail")
@click.argument("thread_id")
@click.option("--me", required=True, help="Your own email address to measure replies.")
def reply_times_gmail(thread_id, me):
    """Fetch a Gmail thread and compute how long it took you to reply, each time."""
    try:
        raws = fetch_thread_raw(thread_id)
    except HttpError:
        click.echo("Warning: not a thread ID—fetching single message…")
        raws = [fetch_message_raw(thread_id)]

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
                f"{r['reply_number']}. reply to {r['from']} — "
                f"{hours:.2f} h (at {r['reply_at']:%Y-%m-%d %H:%M})"
            )


# ─── ENTRYPOINT ────────────────────────────────────────────────────────────────

def main():
    cli()


if __name__ == "__main__":
    sys.exit(main())