# src/email_summarizer/outlook_fetcher.py

from .outlook_setup import get_graph_session

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

def list_messages(top: int = 10, filter_q: str = None, login_hint: str = None):
    sess = get_graph_session(login_hint=login_hint)
    params = {"$top": top}
    if filter_q:
        params["$filter"] = filter_q

    resp = sess.get(f"{GRAPH_BASE}/me/messages", params=params)
    resp.raise_for_status()
    return resp.json().get("value", [])


def get_message_raw(message_id: str, login_hint: str = None) -> str:
    sess = get_graph_session(login_hint=login_hint)
    resp = sess.get(f"{GRAPH_BASE}/me/messages/{message_id}/$value")
    resp.raise_for_status()
    return resp.text
