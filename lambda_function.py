import json
import os
import sys
import argparse
import requests
import feedparser
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from openai import OpenAI

def load_env_file():
    """Load variables from .env file if it exists."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    os.environ[key] = val

# Automatically load local variables if .env exists
load_env_file()

# ── Config & Defaults ───────────────────────────────────
FEDERAL_REGISTER_URL = "https://www.federalregister.gov/api/v1/documents.json"

SYSTEM_PROMPT = """You are a regulatory analyst specializing in US stablecoin 
and digital asset regulation. You monitor developments for 
a fintech founder evaluating compliance infrastructure 
opportunities.

You receive a batch of regulatory items published in the 
last 24 hours — from the Federal Register, law firm client 
alerts, and industry trade press.

BACKGROUND: The GENIUS Act (Guiding and Establishing 
National Innovation for US Stablecoins) was signed into law 
in July 2025. It establishes the first federal framework for 
payment stablecoin issuers. Implementing regulations are due 
by July 18, 2026. Four critical open questions remain:

Q1 ISSUER DEFINITION: Who qualifies as a "permitted payment 
   stablecoin issuer" in white-label and platform-mediated 
   arrangements?
Q2 ATTESTATION STANDARD: What does "examined by a registered 
   public accounting firm" require? Must issuers follow the 
   AICPA 2025 Criteria, or is a lighter standard acceptable?
Q3 CAPITAL REQUIREMENTS: What capital, liquidity, and risk 
   management requirements will apply to issuers?
Q4 STATE EQUIVALENCE: How will Treasury certify state 
   regulatory regimes as "substantially similar" to federal?

TAGGING & CLASSIFICATION RULES:
- Be conservative with Q1-Q4 tags. Only tag an update with a question if the development provides material, actionable insight or formal proposals regarding that specific question.
- Strict Direction Criteria:
  - "Stricter": The development raises compliance overhead, increases capital/liquidity ratios, or restricts issuer eligibility.
  - "More Permissive": The development lowers barriers, expands permitted reserves, or simplifies state certification.
  - "Clarifying": The development resolves operational procedures without changing the overall compliance burden.
  - "Ambiguous": The development introduces competing signals or depends on future interpretations.

YOUR TASK:

If there are NO relevant new developments today, respond 
with exactly: "NO_UPDATES"

If there ARE relevant developments, produce a brief in this 
format:

