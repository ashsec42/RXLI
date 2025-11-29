#!/usr/bin/env python3
"""
checker.py
Simple m3u8 master detector. Writes discovered master into streams/<STREAM_NAME>.m3u8
"""

import re
import os
import time
import requests
from bs4 import BeautifulSoup

# Config — override with env vars in GitHub Actions
TARGET_PAGE = os.getenv("TARGET_PAGE", "https://rdxgoa.com/")
KNOWN_CDN_BASE = os.getenv("KNOWN_CDN_BASE", "https://g5nl6xoalpq6-hls-live.5centscdn.com/rdxgoa/")
STREAM_NAME = os.getenv("STREAM_NAME", "rdxgoa")    # will write streams/rdxgoa.m3u8
OUT_DIR = os.getenv("OUT_DIR", "streams")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/114.0")
HEADERS = {"User-Agent": USER_AGENT, "Origin": "https://rdxgoa.com", "Referer": "https://rdxgoa.com/"}
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))

M3U8_REGEX = re.compile(
    r"https?://[^\"]+\.m3u8|/rdxgoa/[^\s'\"<>]+\.sdp/[^\s'\"<>]+\.m3u8|/rdxgoa/[^\s'\"<>]+\.m3u8",
    re.IGNORECASE,
)

os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, f"{STREAM_NAME}.m3u8")


def fetch_text(url, timeout=TIMEOUT):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text, r.headers


def find_candidates_simple():
    found = set()
    try:
        r = requests.get(TARGET_PAGE, headers=HEADERS, timeout=TIMEOUT)
        html = r.text
        found.update(M3U8_REGEX.findall(html))
    except Exception:
        html = ""
    # heuristics
    heuristics = [
        KNOWN_CDN_BASE + "playlist.m3u8",
        KNOWN_CDN_BASE + "index.m3u8",
        KNOWN_CDN_BASE + "master.m3u8",
        KNOWN_CDN_BASE + "chunks_dvr.m3u8",
        KNOWN_CDN_BASE + "playlist_dvr.m3u8",
    ]
    for h in heuristics:
        found.add(h)
    # normalize
    candidates = set()
    for f in found:
        if not f:
            continue
        if f.startswith("/"):
            candidates.add("https://g5nl6xoalpq6-hls-live.5centscdn.com" + f)
        else:
            candidates.add(f)
    return sorted(candidates)


def probe_url(url):
    try:
        # try HEAD first
        r = requests.head(url, headers=HEADERS, timeout=6, allow_redirects=True)
        if r.status_code >= 400 or "mpegurl" not in r.headers.get("Content-Type", "").lower():
            r = requests.get(url, headers=HEADERS, timeout=8)
        return {"url": url, "status": r.status_code, "body": r.text}
    except Exception as e:
        return {"url": url, "status": None, "error": str(e)}


def is_master(body):
    if not body:
        return False
    return "#EXT-X-STREAM-INF" in body


def write_master(body):
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    # atomic replace
    os.replace(tmp, OUT_PATH)
    print(f"[+] wrote master to {OUT_PATH}")


if __name__ == "__main__":
    candidates = find_candidates_simple()
    print("[*] candidates=", candidates)
    best = None
    for c in candidates:
        print("[*] probing", c)
        res = probe_url(c)
        if res.get("status") and res.get("status") < 400 and res.get("body"):
            if is_master(res["body"]):
                print("[+] found master at", c)
                write_master(res["body"])
                best = c
                # also write the exact URL to last_url.txt for downstream steps
                try:
                    with open("last_url.txt", "w", encoding="utf-8") as u:
                        u.write(c + "\n")
                    print("[+] wrote last_url.txt")
                except Exception as e:
                    print("[-] failed to write last_url.txt:", e)
                break

    if not best:
        print("[-] no master found in simple mode")
    else:
        print("[+] done")
