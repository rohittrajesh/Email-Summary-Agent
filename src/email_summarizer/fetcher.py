# src/backend/fetcher.py

import os
import base64
from typing import List, Optional, Iterator

from google.auth.transport.requests import Request
from google.oauth2.credentials   import Credentials
from google_auth_oauthlib.flow    import InstalledAppFlow
from googleapiclient.discovery    import build
from ._gmail_setup import service

# Gmail API scope (read-only)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def _get_service():
    """
    Authenticate (or refresh) and return a Gmail service client.
    """
    creds: Optional[Credentials] = None

    # 1) Load existing tokens, if present
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # 2) If no valid creds, run the OAuth2 flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save for next time
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_thread_raw(thread_id: str) -> List[str]:
    """
    Fetch every message in the thread as its own raw-RFC822 string.
    """
    thread = (
        service.users()
               .threads()
               .get(userId="me", id=thread_id, fields="messages(id)")
               .execute()
    )

    raws: List[str] = []
    for m in thread.get("messages", []):
        msg = (
            service.users()
                   .messages()
                   .get(userId="me", id=m["id"], format="raw")
                   .execute()
        )
        # base64-URL-safe decode + UTF-8
        data = base64.urlsafe_b64decode(msg["raw"])
        raws.append(data.decode("utf-8", errors="replace"))

    return raws


def fetch_message_raw(message_id: str) -> str:
    """
    Fetch a single Gmail message as raw MIME.
    """
    service = _get_service()
    msg = (
        service.users()
               .messages()
               .get(userId="me", id=message_id, format="raw")
               .execute()
    )
    raw_bytes = base64.urlsafe_b64decode(msg["raw"].encode("ASCII"))
    return raw_bytes.decode("utf-8", errors="replace")


def list_recent_threads(n: int = 5) -> List[str]:
    """
    Return the thread IDs of your n most recent threads.
    """
    service = _get_service()
    resp = service.users().threads().list(userId="me", maxResults=n).execute()
    return [t["id"] for t in resp.get("threads", [])]


def fetch_emails(thread_count: int = 5) -> Iterator[List[str]]:
    """
    Generator that yields the raw-MIME strings for each of the most recent
    Gmail threads. By default, fetches `thread_count=5` threads.

    Usage:
        for raw_thread in fetch_emails(10):
            # `raw_thread` is a List[str], one raw MIME per message in the thread
            ...
    """
    for thread_id in list_recent_threads(thread_count):
        try:
            raws = fetch_thread_raw(thread_id)
        except Exception:
            # If it's not a thread, fall back to single-message fetch
            raws = [fetch_message_raw(thread_id)]
        yield raws
