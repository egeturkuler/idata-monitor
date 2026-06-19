"""
iDATA Duyurular Monitor
-----------------------
Checks https://www.idata.com.tr/ita/tr/p/duyurular for new announcements
and sends an email notification when new ones are detected.

State is stored in state.json (committed back to repo by GitHub Actions).

HTML structure (verified from live page source):
  Each announcement is a pair of sibling divs inside .entry-post:
    <div class="col-sm-2">  ← date block
      <p>...Nisan 2026</p>
      <p class="col-sm-12">22</p>
    </div>
    <div class="col-sm-10">  ← content block
      <h6>Title here</h6>
      <p>Excerpt here...</p>
      <p class="btn-service"><a href="/ita/tr/news/slug">Devamını Oku</a></p>
    </div>
"""

import os
import json
import hashlib
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Configuration ────────────────────────────────────────────────────────────

URL = "https://www.idata.com.tr/ita/tr/p/duyurular"
BASE_URL = "https://www.idata.com.tr"
STATE_FILE = "state.json"

# Recipients — comma-separated list from env var, e.g. "a@x.com,b@x.com"
RECIPIENTS = [e.strip() for e in os.environ.get("NOTIFY_EMAILS", "").split(",") if e.strip()]

# SMTP credentials from env vars
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
_smtp_port_str = os.environ.get("SMTP_PORT") or "587"
SMTP_PORT = int(_smtp_port_str)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
FROM_NAME  = "iDATA Duyuru Monitoru"

