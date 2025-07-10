# src/email_summarizer/summarizer.py

from typing import List, Dict

from dotenv import load_dotenv
load_dotenv()

import os 
import openai

# no longer need an OpenAI() client object—just call the package methods
openai.api_key = os.getenv("OPENAI_API_KEY")

# — Chunking constants ——————————————————————————————————————
MAX_TOKENS = 2000
TOKEN_CHAR_RATIO = 4       # rough chars per token
MAX_CHUNK_CHARS = MAX_TOKENS * TOKEN_CHAR_RATIO


def _chunk_messages(messages: List[Dict]) -> List[List[Dict]]:
    """
    Split a list of parsed messages into chunks so that each chunk's
    total character length stays under MAX_CHUNK_CHARS.
    """
    chunks: List[List[Dict]] = []
    cur_chunk: List[Dict] = []
    cur_size = 0

    for msg in messages:
        # build a single‐line representation for size counting
        segment = f"{msg.get('date','')} - {msg.get('sender','')}: {msg.get('body','')}\n"
        seg_len = len(segment)

        # if adding this message would blow past our char‐limit, start a new chunk
        if cur_chunk and (cur_size + seg_len > MAX_CHUNK_CHARS):
            chunks.append(cur_chunk)
            cur_chunk = []
            cur_size = 0

        cur_chunk.append(msg)
        cur_size += seg_len

    if cur_chunk:
        chunks.append(cur_chunk)

    return chunks


def _call_api(messages: List[Dict]) -> str:
    """
    Construct the prompt from `messages`, call the LLM, and return its answer.
    """
    # build the user prompt
    prompt_lines = [
        "You are an assistant that summarizes email threads.",
        "",
        "Thread messages:",
    ]
    for msg in messages:
        prompt_lines.append(
            f"{msg.get('date','')} - {msg.get('sender','')}: {msg.get('body','')}"
        )
    prompt_lines.extend([
        "",
        "Summary:",
    ])
    user_content = "\n".join(prompt_lines)

    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_content}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def summarize(messages: List[Dict]) -> str:
    """
    Given a list of parsed messages, produce a summary. If the thread is large,
    we split into chunks, summarize each, then combine.
    """
    # 1) Empty‐thread guard
    if not messages:
        return ""

    # 2) Chunk if needed
    chunks = _chunk_messages(messages)
    if len(chunks) == 1:
        return _call_api(chunks[0])

    # 3) Otherwise: summarize each chunk, then assemble
    sub_summaries = [summarize(chunk) for chunk in chunks]
    combined = "\n\n".join(f"Part {i+1}:\n{sub}" for i, sub in enumerate(sub_summaries))

    # 4) Final pass to unify into one cohesive summary:
    final_prompt = [
        "You are an assistant that merges multiple partial summaries into one cohesive summary.",
        "",
        "Partial summaries:",
        combined,
        "",
        "Final unified summary:",
    ]
    final_content = "\n".join(final_prompt)
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": final_content}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()
