"""Tiny stdlib page fetcher shared by resolve/collect/verify. Returns '' on any failure."""
from __future__ import annotations

import re
import urllib.error
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (compatible; Agent47-SDR/1.0)"}
_MAX_BYTES = 400_000


def fetch_text(url: str, timeout: int = 15) -> str:
    """GET a URL and return visible text (tags stripped), '' on any failure."""
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(_MAX_BYTES).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    return strip_html(raw)


def strip_html(html: str) -> str:
    """Crude but dependency-free: drop script/style, strip tags, collapse whitespace."""
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(text.split())
