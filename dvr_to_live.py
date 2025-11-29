#!/usr/bin/env python3
"""
dvr_to_live.py

Fetches the dynamic playlist (PLAYLIST_URL) and either:
 - saves the playlist as streams/<STREAM_NAME>.m3u if it is a master playlist
 - or creates a short live sliding-window playlist streams/<STREAM_NAME>_live.m3u
   containing the last N segments from the fetched DVR/media playlist.

Environment vars:
 - PLAYLIST_URL (required)  : full URL to playlist_dvr.m3u8 (or master m3u8)
 - STREAM_NAME (optional)   : base name for output files (default: rdxgoa)
 - OUT_DIR (optional)       : output directory (default: streams)
 - N_SEGMENTS (optional)    : how many last segments to include for live (default: 4)
 - USER_AGENT / REFERER / ORIGIN optional headers
"""

import os
import sys
import requests
import urllib.parse

PLAYLIST_URL = os.getenv("PLAYLIST_URL")
if not PLAYLIST_URL:
    # allow reading last_url.txt as fallback for local tests / workflows
    if os.path.isfile("last_url.txt"):
        with open("last_url.txt", "r", encoding="utf-8") as f:
            PLAYLIST_URL = f.read().strip()
if not PLAYLIST_URL:
    print("PLAYLIST_URL not set and last_url.txt not found. Exiting.", file=sys.stderr)
    sys.exit(2)

STREAM_NAME = os.getenv("STREAM_NAME", "rdxgoa")
OUT_DIR = os.getenv("OUT_DIR", "streams")
N_SEGMENTS = int(os.getenv("N_SEGMENTS", "4"))

HEADERS = {
    "User-Agent": os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/114.0"),
    "Referer": os.getenv("REFERER", "https://rdxgoa.com/"),
    "Origin": os.getenv("ORIGIN", "https://rdxgoa.com"),
}
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "8"))

os.makedirs(OUT_DIR, exist_ok=True)
OUT_PATH_M3U = os.path.join(OUT_DIR, f"{STREAM_NAME}.m3u")
OUT_PATH_LIVE = os.path.join(OUT_DIR, f"{STREAM_NAME}_live.m3u")


def fetch_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e


def make_absolute(base, ref):
    """Return absolute URL for ref relative to base. If ref is already absolute, return it."""
    if urllib.parse.urlparse(ref).scheme:
        return ref
    return urllib.parse.urljoin(base, ref)


def build_live(playlist_text, base_url, n=N_SEGMENTS):
    """
    Build a short sliding-window live playlist from a media/DVR playlist text.
    Returns the generated m3u content as string.
    """
    lines = [l.strip() for l in playlist_text.splitlines() if l.strip() != ""]
    # Collect segment tuples (EXTINF, uri)
    segs = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            if i + 1 < len(lines):
                seg_uri = lines[i + 1]
                segs.append((lines[i], seg_uri))
                i += 2
                continue
        i += 1

    if not segs:
        raise RuntimeError("No segments found in playlist")

    tail = segs[-n:] if len(segs) >= n else segs

    # Get target duration if present
    td = 6
    for l in lines:
        if l.startswith("#EXT-X-TARGETDURATION"):
            try:
                td = int(l.split(":", 1)[1])
            except Exception:
                pass
            break

    # Get media sequence if present
    media_seq = None
    for l in lines:
        if l.startswith("#EXT-X-MEDIA-SEQUENCE"):
            try:
                media_seq = int(l.split(":", 1)[1])
            except Exception:
                media_seq = None
            break
    if media_seq is None:
        media_seq = 0

    # Compute sequence number for the first item of our tail window
    first_seq = media_seq + (len(segs) - len(tail))

    out_lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{td}",
        f"#EXT-X-MEDIA-SEQUENCE:{first_seq}",
    ]

    for extinf, uri in tail:
        abs_uri = make_absolute(base_url, uri)
        out_lines.append(extinf)
        out_lines.append(abs_uri)

    # Do NOT append #EXT-X-ENDLIST — this is a sliding live playlist
    return "\n".join(out_lines) + "\n"


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def main():
    try:
        playlist_text = fetch_text(PLAYLIST_URL)
    except Exception as e:
        print(e, file=sys.stderr)
        return 2

    # If the fetched playlist is a master (contains EXT-X-STREAM-INF), save it as .m3u
    if "#EXT-X-STREAM-INF" in playlist_text:
        try:
            atomic_write(OUT_PATH_M3U, playlist_text)
            print(f"Wrote master playlist to {OUT_PATH_M3U}")
            return 0
        except Exception as e:
            print(f"Failed to write master: {e}", file=sys.stderr)
            return 3

    # Otherwise treat as media (DVR) playlist and produce small live window
    base_url = PLAYLIST_URL.rsplit("/", 1)[0] + "/"
    try:
        live_text = build_live(playlist_text, base_url, n=N_SEGMENTS)
    except Exception as e:
        print(f"Failed to build live playlist: {e}", file=sys.stderr)
        return 4

    try:
        atomic_write(OUT_PATH_LIVE, live_text)
        print(f"Wrote live playlist to {OUT_PATH_LIVE}")
        return 0
    except Exception as e:
        print(f"Failed to write live file: {e}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main())
