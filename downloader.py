import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
)
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://kukufm.com",
    "Referer": "https://kukufm.com/",
    "package-name": "com.vlv.web",
    "preferred-lang": "hindi",
    "x-source-service": "nodejs-web",
}


def build_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def sanitize_name(name):
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name)).strip()
    return cleaned[:160] or "episode"


def get_show_slug(url):
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc not in {"kukufm.com", "www.kukufm.com"}:
        raise ValueError("Invalid URL. Use: https://kukufm.com/show/<show-slug>")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2 or parts[0] != "show" or not parts[1]:
        raise ValueError("Invalid URL. Use: https://kukufm.com/show/<show-slug>")
    if parsed.query or parsed.fragment:
        raise ValueError("Invalid URL. Send the clean show URL only.")
    return parts[1]


def get_show_info(show_slug):
    session = build_session()
    response = session.get(
        f"https://kukufm.com/api/v2.3/channels/{show_slug}/",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    show_name = data.get("title") or data.get("name") or show_slug.replace("-", " ").title()
    poster_url = (
        data.get("image")
        or data.get("image_url")
        or data.get("cover")
        or data.get("cover_image")
        or data.get("thumbnail")
    )
    return {"name": show_name, "poster_url": poster_url, "raw": data}


def get_all_episodes(show_slug):
    session = build_session()
    episodes = []
    page = 1
    while True:
        response = session.get(
            f"https://kukufm.com/api/v2.3/channels/{show_slug}/episodes/?page={page}",
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        page_episodes = data.get("episodes", [])
        episodes.extend(page_episodes)
        if not data.get("has_more", False):
            break
        page += 1
    return episodes


def download_poster(url, output_folder):
    if not url:
        return None
    output_folder = Path(output_folder)
    path = output_folder / "cover.jpg"
    response = build_session().get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def get_audio_source(episode):
    content = episode.get("content") or {}
    if episode.get("canDownload") is False:
        return None
    return (
        content.get("premiumAudioUrl")
        or content.get("hls_url")
        or content.get("hlsUrl")
    )


def download_episode(episode, output_folder, poster_path=None):
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    ep_index = int(episode.get("index") or 0)
    ep_title = sanitize_name(episode.get("title") or f"Episode {ep_index}")
    final_path = output_folder / f"{ep_index:02d}. {ep_title}.m4a"
    temp_path = output_folder / f".{ep_index:02d}.audio.m4a"

    source_url = get_audio_source(episode)
    if not source_url:
        raise RuntimeError(f"{ep_title}: no downloadable audio source returned.")

    headers = (
        f"User-Agent: {USER_AGENT}\r\n"
        "Origin: https://kukufm.com\r\n"
        "Referer: https://kukufm.com/\r\n"
        "Accept: */*\r\n"
    )

    base_cmd = [
        FFMPEG_PATH, "-y", "-headers", headers, "-i", source_url,
        "-map", "0:a:0", "-vn", "-c:a", "copy", "-bsf:a", "aac_adtstoasc",
        str(temp_path),
    ]
    _run_ffmpeg(base_cmd, ep_title)

    try:
        if poster_path and Path(poster_path).exists():
            cover_cmd = [
                FFMPEG_PATH, "-y",
                "-i", str(temp_path),
                "-i", str(poster_path),
                "-map", "0:a:0", "-map", "1:v:0",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-disposition:v:0", "attached_pic",
                "-metadata", f"title={ep_title}",
                str(final_path),
            ]
            _run_ffmpeg(cover_cmd, ep_title)
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(final_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise

    if not final_path.exists() or final_path.stat().st_size == 0:
        raise RuntimeError(f"{ep_title}: output file was not created.")
    return final_path


def _run_ffmpeg(command, title):
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=60 * 60
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"FFmpeg not found: {FFMPEG_PATH}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{title}: FFmpeg timed out.") from exc
    except subprocess.CalledProcessError as exc:
        error = (exc.stderr or "")[-1000:]
        raise RuntimeError(f"{title}: FFmpeg failed. {error}") from exc
