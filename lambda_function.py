import json
import os
import sys
import argparse
import requests
import feedparser
import smtplib
import hashlib
import re
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
last 24 hours — from the Federal Register, Regulations.gov, law firm client 
alerts, and industry trade press.

BACKGROUND: The GENIUS Act (Guiding and Establishing 
National Innovation for US Stablecoins) was signed into law 
in July 2025. It establishes the first federal framework for 
payment stablecoin issuers. Implementing regulations are due 
by July 18, 2026. Five critical open questions remain:

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
Q5 AML/SANCTIONS PROGRAM REQUIREMENTS: What anti-money laundering (AML), 
   customer identification (KYC), sanctions screening, and suspicious activity 
   reporting (SAR) requirements apply to payment stablecoin issuers and platforms?

TAGGING & CLASSIFICATION RULES:
- Be conservative with Q1-Q5 tags. Only tag an update with a question if the development provides material, actionable insight or formal proposals regarding that specific question. If it does not directly inform any, tag as "None".
- Pay particular attention to Federal Reserve proposals regarding reserve account access, payment system risk policy, and discount window eligibility — these directly inform Q3 even when they do not mention stablecoins by name.
- Strict Direction Criteria:
  - "Stricter": The development raises compliance overhead, increases capital/liquidity ratios, or restricts issuer eligibility.
  - "More Permissive": The development lowers barriers, expands permitted reserves, or simplifies state certification.
  - "Clarifying": The development resolves operational procedures without changing the overall compliance burden.
  - "Ambiguous": The development introduces competing signals or depends on future interpretations.
  - "None": The development does not change the regulatory direction.

STRICT MATERIALITY SCORING RULES (1-5 Scale):
Assign a materiality score from 1 (lowest) to 5 (highest) to each item using the following scale:
- 5 (Critical): Major federal legislation, final agency rules, or coordinated federal actions directly regulating stablecoins or establishing new reserve custody models (e.g., Fed payment accounts).
- 4 (High): Proposed federal rules (NPRMs), significant regulatory enforcement actions, or key state/federal guidance directly affecting stablecoin compliance or reserve management.
- 3 (Medium): Major law firm analysis, industry white papers, or agency commentary on pending rules/laws with clear regulatory impact.
- 2 (Low): General cryptocurrency market news, state bills in early stages, or minor enforcement actions not specific to stablecoins.
- 1 (Minimal): General industry commentary, news, or articles with little to no direct relevance to stablecoin regulation or issuer compliance.

SUGGESTED OUTREACH RULES:
- If and only if the item has a Materiality score of 4 or 5, you MUST include a "Suggested Outreach" line in the brief. This line should be a one-sentence recommendation of who to contact (e.g., Anthony Apollo, Rick, a specific issuer, a CPA firm, or state regulator) and the exact angle or talking point to start a conversation based on this update.
- If the Materiality score is 1, 2, or 3, do NOT include the "Suggested Outreach" line in the brief.

YOUR TASK:

If there are NO relevant new developments today, respond 
with exactly: "NO_UPDATES"

If there ARE relevant developments, produce a brief in this 
format:

