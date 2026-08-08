"""Fetch REAL metadata for a video/social link (yt-dlp, no download).

This is how Parakh identifies who is behind a clip without ever guessing at a
face: the source URL carries the actual uploader, channel, title and
description - verifiable ground truth we can then check against SEBI. Supports
YouTube, Instagram, Facebook, X/Twitter, and the many sites yt-dlp handles.
"""
import logging
import re

log = logging.getLogger("parakh.linkmeta")

VIDEO_HOSTS = (
    "youtube.com", "youtu.be", "instagram.com", "facebook.com", "fb.watch",
    "fb.com", "x.com", "twitter.com", "t.co", "dailymotion.com", "vimeo.com",
    "rumble.com", "share.google",
)


def is_video_link(url: str) -> bool:
    u = url.lower()
    if not u.startswith("http"):
        u = "http://" + u
    host = re.sub(r"^https?://", "", u).split("/")[0]
    return any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS)


OEMBED = {
    "youtube.com": "https://www.youtube.com/oembed",
    "youtu.be": "https://www.youtube.com/oembed",
    "instagram.com": "https://api.instagram.com/oembed",
    "vimeo.com": "https://vimeo.com/api/oembed.json",
    "dailymotion.com": "https://www.dailymotion.com/services/oembed",
}


def _host(url: str) -> str:
    u = url if url.startswith("http") else "http://" + url
    return re.sub(r"^https?://", "", u).split("/")[0].lower()


def _oembed(url: str) -> dict | None:
    """Public oEmbed endpoints return the channel/author + title with no auth
    and are not bot-blocked from datacenter IPs (unlike yt-dlp on YouTube)."""
    import httpx

    host = _host(url)
    endpoint = next((ep for h, ep in OEMBED.items() if host == h or host.endswith("." + h)), None)
    if not endpoint:
        return None
    try:
        r = httpx.get(endpoint, params={"url": url, "format": "json"},
                      timeout=15, follow_redirects=True)
        if r.status_code != 200:
            return None
        d = r.json()
        author = d.get("author_name") or d.get("provider_name") or ""
        return {
            "title": (d.get("title") or "")[:300],
            "description": "",
            "uploader": author,
            "channel": author,
            "uploader_url": d.get("author_url") or "",
            "webpage_url": url,
        }
    except Exception as e:
        log.warning("oembed failed for %s: %s", url, e)
        return None


def _ytdlp(url: str) -> dict | None:
    try:
        import yt_dlp

        opts = {"quiet": True, "skip_download": True, "no_warnings": True,
                "noplaylist": True, "extract_flat": False}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": (info.get("title") or "")[:300],
            "description": (info.get("description") or "")[:2000],
            "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "",
            "channel": info.get("channel") or info.get("uploader") or "",
            "uploader_url": info.get("uploader_url") or info.get("channel_url") or "",
            "webpage_url": info.get("webpage_url") or url,
        }
    except Exception as e:
        log.warning("yt-dlp failed for %s: %s", url, e)
        return None


def fetch_metadata(url: str) -> dict | None:
    """oEmbed first (fast, auth-free, not bot-blocked), yt-dlp as fallback for
    richer data / sites without oEmbed."""
    # oEmbed is instant and gives the identity + title we need - don't pay the
    # yt-dlp latency (and YouTube bot-block) just for a description.
    meta = _oembed(url)
    if meta and meta.get("uploader"):
        return meta
    return _ytdlp(url) or meta
