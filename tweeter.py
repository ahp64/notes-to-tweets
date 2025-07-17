#!/usr/bin/env python3
"""
Tweet each non‑blank line in notes.txt, remembering progress with tweet_offset.txt.
Long lines (>280 chars) are split at word boundaries and threaded.
"""

from __future__ import annotations
import os, subprocess, time
from pathlib import Path

import tweepy
from dotenv import load_dotenv

# ── env ───────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).with_name(".env"))

API_KEY             = os.getenv("API_KEY")
API_SECRET          = os.getenv("API_SECRET")
ACCESS_TOKEN        = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

NOTES_FILE   = Path(os.getenv("NOTES_FILE", "notes.txt"))
OFFSET_FILE  = Path("tweet_offset.txt")
PAUSE_SEC    = float(os.getenv("PAUSE_SEC") or "2")
MAX_PER_RUN  = int(os.getenv("MAX_PER_RUN") or "15")
DRY_RUN      = os.getenv("DRY_RUN", "").lower() == "true"

# ── helpers ───────────────────────────────────────────────────────────
def chunk_text(text: str, limit: int = 280) -> list[str]:
    words, chunks, buf, cur = text.split(), [], [], 0
    for w in words:
        need = len(w) + (1 if buf else 0)
        if cur + need > limit:
            chunks.append(" ".join(buf))
            buf, cur = [w], len(w)
        else:
            buf.append(w)
            cur += need
    if buf:
        chunks.append(" ".join(buf))
    return chunks

def load_notes(path: Path) -> list[str]:
    tweets: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            tweets.extend(chunk_text(line))
    return tweets

def backoff_sleep(err: tweepy.TooManyRequests) -> None:
    reset = int(err.response.headers.get("x-rate-limit-reset", 0))
    wait  = max(reset - int(time.time()) + 5, 60)
    print(f"429 – sleeping {wait}s")
    time.sleep(wait)

def git_push_offset() -> None:
    """Commit + push the updated offset file using Actions token."""
    subprocess.run(["git", "config", "--global", "user.email", "bot@noreply"],
                   check=True)
    subprocess.run(["git", "config", "--global", "user.name", "tweet‑bot"],
                   check=True)
    subprocess.run(["git", "add", "tweet_offset.txt"], check=True)
    subprocess.run(["git", "commit", "-m", "advance offset"], check=True)
    subprocess.run(["git", "push"], check=True)

# ── main ──────────────────────────────────────────────────────────────
def main() -> None:
    print("DBG – API_KEY loaded?", bool(API_KEY))

    # read current offset (default 0)
    try:
        start = int(OFFSET_FILE.read_text().strip())
    except FileNotFoundError:
        start = 0

    tweets_all = load_notes(NOTES_FILE)

    if start >= len(tweets_all):
        print("No more tweets left, offset at end.")
        return

    # limit to one tweet per run (or MAX_PER_RUN)
    tweets_to_send = tweets_all[start : start + MAX_PER_RUN]

    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET,
    )

    sent, reply_to = 0, None
    for txt in tweets_to_send:
        try:
            if DRY_RUN:
                tag = " (thread)" if reply_to else ""
                print(f"[DRY]{tag} {txt[:60]}…")
                tweet_id = None
            else:
                resp = client.create_tweet(text=txt, in_reply_to_tweet_id=reply_to)
                tweet_id = resp.data["id"]
            sent += 1
            reply_to = tweet_id or reply_to
            time.sleep(PAUSE_SEC)
        except tweepy.TooManyRequests as e:
            backoff_sleep(e)
            continue

    # bump offset and push
    OFFSET_FILE.write_text(str(start + sent))
    if not DRY_RUN:
        git_push_offset()

    print(f"run done, {sent} tweet(s) processed")

if __name__ == "__main__":
    main()
