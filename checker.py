#!/usr/bin/env python3
"""
checker.py (playwright-capable)

Modes:
 - MODE=simple    : HTML/heuristics probing (fast)
 - MODE=playwright: launch a headless browser and capture network requests (robust for JS sites)

Set MODE via env var (default: simple). In GitHub Actions we'll set MODE=playwright.
"""
import os
import re
import time
import json
import requests

M3U8_REGEX = re.compile(
    r"https?://[^\"]+\.m3u8|/rdxgoa/[^\s'\"<>]+\.sdp/[^\s'\"<>]+\.m3u8|/rdxgoa/[^\s'\"<>]+\.m3u8",
    re.IGNORECASE,
)

TARGET_PAGE = os.getenv("TARGET_PAGE", "https://rdxgoa.com/live-tv/")
KNOWN_CDN_BASE = os.getenv("KNOWN_CDN_BASE", "https://g5nl6xoalpq6-hls-live.5centscdn.com/rdxgoa/")
STREAM_NAME = os.getenv("STREAM_NAME", "rdxgoa")
OUT_DIR = os.getenv("OUT_DIR", "streams")
MODE = os.getenv("MODE", "simple").lower()
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/114.0")
HEADERS = {"User-Agent": USER_AGENT, "Origin": "https://rdxgoa.com", "Referer": "https://rdxgoa.com/"}
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))

os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH = os.path.join(OUT_DIR, f"{STREAM_NAME}.m3u")

# --- simple helpers ---
def probe_url(url):
    try:
        # try GET directly (some CDNs respond differently to HEAD)
        r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        return {"url": url, "status": r.status_code, "body": r.text}
    except Exception as e:
        return {"url": url, "status": None, "error": str(e)}

def is_master(body):
    if not body:
        return False
    return "#EXT-X-STREAM-INF" in body

def save_master_text(url, body):
    # write master content and last_url.txt
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp, OUT_PATH)
    with open("last_url.txt", "w", encoding="utf-8") as u:
        u.write(url + "\n")
    print("[+] saved master and last_url.txt ->", url)

def find_candidates_simple():
    found = set()
    try:
        r = requests.get(TARGET_PAGE, headers=HEADERS, timeout=TIMEOUT)
        html = r.text
        found.update(M3U8_REGEX.findall(html))
    except Exception:
        html = ""
    heuristics = [
        KNOWN_CDN_BASE + "playlist.m3u8",
        KNOWN_CDN_BASE + "index.m3u8",
        KNOWN_CDN_BASE + "master.m3u8",
        KNOWN_CDN_BASE + "chunks_dvr.m3u8",
        KNOWN_CDN_BASE + "playlist_dvr.m3u8",
    ]
    for h in heuristics:
        found.add(h)
    candidates = set()
    for f in found:
        if not f:
            continue
        if f.startswith("/"):
            candidates.add("https://g5nl6xoalpq6-hls-live.5centscdn.com" + f)
        else:
            candidates.add(f)
    return sorted(candidates)

def run_simple():
    candidates = find_candidates_simple()
    print("[*] candidates=", candidates)
    for c in candidates:
        print("[*] probing", c)
        res = probe_url(c)
        if res.get("status") and res.get("status") < 400 and res.get("body"):
            if is_master(res["body"]):
                print("[+] found master at", c)
                save_master_text(c, res["body"])
                return True
    print("[-] no master found in simple mode")
    return False

# --- playwright mode ---
def run_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("Playwright not available:", e)
        return False

    found_master = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # intercept requests and inspect responses for m3u8
        def on_request(request):
            url = request.url
            if ".m3u8" in url.lower():
                print("[NET] m3u8 requested:", url)
                try:
                    r = requests.get(url, headers=HEADERS, timeout=6)
                    if r.ok:
                        body = r.text
                        if "#EXT-X-STREAM-INF" in body:
                            print("[NET] found master in network:", url)
                            found_master = {"url": url, "body": body}
                            # save and stop
                            save_master_text(url, body)
                except Exception as e:
                    print("err fetching", url, e)

        page.on("request", on_request)

        # goto and wait to allow player to initialize
        print("[*] opening page:", TARGET_PAGE)
        try:
            page.goto(TARGET_PAGE, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print("page.goto error (ignored):", e)

        # wait a bit for background requests (increase if needed)
        time.sleep(4)
        # also query existing requests in context (some requests fire during navigation)
        for req in context.request_ids:
            pass

        browser.close()
    # check if file was written
    if os.path.isfile("last_url.txt"):
        print("[+] last_url.txt present (playwright mode success)")
        return True
    print("[-] playwright mode did not find master")
    return False

# --- main ---
if __name__ == "__main__":
    print("[*] MODE:", MODE)
    ok = False
    if MODE == "playwright":
        ok = run_playwright()
        if not ok:
            print("[*] fallback to simple mode")
            ok = run_simple()
    else:
        ok = run_simple()
    if ok:
        print("[+] done")
    else:
        print("[-] finished without master")
