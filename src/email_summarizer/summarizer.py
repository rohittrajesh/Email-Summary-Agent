# src/email_summarizer/summarizer.py

from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()
import os
import time
import openai
from openai.error import RateLimitError

# Initialize API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Chunking configuration
MAX_TOKENS = 800             # conservative target per chunk
TOKEN_CHAR_RATIO = 4         # approx. chars per token
MAX_CHUNK_CHARS = MAX_TOKENS * TOKEN_CHAR_RATIO


def summarize_message(text: str) -> str:
    """
    Condense a single very long message into 5–7 bullet points.
    """
    prompt = (
        "Summarize this email message in 5–7 concise bullet points:\n\n"
        f"{text}\n\n"
        "Bullets:"
    )
    for backoff in (1, 2, 4):
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=300,
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError:
            time.sleep(backoff)
    # Final attempt
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


def _chunk_messages(bodies: List[str]) -> List[List[str]]:
    """
    Split a list of message texts into chunks so each chunk stays under MAX_CHUNK_CHARS.
    """
    chunks: List[List[str]] = []
    cur_chunk: List[str] = []
    cur_size = 0

    for body in bodies:
        # Ensure no single message exceeds the chunk limit
        if len(body) > MAX_CHUNK_CHARS:
            body = body[:MAX_CHUNK_CHARS] + "\n…[truncated]"

        segment_len = len(body) + 1  # +1 for separator/newline
        if cur_chunk and (cur_size + segment_len > MAX_CHUNK_CHARS):
            chunks.append(cur_chunk)
            cur_chunk = []
            cur_size = 0

        cur_chunk.append(body)
        cur_size += segment_len

    if cur_chunk:
        chunks.append(cur_chunk)

    return chunks


def _call_api(bodies: List[str]) -> str:
    """
    Build a prompt from `bodies`, send to the LLM, and return its response.
    """
    prompt_lines = [
        "You are an assistant that summarizes email threads.",
        "",
        "Thread messages (each bullet is one message):",
    ]
    for body in bodies:
        prompt_lines.append(f"- {body}")
    prompt_lines.extend(["", "Overall Summary:"])
    user_content = "\n".join(prompt_lines)

    for backoff in (1, 2, 4):
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": user_content}],
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError:
            time.sleep(backoff)
    # Final attempt
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_content}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def summarize(messages: List[Dict]) -> str:
    """
    Given a list of parsed messages, produce a cohesive summary
    while ensuring we never exceed the LLM's context window.
    """
    if not messages:
        return ""

    # 1) Extract just the text bodies
    bodies = [msg["body"] for msg in messages if msg.get("body")]

    # 2) Pre‐summarize any very large bodies
    processed = []
    for body in bodies:
        if len(body) > MAX_CHUNK_CHARS:
            processed.append(summarize_message(body))
        else:
            processed.append(body)

    # 3) Chunk the processed list safely
    chunks = _chunk_messages(processed)
    if len(chunks) == 1:
        return _call_api(chunks[0])

    # 4) Summarize each chunk recursively
    partial_summaries = [summarize(chunk) for chunk in chunks]
    combined = "\n\n".join(f"Part {i+1}:\n{sub}" for i, sub in enumerate(partial_summaries))

    # 5) Final pass to unify all partials
    final_prompt = [
        "You are an assistant that merges multiple partial summaries into one cohesive summary.",
        "",
        "Partial summaries:",
        combined,
        "",
        "Final Unified Summary:",
    ]
    final_content = "\n".join(final_prompt)
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": final_content}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()