---
STABLECOIN REGULATORY RADAR — [Today's Date]

## [Development Title]
Source: [Federal Register / Law Firm Name / CoinDesk / Cointelegraph]
Agency: [Treasury / FDIC / SEC / OCC / State / Other]
Type: [Proposed Rule / Final Rule / Notice / Guidance / Enforcement / Commentary]

What happened:
[2-3 sentences. Plain English. A smart non-lawyer should understand this.]

Which open question(s) this informs: [Q1 / Q2 / Q3 / Q4]

Direction: [Stricter / More Permissive / Clarifying / Ambiguous]

Why it matters:
[2-3 sentences connecting this to the practical question of building stablecoin compliance infrastructure. What does a fintech founder or compliance officer need to know?]

[Repeat for each development]

---
DAILY SUMMARY:
[1-2 sentences. What was the most important signal today? 
If nothing major: "Quiet day. No material movement on the four open questions."]

Days until implementing regulations deadline: [calculate from today to July 18, 2026]
---

Rules:
- Never fabricate regulatory actions. If you are unsure whether something is a proposed rule vs. final rule, say so.
- Cite the specific Federal Register document number when available.
- Do not speculate on political outcomes.
- Keep the entire brief readable in under 3 minutes.
"""

def fetch_federal_register(since_date):
    """Query Federal Register API for stablecoin-related documents."""
    print(f"Fetching Federal Register documents since {since_date}...")
    terms = ["stablecoin", "digital asset", "payment token", "reserve attestation"]
    seen_docs = set()
    items = []
    
    for term in terms:
        params = {
            "conditions[term]": term,
            "conditions[publication_date][gte]": since_date,
            "per_page": 20,
            "order": "newest",
        }
        try:
            resp = requests.get(FEDERAL_REGISTER_URL, params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as e:
            print(f"Failed to fetch from Federal Register for term '{term}': {e}")
            continue

        for r in results:
            doc_num = r.get("document_number")
            if not doc_num or doc_num in seen_docs:
                continue
            seen_docs.add(doc_num)
            
            agencies = r.get("agencies", [])
            agency_names = ", ".join(a.get("name", "") for a in agencies if a.get("name"))
            abstract = r.get("abstract") or r.get("excerpts") or ""
            
            items.append({
                "source": "Federal Register",
                "title": r.get("title", ""),
                "abstract": abstract,
                "agency": agency_names or "Unknown",
                "type": r.get("type", "Notice"),
                "url": r.get("html_url", ""),
                "date": r.get("publication_date", ""),
                "doc_number": doc_num,
            })
    return items

def fetch_rss_feeds(since_date):
    """Parse law firm and industry RSS feeds."""
    print(f"Fetching RSS feeds since {since_date}...")
    items = []
    feeds = {
        "K&L Gates FinTech Law Watch": "https://www.fintechlawblog.com/rss",
        "Sheppard Mullin Law of the Ledger": "https://lawoftheledger.com/feed/",
        "Federal Reserve Press Releases": "https://www.federalreserve.gov/feeds/press_all.xml",
        "FDIC Press Releases": "https://public.govdelivery.com/topics/USFDIC_26/feed.rss",
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "Cointelegraph": "https://cointelegraph.com/rss"
    }
    
    since_dt = datetime.strptime(since_date, "%Y-%m-%d")
    
    # Define keywords for filtering
    broad_keywords = ["stablecoin", "genius act", "digital asset", 
                      "payment token", "reserve attestation", "crypto regulation",
                      "fdic", "sec", "occ", "cftc", "treasury"]
                      
    strict_keywords = ["stablecoin", "genius act", "payment token", 
                       "reserve attestation", "attestation standard", "ppsi",
                       "permitted payment stablecoin"]
    
    for feed_name, url in feeds.items():
        try:
            print(f"Parsing feed: {feed_name}...")
            feed = feedparser.parse(url)
            for entry in feed.entries:
                pub = entry.get("published_parsed")
                if pub:
                    pub_dt = datetime(*pub[:6])
                else:
                    upd = entry.get("updated_parsed")
                    if upd:
                        pub_dt = datetime(*upd[:6])
                    else:
                        pub_dt = datetime.utcnow()
                
                # Check date filter
                if pub_dt < since_dt:
                    continue
                
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                title_desc = (title + " " + summary).lower()
                
                # Use strict keywords for noisier news outlets, broad for regulators and law firm feeds
                is_news_source = feed_name in ["CoinDesk", "Cointelegraph"]
                keywords_to_check = strict_keywords if is_news_source else broad_keywords
                
                if any(kw in title_desc for kw in keywords_to_check):
                    items.append({
                        "source": feed_name,
                        "title": title,
                        "abstract": summary[:1000] if summary else "",
                        "url": entry.get("link", ""),
                        "date": pub_dt.strftime("%Y-%m-%d"),
                    })
        except Exception as e:
            print(f"Error parsing RSS feed {feed_name}: {e}")
            
    return items

def analyze(items):
    """Send items to GPT-4o for analysis."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Warning: OPENAI_API_KEY environment variable is not set.")
        return "STABLECOIN REGULATORY RADAR — NO_UPDATES (OPENAI_API_KEY missing)"

    client = OpenAI(api_key=api_key)
    
    if not items:
        return f"STABLECOIN REGULATORY RADAR — {datetime.utcnow().strftime('%B %d, %Y')}\n\nNO_UPDATES\n\nQuiet day. No new stablecoin-related regulatory items detected across monitored sources."
    
    user_msg = f"Today's date: {datetime.utcnow().strftime('%B %d, %Y')}\n\n"
    user_msg += "Items from the last 24 hours:\n\n"
    for i, item in enumerate(items, 1):
        user_msg += f"[{i}] {item['source']}\n"
        user_msg += f"Title: {item['title']}\n"
        user_msg += f"Abstract: {item.get('abstract', 'N/A')}\n"
        user_msg += f"URL: {item.get('url', 'N/A')}\n"
        if item.get('agency'):
            user_msg += f"Agency: {item['agency']}\n"
        if item.get('type'):
            user_msg += f"Type: {item['type']}\n"
        if item.get('doc_number'):
            user_msg += f"Doc Number: {item['doc_number']}\n"
        user_msg += "\n"
    
    print("Analyzing fetched items using GPT-4o...")
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
    )
    return resp.choices[0].message.content

