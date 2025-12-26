from urllib.parse import urlparse

def normalize_server_url(url: str) -> str:
    """Normalize server URL by ensuring proper protocol and format."""
    url = url.strip()
    if not url:
        return ""
    if "://" not in url:
        url = f"http://{url}"
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return url.rstrip("/")
