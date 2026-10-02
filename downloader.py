import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/149 Safari/537.36",
)
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
KUKU_GUEST_USER_ID = os.getenv("KUKU_GUEST_USER_ID", "")
KUKU_JWT_TOKEN = os.getenv("KUKU_JWT_TOKEN", "")


def build_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    cookies = {}
    if KUKU_GUEST_USER_ID:
        cookies["guest_user_id"] = KUKU_GUEST_USER_ID
    if KUKU_JWT_TOKEN:
        cookies["jwtToken"] = KUKU_JWT_TOKEN
    session.cookies.update(cookies)
    return session


def sanitize_name(name):
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name)).strip()
    return cleaned[:160] or "episode"


def get_show_id(url):
    parsed = urlparse(url.strip())
    if parsed.netloc not in {"kukufm.com", "www.kukufm.com"}:
        raise ValueError("Please send a valid KukuFM show URL.")
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2 or parts[0] != "show":
        raise ValueError("Please send a KukuFM /show/... URL.")
    return parts[-1]


def get_all_episodes(show_id):
    session = build_session()
    episodes = []
    page = 1
    while True:
        response = session.get(
            f"https://kukufm.com/api/v2.3/channels/{show_id}/episodes/?page={page}",
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        page_episodes = data.get("episodes", [])
        episodes.extend(page_episodes)
        if not data.get("has_more", False):
            break
        page += 1
        time.sleep(1)
    return episodes


def download_episode(episode, output_folder):
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    ep_index = str(episode.get("index", 0)).zfill(2)
    ep_title = sanitize_name(episode.get("title", f"Episode {ep_index}"))
    final_path = output_folder / f"{ep_index}. {ep_title}.m4a"

    hls_url = episode.get("content", {}).get("hls_url")
    if not hls_url:
        raise RuntimeError(f"No playable URL returned for {ep_title}")

    subprocess.run(
        [
            FFMPEG_PATH,
            "-y",
            "-headers",
            "Referer: https://kukufm.com/\r\nOrigin: https://kukufm.com\r\n",
            "-user_agent",
            USER_AGENT,
            "-i",
            hls_url,
            "-c",
            "copy",
            str(final_path),
        ],
        check=True,
        capture_output=True,
        timeout=60 * 30,
    )
    return final_path
