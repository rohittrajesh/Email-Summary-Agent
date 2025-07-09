# src/email_summarizer/outlook_setup.py

import os
import msal
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES    = ["Mail.Read", "User.Read"]

if not CLIENT_ID:
    raise RuntimeError("Set OUTLOOK_CLIENT_ID in your environment (e.g. in .env)")

def get_graph_session(login_hint: str = None):
    """
    Returns an authenticated requests.Session via device code.
    If login_hint is provided, it helps AAD route the request to
    the right tenant or account.
    """
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)

    # Pass login_hint if we have one
    kwargs = {}
    if login_hint:
        kwargs["login_hint"] = login_hint

    flow = app.initiate_device_flow(scopes=SCOPES, **kwargs)
    if "user_code" not in flow:
        raise RuntimeError("Failed to start device flow: " + str(flow))

    # This prints: “To sign in, use a web browser to open https://microsoft.com/devicelogin and enter ABCD-1234”
    print(flow["message"])

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError("Token acquisition failed: " + result.get("error_description", str(result)))

    sess = requests.Session()
    sess.headers.update({
        "Authorization": f"Bearer {result['access_token']}",
        "Accept": "application/json",
    })
    return sess