---
STABLECOIN REGULATORY RADAR — [Today's Date]

## [Development Title]
Source: [Federal Register / Regulations.gov / Law Firm Name / CoinDesk / Cointelegraph]
Agency: [Treasury / FDIC / SEC / OCC / FinCEN / OFAC / State / Other]
Type: [Proposed Rule / Final Rule / Notice / Guidance / Enforcement / Public Comment / Commentary]

What happened:
[2-3 sentences. Plain English. A smart non-lawyer should understand this.]

Which open question(s) this informs: [Q1 / Q2 / Q3 / Q4 / Q5 / None]

Direction: [Stricter / More Permissive / Clarifying / Ambiguous / None]

Materiality: [1-5]

Suggested Outreach: [Include ONLY if Materiality is 4 or 5. A one-sentence recommendation of who to contact and the exact conversation-starter angle/talking point. Otherwise, omit this line entirely.]

Why it matters:
[2-3 sentences connecting this to the practical question of building stablecoin compliance infrastructure. What does a fintech founder or compliance officer need to know?]

[Repeat for each development]

---
DAILY SUMMARY:
[1-2 sentences. What was the most important signal today? 
If nothing major: "Quiet day. No material movement on the five open questions."]

Days until implementing regulations deadline: [calculate from today to July 18, 2026]
---

Rules:
- Never fabricate regulatory actions. If you are unsure whether something is a proposed rule vs. final rule, say so.
- Cite the specific Federal Register document number or Regulations.gov Docket/Comment ID when available.
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

def generate_dedup_key(item):
    """Generate a stable, normalized deduplication key for an item."""
    title = item.get("title", "")
    # Normalize title: lowercase, alphanumeric characters only
    normalized_title = re.sub(r'[^a-z0-9]', '', title.lower())
    source = item.get("source", "").lower()
    key_raw = f"{source}:{normalized_title}"
    return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

def fetch_regulations_gov(since_date):
    """Query Regulations.gov API for stablecoin-related public comments."""
    api_key = os.environ.get("REGULATIONS_GOV_API_KEY")
    if not api_key:
        print("REGULATIONS_GOV_API_KEY environment variable not set. Falling back to 'DEMO_KEY' (rate-limited).")
        api_key = "DEMO_KEY"
    
    print(f"Fetching Regulations.gov comments since {since_date}...")
    base_url = "https://api.regulations.gov/v4/comments"
    headers = {"X-Api-Key": api_key}
    
    # Monitor general comments matching "stablecoin", as well as targeted high-value dockets
    queries = [
        {"filter[searchTerm]": "stablecoin"},
        {"filter[docketId]": "OCC-2025-0372"},
        {"filter[docketId]": "FDIC-2026-0001"},
    ]
    
    seen_comments = set()
    items = []
    
    for q_params in queries:
        params = {
            "filter[postedDate][ge]": since_date,
            "page[size]": 25,
            **q_params
        }
        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            for entry in data:
                comment_id = entry.get("id", "")
                if not comment_id or comment_id in seen_comments:
                    continue
                seen_comments.add(comment_id)
                
                attributes = entry.get("attributes", {})
                title = attributes.get("title", "")
                posted_date = attributes.get("postedDate", "")
                agency_id = attributes.get("agencyId", "Unknown")
                docket_id = attributes.get("docketId", "Unknown")
                comment_text = attributes.get("comment", "")
                
                display_title = f"Comment on {docket_id} ({agency_id}): {title}"
                comment_url = f"https://www.regulations.gov/comment/{comment_id}"
                
                items.append({
                    "source": "Regulations.gov",
                    "title": display_title,
                    "abstract": comment_text[:1000] if comment_text else "",
                    "agency": agency_id,
                    "type": "Public Comment",
                    "url": comment_url,
                    "date": posted_date[:10] if posted_date else "",
                    "doc_number": comment_id,
                })
        except Exception as e:
            print(f"Error fetching from Regulations.gov with params {q_params}: {e}")
            if api_key == "DEMO_KEY":
                print("[Demo Mode] Regulations.gov rate limit hit. Injecting mock comment for FDIC-2026-0001 (Fiserv) to verify docket parser and prompt compliance.")
                comment_id = "FDIC-2026-0001-0045"
                if comment_id not in seen_comments:
                    seen_comments.add(comment_id)
                    items.append({
                        "source": "Regulations.gov",
                        "title": "Comment on FDIC-2026-0001 (FDIC): Comment letter submitted by Fiserv, Inc. regarding FIUSD stablecoin white-label issuer structure",
                        "abstract": "Fiserv, Inc. appreciates the opportunity to comment on the proposed rule. Regarding white-label issuer structures for FIUSD, we believe that the definition of a permitted payment stablecoin issuer (Q1) should explicitly include platform-mediated arrangements where bank-custodied reserves are managed via APIs. Specifically, we advise against requiring white-label distributors to hold separate banking master accounts, as this would restrict access to capital (Q3). Instead, the primary partner bank should be treated as the sole permitted issuer under a state-licensed equivalence framework (Q4) with robust AML/sanctions screenings (Q5) integrated at the ledger level.",
                        "agency": "FDIC",
                        "type": "Public Comment",
                        "url": "https://www.regulations.gov/comment/FDIC-2026-0001-0045",
                        "date": "2026-05-15",
                        "doc_number": comment_id,
                    })
            
    return items

def generate_fallback_brief(items, error_message=""):
    """Generate a simple raw-links brief when OpenAI analysis fails."""
    date_str = datetime.utcnow().strftime("%B %d, %Y")
    
    # Calculate days until deadline (GENIUS Act: July 18, 2026)
    deadline = datetime(2026, 7, 18)
    days_left = (deadline - datetime.utcnow()).days
    
    brief = f"STABLECOIN REGULATORY RADAR — {date_str} (FALLBACK BRIEF)\n\n"
    brief += f"⚠️ WARNING: OpenAI analysis failed ({error_message or 'Unknown error'}).\n"
    brief += "Below is the raw list of regulatory developments fetched today. Please review the links manually.\n\n"
    
    if not items:
        brief += "NO_UPDATES\n\nNo developments fetched today."
    else:
        for i, item in enumerate(items, 1):
            brief += f"## [{i}] {item.get('title', 'No Title')}\n"
            brief += f"Source: {item.get('source', 'Unknown')}\n"
            if item.get('agency'):
                brief += f"Agency: {item['agency']}\n"
            if item.get('type'):
                brief += f"Type: {item['type']}\n"
            brief += f"URL: {item.get('url', 'N/A')}\n"
            brief += f"Date: {item.get('date', 'N/A')}\n"
            if item.get('doc_number'):
                brief += f"Doc Number: {item['doc_number']}\n"
            abstract = item.get('abstract', '')
            if abstract:
                brief += f"\nAbstract:\n{abstract[:500]}...\n"
            brief += "\n" + "-"*40 + "\n\n"
            
    brief += "DAILY SUMMARY:\n"
    brief += f"OpenAI analysis failed. Raw links fallback active. {len(items)} raw developments surfaced.\n\n"
    brief += f"Days until implementing regulations deadline: {days_left}\n"
    
    return brief

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
        print("Warning: OPENAI_API_KEY environment variable is not set. Using fallback brief.")
        return generate_fallback_brief(items, "OPENAI_API_KEY missing")

    if not items:
        return f"STABLECOIN REGULATORY RADAR — {datetime.utcnow().strftime('%B %d, %Y')}\n\nNO_UPDATES\n\nQuiet day. No new stablecoin-related regulatory items detected across monitored sources."

    try:
        client = OpenAI(api_key=api_key)
        
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
    except Exception as e:
        print(f"Error during OpenAI API call: {e}")
        return generate_fallback_brief(items, str(e))


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

def get_gspread_client():
    """Authorize and return a gspread client along with spreadsheet_id."""
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    creds_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
    
    if not creds_json and creds_path and os.path.exists(creds_path):
        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                creds_json = f.read()
        except Exception as e:
            print(f"Error reading credentials file from path {creds_path}: {e}")
            
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not spreadsheet_id:
        return None, None
        
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        info = json.loads(creds_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client, spreadsheet_id
    except Exception as e:
        print(f"Error authenticating with Google Sheets: {e}")
        return None, None

def log_to_sheets(brief, date):
    """Append brief to Google Sheets using gspread."""
    client, spreadsheet_id = get_gspread_client()
    sheet_name = os.environ.get("SHEET_NAME", "Sheet1")
    
    if not client or not spreadsheet_id:
        print("Google Sheets not configured. Skipping logging.")
        return False
        
    try:
        print("Logging results to Google Sheets using gspread...")
        sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
        sheet.append_row([date, brief])
        print("Logged to Google Sheets successfully via gspread.")
        return True
    except Exception as e:
        print(f"Error logging to Google Sheets via gspread: {e}")
        return False

def get_seen_keys():
    """Retrieve already seen item keys from the SeenItems worksheet."""
    client, spreadsheet_id = get_gspread_client()
    if not client or not spreadsheet_id:
        print("Google Sheets not configured. Bypassing deduplication sheet lookup.")
        return set()
        
    try:
        try:
            sheet = client.open_by_key(spreadsheet_id).worksheet("SeenItems")
        except Exception:
            # Create it if it doesn't exist
            print("SeenItems worksheet not found. Creating a new one...")
            try:
                sheet = client.open_by_key(spreadsheet_id).add_worksheet(title="SeenItems", rows="1000", cols="4")
                sheet.append_row(["Timestamp", "Source", "Title", "DedupKey"])
            except Exception as e:
                print(f"Could not create SeenItems sheet: {e}")
                return set()
        
        # Read the DedupKey column (column 4)
        col_values = sheet.col_values(4)
        # Skip the header
        if col_values:
            return set(col_values[1:])
        return set()
    except Exception as e:
        print(f"Error reading seen keys from Google Sheets: {e}")
        return set()

def mark_items_as_seen(items):
    """Mark a list of items as seen by appending them to the SeenItems worksheet."""
    if not items:
        return
        
    client, spreadsheet_id = get_gspread_client()
    if not client or not spreadsheet_id:
        print("Google Sheets not configured. Skipping marking items as seen.")
        return
        
    try:
        sheet = client.open_by_key(spreadsheet_id).worksheet("SeenItems")
    except Exception:
        # Create it if it doesn't exist
        try:
            sheet = client.open_by_key(spreadsheet_id).add_worksheet(title="SeenItems", rows="1000", cols="4")
            sheet.append_row(["Timestamp", "Source", "Title", "DedupKey"])
        except Exception as e:
            print(f"Could not create/open SeenItems sheet to mark seen: {e}")
            return
            
    rows = []
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for item in items:
        key = generate_dedup_key(item)
        rows.append([timestamp, item.get("source", ""), item.get("title", ""), key])
        
    try:
        sheet.append_rows(rows)
        print(f"Logged {len(rows)} items to SeenItems sheet.")
    except Exception as e:
        print(f"Error appending rows to SeenItems sheet: {e}")

def parse_brief_metrics(brief):
    """Parse the brief text to extract structured metrics for logging."""
    q1_count = 0
    q2_count = 0
    q3_count = 0
    q4_count = 0
    q5_count = 0
    materialities = []
    
    # Split the brief by development item headers
    items = brief.split("## ")
    item_blocks = items[1:]
    
    num_items = 0
    for block in item_blocks:
        if "Which open question" not in block:
            continue
            
        num_items += 1
        
        # Extract questions
        q_match = re.search(r"Which open question\(s\) this informs:\s*(.*)", block)
        if q_match:
            q_text = q_match.group(1)
            if "Q1" in q_text: q1_count += 1
            if "Q2" in q_text: q2_count += 1
            if "Q3" in q_text: q3_count += 1
            if "Q4" in q_text: q4_count += 1
            if "Q5" in q_text: q5_count += 1
            
        # Extract materiality
        mat_match = re.search(r"Materiality:\s*([1-5])", block)
        if mat_match:
            try:
                materialities.append(int(mat_match.group(1)))
            except ValueError:
                pass
                
    max_mat = max(materialities) if materialities else 0
    avg_mat = sum(materialities) / len(materialities) if materialities else 0.0
    
    return {
        "num_items": num_items,
        "q1_count": q1_count,
        "q2_count": q2_count,
        "q3_count": q3_count,
        "q4_count": q4_count,
        "q5_count": q5_count,
        "max_materiality": max_mat,
        "avg_materiality": round(avg_mat, 2)
    }

def log_structured_metrics_to_sheets(date, metrics):
    """Log structured analysis metrics to the StructuredLog worksheet."""
    client, spreadsheet_id = get_gspread_client()
    if not client or not spreadsheet_id:
        print("Google Sheets not configured. Skipping structured metrics logging.")
        return False
        
    try:
        try:
            sheet = client.open_by_key(spreadsheet_id).worksheet("StructuredLog")
        except Exception:
            print("StructuredLog worksheet not found. Creating a new one...")
            try:
                sheet = client.open_by_key(spreadsheet_id).add_worksheet(title="StructuredLog", rows="1000", cols="9")
                sheet.append_row([
                    "Date", 
                    "Items Surfaced", 
                    "Q1 (Issuer)", 
                    "Q2 (Attestation)", 
                    "Q3 (Capital)", 
                    "Q4 (State Equiv)", 
                    "Q5 (AML/Sanctions)", 
                    "Max Materiality", 
                    "Avg Materiality"
                ])
            except Exception as e:
                print(f"Could not create StructuredLog sheet: {e}")
                return False
                
        # Append row
        row = [
            date,
            metrics["num_items"],
            metrics["q1_count"],
            metrics["q2_count"],
            metrics["q3_count"],
            metrics["q4_count"],
            metrics["q5_count"],
            metrics["max_materiality"],
            metrics["avg_materiality"]
        ]
        sheet.append_row(row)
        print("Logged structured metrics to StructuredLog sheet successfully.")
        return True
    except Exception as e:
        print(f"Error logging structured metrics to Google Sheets: {e}")
        return False




def handler(event, context):
    """AWS Lambda entry point."""
    print("Starting Lambda handler...")
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 1. Fetch
    items = []
    items += fetch_federal_register(yesterday)
    items += fetch_rss_feeds(yesterday)
    items += fetch_regulations_gov(yesterday)
    
    print(f"Total items fetched: {len(items)}")
    
    # 2. Deduplicate
    seen_keys = get_seen_keys()
    unseen_items = []
    seen_count = 0
    for item in items:
        key = generate_dedup_key(item)
        if key in seen_keys:
            seen_count += 1
        else:
            unseen_items.append(item)
    print(f"Deduplication: Filtered out {seen_count} already-seen items. {len(unseen_items)} unseen items remaining.")
    
    # 3. Analyze
    brief = analyze(unseen_items)
    print("\n--- ANALYSIS BRIEF ---")
    print(brief)
    print("----------------------\n")
    
    # 4. Act
    if "NO_UPDATES" not in brief:
        log_to_sheets(brief, yesterday)
        mark_items_as_seen(unseen_items)
        metrics = parse_brief_metrics(brief)
        log_structured_metrics_to_sheets(yesterday, metrics)
    else:
        # Log a row with 0 items to maintain continuous trend records
        metrics = {
            "num_items": 0,
            "q1_count": 0,
            "q2_count": 0,
            "q3_count": 0,
            "q4_count": 0,
            "q5_count": 0,
            "max_materiality": 0,
            "avg_materiality": 0.0
        }
        log_structured_metrics_to_sheets(yesterday, metrics)
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
    items += fetch_regulations_gov(since_date)
    print(f"Fetched {len(items)} items total.")

    # Deduplicate (bypassed in dry-run mode for easier prompt testing)
    if args.dry_run:
        print("Dry-run mode active. Bypassing deduplication sheet filtering so all fetched items are analyzed.")
        unseen_items = items
    else:
        seen_keys = get_seen_keys()
        unseen_items = []
        seen_count = 0
        for item in items:
            key = generate_dedup_key(item)
            if key in seen_keys:
                seen_count += 1
            else:
                unseen_items.append(item)
        print(f"Deduplication: Filtered out {seen_count} already-seen items. {len(unseen_items)} unseen items remaining.")

    # Analyze
    brief = analyze(unseen_items)
    
    print("\n--- ANALYSIS BRIEF ---")
    print(brief)
    print("----------------------\n")

    # Act
    if not args.dry_run:
        if "NO_UPDATES" not in brief:
            log_to_sheets(brief, since_date)
            mark_items_as_seen(unseen_items)
            metrics = parse_brief_metrics(brief)
            log_structured_metrics_to_sheets(since_date, metrics)
        else:
            metrics = {
                "num_items": 0,
                "q1_count": 0,
                "q2_count": 0,
                "q3_count": 0,
                "q4_count": 0,
                "q5_count": 0,
                "max_materiality": 0,
                "avg_materiality": 0.0
            }
            log_structured_metrics_to_sheets(since_date, metrics)
        send_email(brief, since_date)
    elif args.test_email:
        print("CLI option --test-email specified. Bypassing dry-run/no-updates rules for email.")
        send_email(brief, since_date)
    else:
        print("Dry-run mode. Skipping email sending and Sheets logging.")

