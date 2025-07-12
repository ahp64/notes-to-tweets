#!/usr/bin/env python3
"""
Read notes.txt and post each entry to X (Twitter).

Safeguards
1. MAX_PER_RUN caps tweets in one session
2. PAUSE_SEC sets a delay between calls
3. Handles 429 errors by waiting until reset
4. DRY_RUN prints tweets instead of sending them
"""

import os
import time
from pathlib import Path

import tweepy
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(Path(__file__).with_name(".env"))
print("DBG - API_KEY loaded?", bool(os.getenv("API_KEY")))


# load keys

API_KEY             = os.getenv("API_KEY")
API_SECRET          = os.getenv("API_SECRET")
ACCESS_TOKEN        = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

NOTES_FILE  = Path(os.getenv("NOTES_FILE", "notes.txt"))
PAUSE_SEC   = float(os.getenv("PAUSE_SEC", "2"))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "15"))
DRY_RUN     = os.getenv("DRY_RUN", "").lower() == "true"

def load_notes(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8").splitlines()
    chunks, buf = [], []
    for line in raw:
        line = line.rstrip()
        if line == "---":
            if buf:
                chunks.append(" ".join(buf))
                buf.clear()
        elif line:
            buf.append(line)
    if buf:
        chunks.append(" ".join(buf))
    return [c[:280] for c in chunks]

def backoff_sleep(err: tweepy.TooManyRequests) -> None:
    reset_unix = int(err.response.headers.get("x-rate-limit-reset", 0))
    wait = max(reset_unix - int(time.time()) + 5, 60)
    print(f"429 received, sleeping {wait} s")
    time.sleep(wait)

def post_batch(client: tweepy.Client, tweets: list[str]) -> None:
    sent = 0
    for txt in tweets[:MAX_PER_RUN]:
        try:
            if DRY_RUN:
                print(f"[DRY] {txt}")
            else:
                client.create_tweet(text=txt)
            sent += 1
            time.sleep(PAUSE_SEC)
        except tweepy.TooManyRequests as e:
            backoff_sleep(e)
            continue
    print(f"session done, {sent} tweet(s) processed")

def main() -> None:
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
