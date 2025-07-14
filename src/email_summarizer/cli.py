import sys
import click
from googleapiclient.errors import HttpError

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
from .utils             import compute_response_times
from .contact_manager   import upsert_contact, Contact, _engine
from .demo_summary      import main as run_sequential
from . import orchestrator

@click.group()
def cli():
    """Email Summarizer & Classifier CLI (Gmail or Outlook)."""
    pass

@cli.command()
def run():
    """Legacy (single-threaded) processor."""
    run_sequential()

@cli.command()
@click.option("--threads",     default=4,  help="Number of LLM worker threads")
@click.option("--fetch-count", default=5,  help="How many email threads to fetch")
@click.option("--me",          required=True, help="Your email address (for reply-time calc)")
def serve(threads, fetch_count, me):
    """Run the multithreaded email pipeline."""
    orchestrator.WORKER_COUNT = threads
    orchestrator.serve_multithreaded(me, fetch_count)

# ─── THREAD LISTING ─────────────────────────────────────────────────────────────

@cli.command("threads")
@click.option("--provider", type=click.Choice(["gmail", "outlook"]), default="gmail", show_default=True)
@click.option("-n", "--count", default=10, show_default=True)
def list_threads(provider, count):
    """List your most recent thread/message IDs."""
    if provider == "gmail":
        resp = service.users().threads().list(userId="me", maxResults=count).execute()
        ids  = [t["id"] for t in resp.get("threads", [])]
    else:
        msgs = outlook_list_messages(top=count)
        ids  = [m["id"] for m in msgs]
    for tid in ids:
        click.echo(tid)

# ─── SUMMARIZE FILE ─────────────────────────────────────────────────────────────

@cli.command("summarize-file")
@click.argument("path", type=click.Path(exists=True))
def summarize_file(path):
    """Parse and summarize a local .eml file."""
    raw  = open(path, encoding="utf-8", errors="replace").read()
    msgs = parse_email(raw)
    click.echo(f"Parsed {len(msgs)} message(s).\n")
    click.echo("=== AI SUMMARY ===\n")
    click.echo(summarize(msgs))

# ─── SUMMARIZE THREAD ────────────────────────────────────────────────────────────

@cli.command("summarize-thread")
@click.option("--provider", type=click.Choice(["gmail","outlook"]), default="gmail", show_default=True)
@click.argument("thread_id")
def summarize_thread(provider, thread_id):
    """Fetch & AI‐summarize a Gmail thread or Outlook conversation."""
    if provider == "gmail":
        try:
            raws = gmail_fetch_thread(thread_id)
        except HttpError:
            click.echo("Warning: not a thread ID—fetching single message…")
            raws = [gmail_fetch_message(thread_id)]
    else:
        try:
            metas = outlook_list_messages(top=50, filter_q=f"conversationId eq '{thread_id}'")
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

# ─── PROCESS (SUMMARIZE + CLASSIFY + SAVE CONTACT) ───────────────────────────────

@cli.command("process-thread")
@click.option("--provider", type=click.Choice(["gmail","outlook"]), default="gmail", show_default=True)
@click.argument("thread_id")
@click.option("--me", default=None, help="Your email address (for classification context).")
def process_thread(provider, thread_id, me):
    """
    Summarize + classify + save the *sender* of the last message in this thread.
    """
    # first summary
    ctx = click.get_current_context()
    ctx.invoke(summarize_thread, provider=provider, thread_id=thread_id)

    # fetch raw again
    if provider == "gmail":
        try:
            raws = gmail_fetch_thread(thread_id)
        except HttpError:
            raws = [gmail_fetch_message(thread_id)]
    else:
        try:
            metas = outlook_list_messages(top=50, filter_q=f"conversationId eq '{thread_id}'")
            raws = [outlook_fetch_message(m["id"]) for m in metas]
        except Exception:
            raws = [outlook_fetch_message(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    # last message = msgs[-1]
    last = msgs[-1]
    contact = upsert_contact(
        name=           last.get("sender",""),
        email=          last.get("sender",""),
        signature_text= last.get("body",""),
        subject=        last.get("subject",""),
        body=           last.get("body",""),
        to_addrs=       last.get("to",""),
        cc_addrs=       last.get("cc",""),
    )
    click.echo(f"Saved contact: {contact.name} <{contact.email}>  (Importance: {contact.importance})")

    # then classification
    label = classify(summarize(msgs))
    click.echo(f"\n=== ASSIGNED CATEGORY: {label} ===")

# ─── CLASSIFY SNIPPET ───────────────────────────────────────────────────────────

@cli.command("classify-snippet")
@click.argument("snippet")
def classify_snippet(snippet):
    """Classify a short text snippet."""
    click.echo(classify(snippet))

@cli.command("classify-file")
@click.argument("path", type=click.Path(exists=True))
def classify_file(path):
    """Parse a .eml file and classify its body text."""
    raw  = open(path, encoding="utf-8", errors="replace").read()
    msgs = parse_email(raw)
    combined = "\n\n".join(f"{m['date']} – {m['sender']}: {m.get('body','')}" for m in msgs)
    click.echo(classify(combined))

@cli.command("classify-thread")
@click.option("--provider", type=click.Choice(["gmail","outlook"]), default="gmail", show_default=True)
@click.argument("thread_id")
def classify_thread(provider, thread_id):
    """Fetch a thread/message and classify the entire text."""
    if provider == "gmail":
        try:
            raws = gmail_fetch_thread(thread_id)
        except HttpError:
            click.echo("Warning: not a thread ID—fetching single message…")
            raws = [gmail_fetch_message(thread_id)]
    else:
        try:
            metas = outlook_list_messages(top=50, filter_q=f"conversationId eq '{thread_id}'")
            raws = [outlook_fetch_message(m["id"]) for m in metas]
        except Exception:
            raws = [outlook_fetch_message(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    combined = "\n\n".join(f"{m['date']} – {m['sender']}: {m.get('body','')}" for m in msgs)
    click.echo(classify(combined))

# ─── REPLY TIMES ────────────────────────────────────────────────────────────────

@cli.command("reply-times")
@click.argument("thread_id")
@click.option("--me", required=True, help="Your email address to measure replies.")
def reply_times(thread_id, me):
    """Compute how long it took you to reply in a thread/message."""
    try:
        raws = gmail_fetch_thread(thread_id)
    except HttpError:
        click.echo("Warning: not a thread ID—fetching single message…")
        raws = [gmail_fetch_message(thread_id)]

    msgs = []
    for r in raws:
        msgs.extend(parse_email(r))

    click.echo(f"Fetched & parsed {len(msgs)} message(s).\n")
    recs = compute_response_times(msgs, me)
    if not recs:
        click.echo(f"No replies by {me} found in this thread.")
    else:
        for r in recs:
            hrs = r["delta"].total_seconds() / 3600
            click.echo(
                f"{r['reply_number']}. reply to {r['from']} — {hrs:.2f} h (at {r['reply_at']:%Y-%m-%d %H:%M})"
            )

# ─── LIST RECORDS ────────────────────────────────────────────────────────────────

@cli.command("list-records")
def list_records():
    """List all saved contacts."""
    from sqlalchemy.orm import Session as _Session
    with _Session(_engine) as sess:
        for c in sess.query(Contact).all():
            click.echo(
                f"{c.name} <{c.email}>  |  "
                f"Company: {c.company}  |  "
                f"Address: {c.address}  |  "
                f"Phone: {c.phone}  |  "
                f"Title: {c.job_title}  |  "
                f"Importance: {c.importance}"
            )


def main():
    cli()

if __name__ == "__main__":
    sys.exit(main())