# src/email_summarizer/fetcher.py

import os
import base64
from typing import Iterator, Optional, List

from googleapiclient.discovery       import build
from google.oauth2.credentials       import Credentials
from google.auth.transport.requests  import Request
from google_auth_oauthlib.flow       import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# pick up these paths from ENV, falling back to the current dir
CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE          = os.getenv("GOOGLE_TOKEN_FILE",       "token.json")


def _get_service():
    creds: Optional[Credentials] = None

    # 1) Try loading saved token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # 2) If no valid creds, do OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                SCOPES
            )
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent"
            )
        # 3) Save for next time
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


class RawEmail:
    def __init__(
        self,
        msg_id: str,
        date:   str,
        sender: str,
        subject:str,
        plain:  str,
        html:   str
    ):
        self.id      = msg_id
        self.date    = date
        self.sender  = sender
        self.subject = subject
        self.plain   = plain
        self.html    = html


class RawThread:
    def __init__(self, thread_id: str, messages: List[RawEmail]):
        self.id       = thread_id
        self.messages = messages


def fetch_threads(
    max_threads: int = 5,
    query:       Optional[str] = None
) -> Iterator[RawThread]:
    """
    List up to `max_threads` UNREAD threads in INBOX, optionally
    filtered by Gmail `q=…` syntax (e.g. "newer_than:1d").
    Yields RawThread objects.
    """
    svc = _get_service()

    list_kwargs = {
        "userId":     "me",
        "maxResults": max_threads,
        "labelIds":   ["INBOX", "UNREAD"],
    }
    if query:
        list_kwargs["q"] = query

    resp = svc.users().threads().list(**list_kwargs).execute()
    for meta in resp.get("threads", []):
        tid = meta["id"]
        thread = svc.users().threads().get(
            userId="me", id=tid, format="full"
        ).execute()

        raws: List[RawEmail] = []
        for m in thread.get("messages", []):
            msg = svc.users().messages().get(
                userId="me", id=m["id"], format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            date    = headers.get("Date", "")
            sender  = headers.get("From", "")
            subject = headers.get("Subject", "")

            plain, html = "", ""
            parts = msg["payload"].get("parts") or []
            for part in parts:
                data = part.get("body", {}).get("data")
                if not data:
                    continue
                chunk = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                mime  = part.get("mimeType", "")
                if mime == "text/plain":
                    plain = chunk
                elif mime == "text/html":
                    html = chunk

            # fallback if non-multipart
            if not parts and msg["payload"].get("body", {}).get("data"):
                data = msg["payload"]["body"]["data"]
                text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                if msg["payload"].get("mimeType") == "text/html":
                    html = text
                else:
                    plain = text

            raws.append(RawEmail(m["id"], date, sender, subject, plain, html))

        yield RawThread(tid, raws)


def mark_as_read(raw_email: RawEmail):
    """
    Remove the UNREAD label so Gmail won’t return this message again.
    """
    svc = _get_service()
    svc.users().messages().modify(
        userId="me",
        id=raw_email.id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()