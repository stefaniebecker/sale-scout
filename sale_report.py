"""
Milestone 3: Scrape storefront → check prices → report items on sale.

Scrapes all ASINs from an Amazon influencer storefront, batches them through
the Creators API, and prints any items at or above the discount threshold.

Usage:
    python3 sale_report.py
    python3 sale_report.py --storefront the_car_mom --threshold 15
    python3 sale_report.py --asins-file asins.txt --threshold 15
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from creatorsapi_python_sdk import ApiClient, DefaultApi
from creatorsapi_python_sdk.models import GetItemsRequestContent, GetItemsResource

from scrape_storefront import scrape_storefront
from deeplink import make_deep_link

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

CREDENTIAL_ID     = os.environ["AMAZON_ACCESS_KEY"]
CREDENTIAL_SECRET = os.environ["AMAZON_SECRET_KEY"]
PARTNER_TAG       = os.environ["AMAZON_PARTNER_TAG"]
API_VERSION       = os.environ.get("AMAZON_API_VERSION", "v3.1")
LWA_ENDPOINT      = "https://api.amazon.com/auth/o2/token"
MARKETPLACE       = "www.amazon.com"

BATCH_SIZE = 10  # API max per request

RESOURCES = [
    GetItemsResource.ITEM_INFO_DOT_TITLE,
    GetItemsResource.IMAGES_DOT_PRIMARY_DOT_MEDIUM,
    GetItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_PRICE,
    GetItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_DEAL_DETAILS,
    GetItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_AVAILABILITY,
    GetItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_IS_BUY_BOX_WINNER,
]


@dataclass
class SaleItem:
    asin: str
    title: str
    current_price: float
    original_price: float
    pct_off: int
    deal_type: object
    affiliate_url: str
    deep_link: str
    image_url: object


def build_api() -> DefaultApi:
    client = ApiClient(
        host="https://creatorsapi.amazon",
        credential_id=CREDENTIAL_ID,
        credential_secret=CREDENTIAL_SECRET,
        version=API_VERSION,
        auth_endpoint=LWA_ENDPOINT,
    )
    return DefaultApi(client)


def batches(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def get_sale_items(api: DefaultApi, asins: list, threshold: int, stats: dict = None) -> list:
    """Pass a dict as `stats` to collect batch success/failure counts."""
    sale_items = []
    total_batches = (len(asins) + BATCH_SIZE - 1) // BATCH_SIZE
    if stats is not None:
        stats.update(batches_ok=0, batches_failed=0, last_error=None)

    for i, batch in enumerate(batches(asins, BATCH_SIZE), 1):
        print(f"  Checking batch {i}/{total_batches} ({len(batch)} ASINs)...", end=" ")
        try:
            request = GetItemsRequestContent(
                partner_tag=PARTNER_TAG,
                item_ids=batch,
                resources=RESOURCES,
            )
            response = api.get_items(x_marketplace=MARKETPLACE, get_items_request_content=request)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            if stats is not None:
                stats["batches_failed"] += 1
                stats["last_error"] = str(e)[:200]
            time.sleep(2)
            continue

        if stats is not None:
            stats["batches_ok"] += 1

        items = []
        result = getattr(response, "items_result", None)
        if result:
            items = getattr(result, "items", []) or []

        found_on_sale = 0
        for item in items:
            sale = extract_sale(item, threshold)
            if sale:
                sale_items.append(sale)
                found_on_sale += 1

        print(f"{found_on_sale} on sale")
        time.sleep(0.5)  # stay within 1 req/sec rate limit

    return sale_items


def extract_sale(item, threshold: int):
    """Return a SaleItem if the buy-box listing is on sale >= threshold%, else None."""
    offers = getattr(item, "offers_v2", None)
    listings = getattr(offers, "listings", None) if offers else None
    if not listings:
        return None

    # Prefer the buy-box winner; fall back to first listing
    buy_box = next((l for l in listings if getattr(l, "is_buy_box_winner", False)), None)
    listing = buy_box or listings[0]

    price_obj = getattr(listing, "price", None)
    if not price_obj:
        return None

    money = getattr(price_obj, "money", None)
    current = getattr(money, "amount", None) if money else None
    if current is None:
        return None

    savings = getattr(price_obj, "savings", None)
    pct_off = getattr(savings, "percentage", None) if savings else None
    if not pct_off or pct_off < threshold:
        return None

    saving_basis = getattr(price_obj, "saving_basis", None)
    basis_money = getattr(saving_basis, "money", None) if saving_basis else None
    original = getattr(basis_money, "amount", None) if basis_money else current

    deal = getattr(listing, "deal_details", None)
    deal_type = getattr(deal, "deal_type", None) if deal else None

    title = "Unknown"
    if item.item_info and item.item_info.title:
        title = item.item_info.title.display_value or "Unknown"

    affiliate_url = getattr(item, "detail_page_url", "") or ""

    image_url = None
    if item.images and item.images.primary and item.images.primary.medium:
        image_url = item.images.primary.medium.url

    return SaleItem(
        asin=item.asin,
        title=title,
        current_price=current,
        original_price=original,
        pct_off=pct_off,
        deal_type=str(deal_type) if deal_type else None,
        affiliate_url=affiliate_url,
        deep_link=make_deep_link(affiliate_url),
        image_url=image_url,
    )


def print_report(sale_items: list[SaleItem], storefront: str, threshold: int):
    print(f"\n{'═' * 65}")
    print(f"  SALE REPORT — {storefront.upper()}  (>= {threshold}% off)")
    print(f"{'═' * 65}")

    if not sale_items:
        print(f"\n  No items found at {threshold}% off or more today.\n")
        return

    # Sort by biggest discount first
    sale_items.sort(key=lambda x: x.pct_off, reverse=True)

    for item in sale_items:
        print(f"\n  {item.title[:60]}")
        print(f"  ASIN:     {item.asin}")
        print(f"  Price:    ${item.current_price:.2f}  (was ${item.original_price:.2f}  —  {item.pct_off}% off)")
        if item.deal_type:
            print(f"  Deal:     {item.deal_type}")
        if item.image_url:
            print(f"  Image:    {item.image_url}")
        print(f"  Web link: {item.affiliate_url}")
        print(f"  App link: {item.deep_link}")

    print(f"\n{'─' * 65}")
    print(f"  {len(sale_items)} item(s) on sale at {threshold}%+ off")
    print(f"{'─' * 65}\n")


def load_asins_from_file(path: str) -> list:
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storefront", default="the_car_mom")
    parser.add_argument("--threshold", type=int, default=15, help="Minimum %% off for Slack (default: 15)")
    parser.add_argument("--email-threshold", type=int, default=25, help="Minimum %% off for email (default: 25)")
    parser.add_argument("--asins-file", default=None, help="Skip scraping; load ASINs from file")
    parser.add_argument("--slack-channel", default=None, help="Override Slack channel (default: from .env)")
    parser.add_argument("--email-to", default=None, help="Send email digest to this address")
    parser.add_argument("--no-slack", action="store_true", help="Skip Slack delivery")
    parser.add_argument("--no-email", action="store_true", help="Skip email delivery")
    args = parser.parse_args()

    # Step 1: get ASINs
    if args.asins_file:
        print(f"Loading ASINs from {args.asins_file}...")
        asins = load_asins_from_file(args.asins_file)
    else:
        print(f"Scraping storefront: {args.storefront}")
        asins = scrape_storefront(args.storefront)

    if not asins:
        print("No ASINs to check. Exiting.")
        sys.exit(1)

    # Use the lower of the two thresholds so we only call the API once
    min_threshold = min(args.threshold, args.email_threshold)
    print(f"\nFound {len(asins)} ASINs. Checking prices...\n")

    # Step 2: check prices (fetch everything at the lower threshold)
    api = build_api()
    all_sale_items = get_sale_items(api, asins, min_threshold)

    # Step 3: filter per delivery method and print report
    slack_items = [i for i in all_sale_items if i.pct_off >= args.threshold]
    email_items = [i for i in all_sale_items if i.pct_off >= args.email_threshold]

    print_report(slack_items, args.storefront, args.threshold)

    # Step 4: Slack delivery (15%+ by default)
    if not args.no_slack and slack_items:
        channel = args.slack_channel or os.environ.get("SLACK_CHANNEL", "carmomsales")
        print(f"Sending {len(slack_items)} items to #{channel} (>= {args.threshold}% off)...")
        sent = send_sale_digest(slack_items, channel=channel, creator_name="The Car Mom")
        print(f"Slack: {sent}/{len(slack_items)} items delivered.")

    # Step 5: email delivery (25%+ by default)
    if not args.no_email and args.email_to and email_items:
        print(f"Sending {len(email_items)} items via email to {args.email_to} (>= {args.email_threshold}% off)...")
        send_sale_email(email_items, to_address=args.email_to, creator_name="The Car Mom")
    elif not args.no_email and args.email_to and not email_items:
        print(f"No items at {args.email_threshold}%+ off — skipping email.")


if __name__ == "__main__":
    main()
