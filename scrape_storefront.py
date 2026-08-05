"""
Milestone 2: Scrape ASINs from an Amazon influencer storefront.

Navigates to amazon.com/shop/<handle>, discovers all idea lists,
then visits each list page to extract ASINs.

Usage:
    python3 scrape_storefront.py
    python3 scrape_storefront.py --storefront the_car_mom
    python3 scrape_storefront.py --storefront the_car_mom --output asins.txt
"""

import argparse
import re
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE = "https://www.amazon.com"
STOREFRONT_URL = BASE + "/shop/{handle}"
ASIN_RE = re.compile(r'^B[A-Z0-9]{9}$')
LIST_PATH_RE = re.compile(r'/shop/[^/]+/list/([A-Z0-9]+)', re.IGNORECASE)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def make_page(browser):
    context = browser.new_context(
        user_agent=UA,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    page = context.new_page()
    return page


def scroll_to_bottom(page, max_scrolls=30, pause=1.5):
    prev = 0
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(pause)
        h = page.evaluate("document.body.scrollHeight")
        if h == prev:
            break
        prev = h


def extract_asins_from_html(html: str) -> set:
    found = set()
    # /dp/ASIN paths in links
    for asin in re.findall(r'/dp/([A-Z0-9]{10})', html):
        if ASIN_RE.match(asin):
            found.add(asin)
    # data-asin="ASIN" attributes
    for asin in re.findall(r'data-asin="([A-Z0-9]{10})"', html):
        if ASIN_RE.match(asin):
            found.add(asin)
    return found


def get_list_urls(page, handle: str) -> list:
    """Visit the main storefront page and return all idea-list URLs."""
    url = STOREFRONT_URL.format(handle=handle)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeout:
        print(f"ERROR: Timed out loading storefront {url}", file=sys.stderr)
        return []

    time.sleep(4)
    html = page.content()

    # Find /shop/<handle>/list/<ID> hrefs
    raw = re.findall(r'href="(/shop/[^"]+/list/[^"?]+)', html)
    raw += re.findall(r'href="(https://www\.amazon\.com/shop/[^"]+/list/[^"?]+)', html)

    seen = set()
    urls = []
    for path in raw:
        clean = path.replace("https://www.amazon.com", "")
        if clean not in seen:
            seen.add(clean)
            urls.append(BASE + clean)

    return urls


def scrape_list_page(page, url: str, verbose: bool) -> set:
    """Visit one idea-list page, scroll fully, return set of ASINs."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeout:
        print(f"  WARN: Timeout on {url}", file=sys.stderr)
        return set()

    time.sleep(3)
    scroll_to_bottom(page, max_scrolls=20, pause=1.2)

    html = page.content()
    asins = extract_asins_from_html(html)

    if verbose:
        title = page.title()
        print(f"  [{len(asins):3d} ASINs]  {title[:60]}")

    return asins


def scrape_storefront(handle: str, verbose: bool = True) -> list:
    all_asins = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Step 1: get all list URLs from the main storefront page
        if verbose:
            print(f"Fetching storefront: {STOREFRONT_URL.format(handle=handle)}")
        page = make_page(browser)
        list_urls = get_list_urls(page, handle)
        page.context.close()

        if not list_urls:
            print("No idea lists found on storefront page. Trying main page ASINs directly.")
            page = make_page(browser)
            page.goto(STOREFRONT_URL.format(handle=handle), wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            scroll_to_bottom(page, max_scrolls=15, pause=1.5)
            all_asins = extract_asins_from_html(page.content())
            page.context.close()
        else:
            if verbose:
                print(f"Found {len(list_urls)} idea lists. Scraping each...\n")

            # Step 2: scrape each list page
            for i, url in enumerate(list_urls, 1):
                if verbose:
                    print(f"  [{i}/{len(list_urls)}]", end=" ")
                page = make_page(browser)
                asins = scrape_list_page(page, url, verbose)
                all_asins |= asins
                page.context.close()
                time.sleep(1.5)  # polite pause between list pages

        browser.close()

    return sorted(all_asins)


def main():
    parser = argparse.ArgumentParser(description="Scrape ASINs from an Amazon storefront.")
    parser.add_argument("--storefront", default="the_car_mom")
    parser.add_argument("--output", default=None, help="Write ASINs to file (one per line)")
    args = parser.parse_args()

    asins = scrape_storefront(args.storefront)

    if not asins:
        print("\nNo ASINs found. Amazon may be blocking requests — try again in a few minutes.")
        sys.exit(1)

    print(f"\nTotal unique ASINs: {len(asins)}")
    for asin in asins:
        print(f"  {asin}")

    if args.output:
        with open(args.output, "w") as f:
            f.write("\n".join(asins) + "\n")
        print(f"\nWritten to {args.output}")


if __name__ == "__main__":
    main()
