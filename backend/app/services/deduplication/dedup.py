import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from rapidfuzz import fuzz


def normalize_url(url: str) -> str:
    url = url.strip().lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    parsed = urlparse(f"http://{url}")
    path = parsed.path.rstrip("/")
    # strip common tracking params
    keep = [p for p in parsed.query.split("&") if p and not p.split("=")[0].startswith(("utm_", "fbclid", "ref"))]
    return parsed.netloc + path + ("?" + "&".join(keep) if keep else "")


def content_fingerprint(title: str, content: str | None) -> str:
    norm_title = re.sub(r"[^a-z0-9 ]", "", (title or "").lower())
    norm_content = re.sub(r"\s+", " ", (content or "").lower())[:2000]
    return hashlib.sha256((norm_title + "|" + norm_content).encode()).hexdigest()


def titles_match(a: str, b: str, threshold: float = 82.0) -> bool:
    score = max(
        fuzz.token_set_ratio(a.lower(), b.lower()),
        fuzz.partial_ratio(a.lower(), b.lower()),
    )
    return score >= threshold


def within_time_window(t1: datetime | None, t2: datetime, hours: float = 48.0) -> bool:
    if t1 is None:
        return True
    if t1.tzinfo is None:
        t1 = t1.replace(tzinfo=timezone.utc)
    if t2.tzinfo is None:
        t2 = t2.replace(tzinfo=timezone.utc)
    delta = abs((t2 - t1).total_seconds()) / 3600.0
    return delta <= hours
