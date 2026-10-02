import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/149 Safari/537.36",
)
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))


def build_session():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "hi-IN,hi;q=0.9,en;q=0.8",
        }
    )
    return session


def sanitize_name(name):
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name)).strip()
    return cleaned[:160] or "episode"


def get_show_id(url):
    parsed = urlparse(url.strip())
    if parsed.netloc not in {"kukufm.com", "www.kukufm.com"}:
        raise ValueError("Please send a valid KukuFM show URL.")

    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2 or parts[0] != "show" or not parts[1]:
        raise ValueError("Please send a KukuFM /show/<slug> URL.")

    return parts[1]


def _extract_initial_data(text):
    marker = '"initialData":'
    start = text.find(marker)
    if start == -1:
        raise RuntimeError("Show response did not contain initialData.")

    start += len(marker)
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Could not parse initialData from the show response.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Invalid initialData format returned by KukuFM.")
    return data


def get_show_data(show_slug):
    session = build_session()
    url = f"https://kukufm.com/show/{show_slug}"

    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Show request failed: {exc}") from exc

    initial_data = _extract_initial_data(response.text)
    show = initial_data.get("show")
    episodes = initial_data.get("episodes")

    if not isinstance(show, dict):
        raise RuntimeError("Show metadata was not found in the current response.")
    if not isinstance(episodes, list):
        raise RuntimeError("Episode list was not found in the current response.")

    return show, episodes


def get_all_episodes(show_slug):
    _, episodes = get_show_data(show_slug)
    return sorted(episodes, key=lambda item: item.get("index", 0))


def _get_audio_source(episode):
    content = episode.get("content") or {}

    # Only use media that the response says this session may download.
    if episode.get("canDownload") is not True:
        return None

    return content.get("premiumAudioUrl") or content.get("hlsUrl")


def download_episode(episode, output_folder):
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    ep_index = int(episode.get("index") or 0)
    ep_title = sanitize_name(episode.get("title") or f"Episode {ep_index}")
    final_path = output_folder / f"{ep_index:02d}. {ep_title}.m4a"

    source_url = _get_audio_source(episode)
    if not source_url:
        raise RuntimeError(
            f"{ep_title}: no permitted downloadable audio URL was returned."
        )

    command = [
        FFMPEG_PATH,
        "-y",
        "-user_agent",
        USER_AGENT,
        "-headers",
        "Referer: https://kukufm.com/\\r\\nOrigin: https://kukufm.com\\r\\n",
        "-i",
        source_url,
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "copy",
        str(final_path),
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=60 * 30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"FFmpeg was not found at: {FFMPEG_PATH}") from exc
    except subprocess.TimeoutExpired as exc:
        final_path.unlink(missing_ok=True)
        raise RuntimeError(f"{ep_title}: FFmpeg timed out.") from exc
    except subprocess.CalledProcessError as exc:
        final_path.unlink(missing_ok=True)
        error = (exc.stderr or "").strip()
        if len(error) > 700:
            error = error[-700:]
        raise RuntimeError(f"{ep_title}: FFmpeg failed. {error}") from exc

    if not final_path.exists() or final_path.stat().st_size == 0:
        raise RuntimeError(f"{ep_title}: output file was not created.")

    return final_path
