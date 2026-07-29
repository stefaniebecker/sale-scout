"""
Deep link generation for Amazon affiliate URLs.

Converts a standard Amazon affiliate URL into a link that opens the Amazon
app on iOS and Android instead of a browser.

Current implementation: Amazon native URL scheme (amzn://)
  - Works when the Amazon app is already installed on the device
  - Falls back gracefully to the web URL in platforms that don't support
    custom schemes (e.g. Instagram in-app browser)

Future: swap make_deep_link() to call PostTap or URLgenius once API key
is available — the rest of the codebase doesn't need to change.
"""

import os
import re

POSTTAP_API_KEY = os.environ.get("POSTTAP_API_KEY")
URLGENIUS_API_KEY = os.environ.get("URLGENIUS_API_KEY")

# Matches https://www.amazon.com/dp/ASIN or https://www.amazon.com/anything/dp/ASIN
_ASIN_RE = re.compile(r'amazon\.com(?:/[^/]+)?/dp/([A-Z0-9]{10})')


def _extract_asin(url: str):
    m = _ASIN_RE.search(url)
    return m.group(1) if m else None


def _preserve_query(url: str) -> str:
    """Return the query string from a URL, excluding the path."""
    if '?' in url:
        return '?' + url.split('?', 1)[1]
    return ''


def make_deep_link(affiliate_url: str) -> str:
    """
    Convert an Amazon affiliate URL to a deep link that opens the Amazon app.

    Priority:
      1. PostTap API  — if POSTTAP_API_KEY is set
      2. URLgenius API — if URLGENIUS_API_KEY is set
      3. Amazon native scheme (amzn://) — always available, no key needed

    Returns the deep link URL, or the original affiliate URL if conversion fails.
    """
    if POSTTAP_API_KEY:
        return _posttap(affiliate_url)

    if URLGENIUS_API_KEY:
        return _urlgenius(affiliate_url)

    return _amzn_scheme(affiliate_url)


def _amzn_scheme(affiliate_url: str) -> str:
    """
    Amazon native deep link using the amzn:// custom URL scheme.

    Format: amzn://dp/ASIN?tag=PARTNER_TAG&linkCode=ogi
    - Opens the Amazon app directly on iOS and Android
    - Preserves the affiliate tag so commission is tracked
    - If Amazon app is not installed, most messaging apps will fall back
      to the https:// URL automatically
    """
    asin = _extract_asin(affiliate_url)
    if not asin:
        return affiliate_url

    query = _preserve_query(affiliate_url)
    return f"amzn://dp/{asin}{query}"


def _posttap(affiliate_url: str) -> str:
    """
    PostTap (by Button) deep link API.
    Placeholder — fill in once PostTap API endpoint/format is confirmed.
    """
    try:
        import requests
        # TODO: replace with confirmed PostTap endpoint once available
        response = requests.post(
            "https://api.posttap.com/v1/links",
            json={"url": affiliate_url},
            headers={"Authorization": f"Bearer {POSTTAP_API_KEY}"},
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("short_url") or affiliate_url
    except Exception:
        return _amzn_scheme(affiliate_url)


def _urlgenius(affiliate_url: str) -> str:
    """
    URLgenius deep link API.
    Requires Enterprise plan. Falls back to amzn:// scheme on error.
    """
    try:
        import requests
        response = requests.post(
            "https://api.urlgeni.us/links",
            json={"url": affiliate_url},
            headers={"api-key": URLGENIUS_API_KEY},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("shortLink") or data.get("url") or affiliate_url
    except Exception:
        return _amzn_scheme(affiliate_url)
