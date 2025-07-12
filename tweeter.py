#!/usr/bin/env python3
"""
Post each entry in notes.txt to X (Twitter).

Features
• Splits paragraphs >280 chars into 280-char chunks
• Threads multi-chunk tweets automatically
• DRY_RUN prints tweets instead of sending
• MAX_PER_RUN and PAUSE_SEC throttle output
• Backs off and resumes on HTTP 429
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import tweepy
from dotenv import load_dotenv

# ── config ────────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).with_name(".env"))  # always load env beside script

API_KEY             = os.getenv("API_KEY")
API_SECRET          = os.getenv("API_SECRET")
ACCESS_TOKEN        = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

NOTES_FILE  = Path(os.getenv("NOTES_FILE", "notes.txt"))
PAUSE_SEC   = float(os.getenv("PAUSE_SEC", "2"))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "15"))
DRY_RUN     = os.getenv("DRY_RUN", "").lower() == "true"

# ── helpers ───────────────────────────────────────────────────────────────────
def chunk_text(text: str, limit: int = 280) -> list[str]:
    """Split long text into ≤limit-char chunks without breaking words."""
    words = text.split()
    chunks, buf = [], []
    cur_len = 0
    for w in words:
        word_len = len(w) + (1 if buf else 0)  # space before word if not first
        if cur_len + word_len > limit:
            chunks.append(" ".join(buf))
            buf, cur_len = [w], len(w)
        else:
            buf.append(w)
            cur_len += word_len
    if buf:
        chunks.append(" ".join(buf))
    return chunks

def load_notes(path: Path) -> list[str]:
    """
    Read notes.txt and return a flat list of tweet-sized strings.
    • Blank line = continue same paragraph
    • Line with '---' = end current paragraph / tweet
    """
    raw = path.read_text(encoding="utf-8").splitlines()
    blocks, buf = [], []
    for line in raw:
        if line.strip() == "---":
            if buf:
                blocks.append(" ".join(buf))
                buf.clear()
        elif line.strip():              # ignore pure blank lines
            buf.append(line.strip())
    if buf:
        blocks.append(" ".join(buf))

    tweets: list[str] = []
    for block in blocks:
        tweets.extend(chunk_text(block))
    return tweets

def backoff_sleep(err: tweepy.TooManyRequests) -> None:
    reset_unix = int(err.response.headers.get("x-rate-limit-reset", 0))
    wait = max(reset_unix - int(time.time()) + 5, 60)
    print(f"429 received, sleeping {wait} s")
    time.sleep(wait)

def post_batch(client: tweepy.Client, tweets: list[str]) -> None:
    sent, reply_to = 0, None
    for txt in tweets[:MAX_PER_RUN]:
        try:
            if DRY_RUN:
                tag = " (thread)" if reply_to else ""
                print(f"[DRY]{tag} {txt[:60]}…")
                tweet_id = None
            else:
                resp = client.create_tweet(
                    text=txt,
                    in_reply_to_tweet_id=reply_to
                )
                tweet_id = resp.data["id"]
            sent += 1
            reply_to = tweet_id or reply_to     # thread from 2nd tweet onward
            time.sleep(PAUSE_SEC)
        except tweepy.TooManyRequests as e:
            backoff_sleep(e)
            continue
    print(f"session done, {sent} tweet(s) processed")

# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print("DBG - API_KEY loaded?", bool(API_KEY))
    tweets = load_notes(NOTES_FILE)
    if not tweets:
        print("nothing to post")
        return

    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET,
    )
    post_batch(client, tweets)

if __name__ == "__main__":
    main()