# ── Scraping ─────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def fetch_announcements():
    """
    Scrape the announcements page and return a list of dicts:
      { "id": <md5 of url>, "date": "22 Nisan 2026", "title": "...", "excerpt": "...", "url": "..." }

    Page structure (from verified HTML source):
      Inside <div class="entry-post">, announcements are rendered as alternating:
        <div class="col-sm-2">  → date (month text + day number)
        <div class="col-sm-10"> → title (h6) + excerpt (p) + link (.btn-service a)
      Separated by <div class="col-sm-12"><hr></div>
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    # Pre-visit homepage to acquire session cookies (helps bypass bot checks)
    try:
        session.get(BASE_URL + "/ita/tr", timeout=15)
    except Exception:
        pass

    resp = session.get(URL, timeout=25)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    announcements = []

    # Find the entry-post div that contains the announcements list
    entry_post = soup.find("div", class_="entry-post")
    if not entry_post:
        print("   WARNING: Could not find .entry-post container — page structure may have changed.")
        return announcements

    # Collect all col-sm-2 (date) and col-sm-10 (content) divs in order
    date_divs    = entry_post.find_all("div", class_="col-sm-2")
    content_divs = entry_post.find_all("div", class_="col-sm-10")

    # Zip them together — each pair is one announcement
    for date_div, content_div in zip(date_divs, content_divs):
        # ── Date ──────────────────────────────────────────────────────────
        # Red box: e.g. "Nisan 2026"   Gray box: e.g. "22"
        ps = date_div.find_all("p")
        month_year = ps[0].get_text(strip=True) if len(ps) > 0 else ""
        day        = ps[1].get_text(strip=True) if len(ps) > 1 else ""

        # Clean up icon text that gets pulled in with the calendar icon
        month_year = month_year.replace("\xa0", "").strip()
        # FontAwesome icon renders as text — strip anything before the first letter of the month
        # e.g. " Nisan 2026" after icon
        import re
        month_year = re.sub(r"^[^A-Za-zÀ-ÖØ-öø-ÿ]+", "", month_year).strip()
        date_str = f"{day} {month_year}".strip()

        # ── Title ──────────────────────────────────────────────────────────
        h6 = content_div.find("h6")
        title = h6.get_text(strip=True) if h6 else ""

        # ── Excerpt ────────────────────────────────────────────────────────
        # First <p> that is NOT the btn-service paragraph
        excerpt = ""
        for p in content_div.find_all("p"):
            if "btn-service" not in p.get("class", []):
                text = p.get_text(strip=True)
                if text and text != title:
                    excerpt = text
                    break

        # ── URL ────────────────────────────────────────────────────────────
        btn_service = content_div.find("p", class_="btn-service")
        link = btn_service.find("a") if btn_service else None
        href = link["href"] if link and link.get("href") else ""
        full_url = href if href.startswith("http") else BASE_URL + href

        if not title:
            continue

        uid = hashlib.md5(full_url.encode()).hexdigest()
        announcements.append({
            "id":      uid,
            "date":    date_str,
            "title":   title,
            "excerpt": excerpt,
            "url":     full_url,
        })

    return announcements


# ── State management ──────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen_ids": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(new_items):
    if not RECIPIENTS:
        print("   WARNING: No recipients configured — set NOTIFY_EMAILS env var.")
        return
    if not SMTP_USER or not SMTP_PASS:
        print("   WARNING: SMTP credentials missing — set SMTP_USER and SMTP_PASS.")
        return

    count  = len(new_items)
    subject = f"iDATA: {count} Yeni Duyuru Yayinlandi"

    # ── HTML body ──────────────────────────────────────────────────────────
    items_html = ""
    for item in new_items:
        date_line    = f'<span style="color:#c60000;font-weight:600;">{item["date"]}</span>' if item["date"] else ""
        excerpt_line = f'<p style="margin:8px 0 0;color:#555;line-height:1.5;">{item["excerpt"]}</p>' if item["excerpt"] else ""
        read_more    = (
            f'<p style="margin:10px 0 0;">'
            f'<a href="{item["url"]}" style="color:#0055a5;font-weight:bold;text-decoration:none;">'
            f'Devamini Oku &rarr;</a></p>'
        ) if item["url"] else ""

        items_html += f"""
        <div style="border-left:4px solid #c60000;padding:12px 18px;margin-bottom:22px;
                    background:#fafafa;border-radius:0 6px 6px 0;">
          {date_line}
          <h3 style="margin:4px 0 0;font-size:15px;color:#222;">{item["title"]}</h3>
          {excerpt_line}
          {read_more}
        </div>"""

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:auto;color:#333;padding:0;">

  <div style="background:#c60000;padding:18px 24px;border-radius:8px 8px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:20px;">iDATA - Yeni Duyurular</h2>
    <p style="color:#ffd0d0;margin:4px 0 0;font-size:13px;">Kontrol tarihi: {now_str}</p>
  </div>

  <div style="background:#fff;padding:24px;border:1px solid #e0e0e0;
              border-top:none;border-radius:0 0 8px 8px;">
    <p style="margin:0 0 18px;">{count} yeni duyuru yayinlandi:</p>
    {items_html}
    <hr style="border:none;border-top:1px solid #eee;margin:22px 0;">
    <p style="font-size:12px;color:#999;margin:0;">
      Bu e-posta otomatik olarak gonderilmektedir.<br>
      Kaynak: <a href="{URL}" style="color:#c60000;">{URL}</a>
    </p>
  </div>

</body></html>"""

    # ── Plain text fallback ────────────────────────────────────────────────
    plain = f"iDATA - {count} yeni duyuru:\n\n"
    for item in new_items:
        plain += f"[{item['date']}] {item['title']}\n"
        if item["excerpt"]:
            plain += f"{item['excerpt'][:200]}\n"
        plain += f"{item['url']}\n\n"
    plain += f"\nKaynak: {URL}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{FROM_NAME} <{SMTP_USER}>"
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, RECIPIENTS, msg.as_string())

    print(f"   Email sent to: {', '.join(RECIPIENTS)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Checking {URL} ...")

    try:
        announcements = fetch_announcements()
    except Exception as e:
        print(f"   FAILED to fetch page: {e}")
        sys.exit(1)

    print(f"   Found {len(announcements)} announcement(s) on page.")
    for a in announcements:
        print(f"      [{a['date']}] {a['title'][:70]}")

    state    = load_state()
    seen_ids = set(state.get("seen_ids", []))
    new_items = [a for a in announcements if a["id"] not in seen_ids]

    if not new_items:
        print("   No new announcements. Nothing to send.")
        state["last_checked"] = datetime.now().isoformat()
        save_state(state)
        return

    print(f"   NEW: {len(new_items)} announcement(s) detected!")
    for item in new_items:
        print(f"      -> [{item['date']}] {item['title'][:70]}")

    email_error = None
    try:
        send_email(new_items)
    except Exception as e:
        email_error = e
        print(f"   Email FAILED: {e}")

    # Save updated state regardless — avoids duplicate alerts on next run
    state["seen_ids"]       = [a["id"] for a in announcements]
    state["last_checked"]   = datetime.now().isoformat()
    state["last_new_count"] = len(new_items)
    save_state(state)
    print("   State saved.")

    if email_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
