"""
Email delivery for sale items via Gmail SMTP.

Sends a formatted HTML email with product images, prices, discounts,
and deep links — one email per recipient.

Required .env variables:
    GMAIL_ADDRESS      your Gmail address (the sender)
    GMAIL_APP_PASSWORD 16-character Google App Password (NOT your Gmail password)

Usage (standalone test):
    python3 email_notify.py --to recipient@example.com
"""

import argparse
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import date

from dotenv import load_dotenv

# Brand colors from The Car Mom brand guide
BRAND_BLUE    = "#2860A3"
LIGHT_BLUE    = "#B2CBDC"
OFF_WHITE     = "#F9F8F8"
WARM_GRAY     = "#E8E5E2"
DARK_SLATE    = "#4C5966"
WHITE         = "#FFFFFF"

# Logo — attached as a CID image so it works in Gmail and all major email clients
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "tcm_logo.png")
_LOGO_CID  = "tcm_logo"

def _logo_bytes():
    """Return raw PNG bytes for the logo, or None if file is missing."""
    try:
        with open(_LOGO_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _discount_label(pct_off: int) -> str:
    if pct_off >= 40:
        return "🔥 Hot Deal"
    if pct_off >= 25:
        return "🏷 Great Deal"
    return "💰 On Sale"


def _item_html(item) -> str:
    """Render one sale item as an HTML table row block."""
    image_block = ""
    if item.image_url:
        image_block = f'<img src="{item.image_url}" alt="product" width="120" style="border-radius:6px;">'

    label = _discount_label(item.pct_off)

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px; border:1px solid {LIGHT_BLUE}; border-radius:8px; overflow:hidden;">
      <tr>
        <td width="136" valign="top" style="padding:16px; background:{WARM_GRAY};">
          {image_block}
        </td>
        <td valign="top" style="padding:16px; background:{WHITE};">
          <p style="margin:0 0 6px 0; font-size:15px; font-weight:600; color:#111827;">{item.title[:100]}</p>
          <p style="margin:0 0 8px 0;">
            <span style="font-size:20px; font-weight:700; color:{BRAND_BLUE};">${item.current_price:.2f}</span>
            &nbsp;
            <span style="font-size:14px; color:{DARK_SLATE}; text-decoration:line-through;">${item.original_price:.2f}</span>
            &nbsp;
            <span style="font-size:13px; font-weight:600; color:#dc2626;">{item.pct_off}% off</span>
          </p>
          <p style="margin:0 0 12px 0;">
            <span style="display:inline-block; padding:2px 10px; background:{LIGHT_BLUE}; color:{BRAND_BLUE}; font-size:12px; font-weight:600; border-radius:999px;">{label}</span>
          </p>
          <p style="margin:0 0 8px 0;">
            <a href="{item.affiliate_url}" style="display:inline-block; padding:8px 18px; background:{BRAND_BLUE}; color:#fff; font-size:13px; font-weight:600; text-decoration:none; border-radius:6px;">View on Amazon</a>
          </p>
          <p style="margin:0 0 4px 0; font-size:11px; color:{DARK_SLATE}; font-weight:600;">Deep link (hold to copy):</p>
          <p style="margin:0; font-size:11px; color:{BRAND_BLUE}; word-break:break-all;">{item.deep_link}</p>
        </td>
      </tr>
    </table>
    """


def build_html(sale_items: list, creator_name: str, has_logo: bool = True) -> str:
    today = date.today().strftime("%B %d, %Y")
    items_html = "\n".join(_item_html(item) for item in sale_items)

    if has_logo:
        logo_tag = f'<img src="cid:{_LOGO_CID}" alt="{creator_name}" width="180" style="display:block; margin:0 auto;">'
    else:
        logo_tag = f'<span style="font-size:22px; font-weight:700; color:{WHITE};">{creator_name}</span>'

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sale Items — {today}</title>
</head>
<body style="margin:0; padding:0; background:{OFF_WHITE}; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="620" cellpadding="0" cellspacing="0" style="background:{WHITE}; border-radius:12px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.1);">

          <!-- Header -->
          <tr>
            <td style="background:{BRAND_BLUE}; padding:28px 32px; text-align:center;">
              {logo_tag}
              <p style="margin:14px 0 0 0; font-size:14px; color:rgba(255,255,255,.85);">{today} &nbsp;·&nbsp; {len(sale_items)} items on sale</p>
            </td>
          </tr>

          <!-- Items -->
          <tr>
            <td style="padding:24px 32px; background:{OFF_WHITE};">
              {items_html}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px; background:{WARM_GRAY}; border-top:1px solid {LIGHT_BLUE};">
              <p style="margin:0; font-size:12px; color:{DARK_SLATE}; text-align:center;">
                Sent by The Car Mom Bot · Affiliate links tagged kellystumpe-20
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_sale_email(
    sale_items: list,
    to_address: str,
    creator_name: str = "The Car Mom",
    from_address: str = GMAIL_ADDRESS,
) -> bool:
    """
    Send a sale digest email via Gmail SMTP.

    Returns True on success, False on failure.
    """
    if not from_address or not GMAIL_APP_PASSWORD:
        print("ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env", file=sys.stderr)
        return False

    if not sale_items:
        print("No sale items — skipping email.")
        return True

    today = date.today().strftime("%B %d, %Y")
    subject = f"{creator_name} — {len(sale_items)} Items on Sale Today ({today})"

    # Outer container: "related" allows HTML part to reference CID images
    logo_data = _logo_bytes()
    has_logo = logo_data is not None

    msg_root = MIMEMultipart("related")
    msg_root["Subject"] = subject
    msg_root["From"]    = f"The Car Mom Bot <{from_address}>"
    msg_root["To"]      = to_address

    # Inner alternative (plain text + HTML)
    msg_alt = MIMEMultipart("alternative")
    msg_root.attach(msg_alt)

    # Plain-text fallback
    plain_lines = [f"{creator_name} Sale Report — {today}", ""]
    for item in sale_items:
        plain_lines.append(f"• {item.title[:80]}")
        plain_lines.append(f"  ${item.current_price:.2f} (was ${item.original_price:.2f}) — {item.pct_off}% off")
        plain_lines.append(f"  Deep link: {item.deep_link}")
        plain_lines.append(f"  Web link:  {item.affiliate_url}")
        plain_lines.append("")
    plain_text = "\n".join(plain_lines)

    msg_alt.attach(MIMEText(plain_text, "plain"))
    msg_alt.attach(MIMEText(build_html(sale_items, creator_name, has_logo=has_logo), "html"))

    # Attach logo as CID image (works in Gmail, Apple Mail, Outlook)
    if has_logo:
        logo_mime = MIMEImage(logo_data, _subtype="png")
        logo_mime.add_header("Content-ID", f"<{_LOGO_CID}>")
        logo_mime.add_header("Content-Disposition", "inline", filename="tcm_logo.png")
        msg_root.attach(logo_mime)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(from_address, GMAIL_APP_PASSWORD)
            smtp.sendmail(from_address, to_address, msg_root.as_string())
        print(f"  Email sent to {to_address}")
        return True
    except smtplib.SMTPAuthenticationError:
        print(
            "ERROR: Gmail authentication failed.\n"
            "  Make sure GMAIL_APP_PASSWORD in .env is a Google App Password\n"
            "  (16 characters, generated at myaccount.google.com/apppasswords)\n"
            "  — NOT your regular Gmail password.",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", required=True, help="Recipient email address")
    args = parser.parse_args()

    # Smoke test with two fake items
    from dataclasses import dataclass

    @dataclass
    class FakeSaleItem:
        asin: str
        title: str
        current_price: float
        original_price: float
        pct_off: int
        deal_type: object
        affiliate_url: str
        deep_link: str
        image_url: object

    test_items = [
        FakeSaleItem(
            asin="B0CV64341S",
            title="STANLEY Quencher H2.0 Tumbler with Handle and Straw 30 oz",
            current_price=34.00,
            original_price=40.00,
            pct_off=15,
            deal_type=None,
            affiliate_url="https://www.amazon.com/dp/B0CV64341S?tag=kellystumpe-20&linkCode=ogi&th=1&psc=1",
            deep_link="amzn://dp/B0CV64341S?tag=kellystumpe-20&linkCode=ogi&th=1&psc=1",
            image_url="https://m.media-amazon.com/images/I/31SO4DG9ynL._SL160_.jpg",
        ),
        FakeSaleItem(
            asin="B0DDL8WGH5",
            title="DJI Mic Mini (2 TX + 1 RX + Charging Case), Wireless Lavalier Mic",
            current_price=79.00,
            original_price=99.00,
            pct_off=20,
            deal_type=None,
            affiliate_url="https://www.amazon.com/dp/B0DDL8WGH5?tag=kellystumpe-20&linkCode=ogi&th=1&psc=1",
            deep_link="amzn://dp/B0DDL8WGH5?tag=kellystumpe-20&linkCode=ogi&th=1&psc=1",
            image_url="https://m.media-amazon.com/images/I/31KzYDU8pvL._SL160_.jpg",
        ),
    ]

    print(f"Sending test email to {args.to}...")
    ok = send_sale_email(test_items, to_address=args.to)
    if ok:
        print("Done — check your inbox.")