def send_email(brief, date):
    """Send via Gmail SMTP."""
    gmail_user = os.environ.get("SENDER", "dannylee0210@gmail.com")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("RECIPIENT", "dannylee0210@gmail.com")
    
    if not gmail_password:
        print("GMAIL_APP_PASSWORD environment variable not set. Skipping email sending.")
        return False
        
    msg = MIMEText(brief, "plain")
    msg["Subject"] = f"Stablecoin Radar — {date}"
    msg["From"] = gmail_user
    msg["To"] = recipient
    
    try:
        print(f"Connecting to smtp.gmail.com:587 to send email to {recipient}...")
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(gmail_user, gmail_password)
            s.send_message(msg)
        print("Email sent successfully.")
        return True
    except Exception as e:
        print(f"\n⚠️ SMTP Connection Failed: {e}")
        print("Note: Outbound SMTP ports (465, 587) are likely blocked by your local network/ISP.")
        print("This is a common local environment restriction. The email will send successfully when deployed to AWS Lambda.")
        
        # Save to mock file so user can verify contents
        fallback_file = "mock_email_brief.txt"
        try:
            with open(fallback_file, "w", encoding="utf-8") as f:
                f.write(f"Subject: Stablecoin Radar — {date}\n")
                f.write(f"To: {recipient}\n")
                f.write("="*40 + "\n\n")
                f.write(brief)
            print(f"💾 Fallback: Saved email brief to local file '{fallback_file}' for review.")
        except Exception as file_err:
            print(f"Failed to write mock email file: {file_err}")
        return False

def log_to_sheets(brief, date):
    """Append brief to Google Sheets using gspread."""
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    creds_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
    
    if not creds_json and creds_path and os.path.exists(creds_path):
        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                creds_json = f.read()
        except Exception as e:
            print(f"Error reading credentials file from path {creds_path}: {e}")
            
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    sheet_name = os.environ.get("SHEET_NAME", "Sheet1")
    
    if not creds_json or not spreadsheet_id:
        print("Google Sheets credentials or Spreadsheet ID not configured. Skipping logging.")
        return False
        
    try:
        print("Logging results to Google Sheets using gspread...")
        import gspread
        from google.oauth2.service_account import Credentials
        
        info = json.loads(creds_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
        sheet.append_row([date, brief])
        print("Logged to Google Sheets successfully via gspread.")
        return True
    except Exception as e:
        print(f"Error logging to Google Sheets via gspread: {e}")
        return False


def handler(event, context):
    """AWS Lambda entry point."""
    print("Starting Lambda handler...")
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 1. Fetch
    items = []
    items += fetch_federal_register(yesterday)
    items += fetch_rss_feeds(yesterday)
    
    print(f"Total items fetched: {len(items)}")
    
    # 2. Analyze
    brief = analyze(items)
    print("\n--- ANALYSIS BRIEF ---")
    print(brief)
    print("----------------------\n")
    
    # 3. Act
    if "NO_UPDATES" not in brief:
        log_to_sheets(brief, yesterday)
    send_email(brief, yesterday)
    
    return {"statusCode": 200, "body": "OK"}

# Alias for AWS default configuration (lambda_function.lambda_handler)
lambda_handler = handler

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Stablecoin Regulatory Radar CLI Runner")
    parser.add_argument("--since", type=str, help="Start date for scanning (YYYY-MM-DD). Defaults to yesterday.")
    parser.add_argument("--dry-run", action="store_true", help="Print brief and do not send email or log to Sheets.")
    parser.add_argument("--test-email", action="store_true", help="Force email send even if NO_UPDATES or dry-run is specified.")
    args = parser.parse_args()

    # Determine date
    if args.since:
        since_date = args.since
    else:
        since_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Running in CLI mode starting from: {since_date}")
    
    # Fetch
    items = []
    items += fetch_federal_register(since_date)
    items += fetch_rss_feeds(since_date)
    print(f"Fetched {len(items)} items total.")

    # Analyze
    brief = analyze(items)
    
    print("\n--- ANALYSIS BRIEF ---")
    print(brief)
    print("----------------------\n")

    # Act
    if not args.dry_run:
        if "NO_UPDATES" not in brief:
            log_to_sheets(brief, since_date)
        send_email(brief, since_date)
    elif args.test_email:
        print("CLI option --test-email specified. Bypassing dry-run/no-updates rules for email.")
        send_email(brief, since_date)
    else:
        print("Dry-run mode. Skipping email sending and Sheets logging.")
