# src/email_summarizer/_gmail_setup.py

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials    import Credentials
from google_auth_oauthlib.flow    import InstalledAppFlow
from googleapiclient.discovery     import build

# Scopes for Gmail read‐only + thread metadata
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def get_gmail_service():
    """
    Handles loading/storing OAuth2 credentials, and returns
    an authenticated Gmail API service object.
    Expects to find:
      - credentials.json   (your OAuth client_secret)
      - token.json         (where we store the user’s token)
    """
    creds = None
    # 1) Try load existing token
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # 2) If no valid creds, run the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save for next run
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    # 3) Build the Gmail service
    return build("gmail", "v1", credentials=creds)

# instantiate once
service = get_gmail_service()