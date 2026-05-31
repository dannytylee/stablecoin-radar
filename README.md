# Stablecoin Regulatory Radar (v3 - Active Intelligence)

An active, daily regulatory intelligence agent that monitors primary regulatory sources, dockets, and key industry press for new stablecoin rules and commentary. It parses updates using GPT-4o, maps developments against five critical tracking questions, rates their materiality (1–5), logs structured metrics and state deduplication hashes to Google Sheets, and alerts stakeholders with suggested outreach talking points via Gmail.

---

## 🛰️ Architecture Overview

```
                          [ AWS EventBridge (Daily at 8am PT) ]
                                           │
                                           ▼
                               [ AWS Lambda (Python 3.11) ]
                                           │
    ┌─────────────────────┬────────────────┴───────────────┬──────────────────────┐
    ▼                     ▼                                ▼                      ▼
[ Federal Register ]  [ Regulations.gov ]            [ RSS Feeds ]          [ OpenAI GPT-4o ]
  API conditions:       Polling /v4/comments           • CoinDesk             • Analyze entries
  "stablecoin",         • "stablecoin" query           • Cointelegraph        • Match vs. Q1-Q5
  "digital asset",      • OCC-2025-0372 docket         • Sheppard Mullin      • Materiality (1-5)
  "payment token"       • FDIC-2026-0001 docket        • K&L Gates            • Suggested Outreach
    │                     │                                │                      │
    └───────────┬─────────┴────────────────┬───────────────┘                      │
                ▼                          ▼                                      ▼
             [ Fetch & Validate ] ──► [ SeenItems Deduplication ] ──────► [ Deliver Brief ]
                                                                                  │
                                                               ┌──────────────────┴──────────────────┐
                                                               ▼                                     ▼
                                                        [ Gmail SMTP ]                       [ Google Sheets ]
                                                        Daily Alert Email                    • SeenItems (State log)
                                                                                             • StructuredLog (Metrics)
```

---

## 📂 Project Structure & Directory Tree

```text
stablecoin-regulatory-agent/
├── .env                              # Local environment variables (ignored by git)
├── .gitignore                        # Excludes environment files, credentials, and zip packages
├── Stablecoin Radar Logger.json      # Google Cloud Service Account credentials (ignored by git)
├── requirements.txt                  # Python dependencies (requests, feedparser, openai, gspread, oauth2client)
├── package.sh                        # Shell packaging script for AWS Lambda (compiles x86_64 binaries)
├── lambda_function.py                # Main application handler (polling, deduplication, LLM, logging, emailing)
├── test_regs_api.py                  # Standalone verification script for the Regulations.gov API v4
├── deployment.zip                    # Compiled Lambda deployment package (ignored by git)
└── README.md                         # Project documentation and architectural setup guide
```

---

## 📊 Active Data Sources

The agent aggregates primary regulatory documents, official agency feeds, legal analysis, and trade press:

| Source Category | Endpoint / Details | Target Content |
| :--- | :--- | :--- |
| **Federal Register** | `https://www.federalregister.gov/api/v1` | Documents matching `"stablecoin"`, `"digital asset"`, or `"payment token"` |
| **Regulations.gov** | `https://api.regulations.gov/v4/comments` | Comment letters matching search `"stablecoin"`, and full docket reviews for high-value rulemaking: <br>• **OCC-2025-0372** (National Bank Reserve Accounts)<br>• **FDIC-2026-0001** (Deposit Insurance Rules) |
| **Federal Reserve** | Official RSS Press Feed | Press releases, policy statements, and discount window/payment system risk updates |
| **FDIC** | Official RSS Press Feed | Board decisions, enforcement actions, and deposit insurance proposals |
| **Top-Tier Legal Blogs** | Law firm RSS Feeds | Regulatory analysis and legal briefs:<br>• **K&L Gates** (FinTech Law Watch)<br>• **Sheppard Mullin** (Law of the Ledger) |
| **Crypto Press** | Industry News RSS Feeds | Market sentiment, legislative drafts, and policy reactions:<br>• **CoinDesk**<br>• **Cointelegraph** |

---

## 📋 The Five Tracking Questions (GENIUS Act Framework)

Regulatory developments are evaluated by the LLM and categorized against the five open regulatory gaps of the GENIUS Act (Guiding and Establishing National Innovation for US Stablecoins):

1. **Q1: Issuer Definition** — Who qualifies as a "permitted payment stablecoin issuer" in white-label and platform-mediated arrangements?
2. **Q2: Attestation Standard** — What does "examined by a registered public accounting firm" require in practice? (AICPA 2025 Criteria vs. Lighter standard)
3. **Q3: Capital Requirements** — What capital, liquidity, and risk management requirements apply to stablecoin issuers?
4. **Q4: State Equivalence** — How will Treasury certify state regulatory regimes as "substantially similar" to federal?
5. **Q5: AML/Sanctions Program Requirements** — What AML, KYC, sanctions screening, and suspicious activity reporting (SAR) regulations apply?

---

## 🛠️ Local Installation & Setup

### 1. Clone & Install Dependencies
Ensure you have Python 3.11+ installed.
```bash
pip install -r requirements.txt
```

### 2. Configure Credentials via .env
Create a `.env` file at the root of the workspace:

```env
# API Keys
OPENAI_API_KEY="your-openai-api-key"
REGULATIONS_GOV_API_KEY="your-regulations-gov-api-key"
GMAIL_APP_PASSWORD="your-gmail-app-password"

# Email Settings
RECIPIENT="your-email@gmail.com"
SENDER="your-email@gmail.com"

# Google Sheets Logging
SPREADSHEET_ID="your-spreadsheet-id"
GOOGLE_SHEETS_CREDENTIALS_PATH="/path/to/your/google-credentials.json"
SHEET_NAME="Sheet1"
```

---

## 🚀 Running & Testing Locally

The script contains a CLI runner to easily run historic checks and perform dry-runs without triggering emails or sheets logs.

### 1. Perform a Dry Run (Fetch and Analyze)
Run a scan from a specific historical date and print the analysis to your terminal without sending emails or writing to Sheets:
```bash
python3 lambda_function.py --since 2026-05-01 --dry-run
```

### 2. Run a Full Flow (Dry-run + Test Email)
Fetch, analyze, and force-send the generated brief to your inbox (even if no updates are found):
```bash
python3 lambda_function.py --since 2026-05-01 --test-email
```

### 3. Normal Execution (Fetch, Analyze, Log & Email)
Run standard execution (which looks back 24 hours):
```bash
python3 lambda_function.py
```

### 4. Regulations.gov Scraper Verification
Verify that Regulations.gov API v4 is communicating and parsing comment letters correctly:
```bash
python3 test_regs_api.py
```

---

## 📦 AWS Lambda Console Deployment (GUI-Based)

Since command-line tools like `aws` might not be configured, you can build the deployment archive and configure it through the AWS Web Console.

### Step 1: Package the Zip
Run the provided packaging script. This compiles all dependencies into a clean `deployment.zip` alongside `lambda_function.py`:
```bash
./package.sh
```

### Step 2: Create AWS Lambda Function
1. Open the **AWS Lambda Console**.
2. Click **Create function**.
3. Choose **Author from scratch**:
   - **Function name**: `stablecoin-radar`
   - **Runtime**: `Python 3.11`
   - **Architecture**: `x86_64`
4. For permissions, let AWS create a basic execution role.
5. Click **Create function**.

### Step 3: Upload the Code Zip
1. On the Lambda function details page, locate the **Code** tab.
2. In the **Code source** section, click **Upload from** -> **.zip file**.
3. Select and upload the `deployment.zip` generated in Step 1.
4. Click **Save**.

### Step 4: Configure Settings & Environment Variables
1. Go to the **Configuration** tab.
2. In the **General configuration** card, click **Edit** and set **Timeout** to `2 minutes` (to allow for feed fetching and LLM calls). Save changes.
3. In the **Environment variables** sidebar, click **Edit** and add:
   - `OPENAI_API_KEY` = `sk-proj-...`
   - `GMAIL_APP_PASSWORD` = `xxxx xxxx xxxx xxxx` (Your Gmail App Password)
   - `RECIPIENT` = `your-email@gmail.com`
   - `SENDER` = `your-email@gmail.com`
   - `SPREADSHEET_ID` = `(Optional)`
   - `GOOGLE_SHEETS_CREDENTIALS` = `(Optional JSON string)`
   - `SHEET_NAME` = `Sheet1` (Optional)
4. Save changes.

### Step 5: Schedule with EventBridge (CloudWatch Events)
1. In the Lambda details page, click **Add trigger**.
2. Select **EventBridge (CloudWatch Events)**.
3. Choose **Create a new rule**:
   - **Rule name**: `daily-8am-pacific`
   - **Rule type**: `Schedule expression`
   - **Schedule expression**: `cron(0 15 * * ? *)` *(Note: 15:00 UTC corresponds to 8:00 AM PT)*
4. Click **Add**.

---

## 💻 AWS CLI Deployment Instructions (Alternative)

If you prefer to deploy and manage resources via the terminal, use the following commands.

### Step 1: Create IAM Execution Role
Create a trust policy document:
```bash
cat <<EOF > trust-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
```

Create the role and attach the execution policy:
```bash
# Create IAM role
aws iam create-role \
  --role-name stablecoin-radar-execution-role \
  --assume-role-policy-document file://trust-policy.json

# Attach standard Lambda execution policy (for CloudWatch logging)
aws iam attach-role-policy \
  --role-name stablecoin-radar-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

Wait a few seconds for the IAM changes to propagate, then fetch the Role ARN:
```bash
ROLE_ARN=$(aws iam get-role --role-name stablecoin-radar-execution-role --query "Role.Arn" --output text)
```

### Step 2: Create the Lambda Function
Package the zip (using `./package.sh`) and run (using your target region, e.g., `us-east-2`):
```bash
aws lambda create-function \
  --function-name stablecoin-radar \
  --runtime python3.11 \
  --handler lambda_function.handler \
  --zip-file fileb://deployment.zip \
  --role "$ROLE_ARN" \
  --timeout 120 \
  --memory-size 128 \
  --region us-east-2 \
  --environment "Variables={OPENAI_API_KEY=sk-proj-...,GMAIL_APP_PASSWORD=xxxx,RECIPIENT=your-email@gmail.com,SENDER=your-email@gmail.com}"
```

### Step 3: Create EventBridge Rule & Targets
Create the Cron trigger rule (15:00 UTC = 8:00 AM PT):
```bash
# Create Rule
aws events put-rule \
  --name daily-8am-pacific \
  --schedule-expression "cron(0 15 * * ? *)"

# Save the Rule ARN
RULE_ARN=$(aws events describe-rule --name daily-8am-pacific --query "Arn" --output text)
```

Authorize EventBridge to invoke the Lambda function:
```bash
# Grant permissions to trigger Lambda
aws lambda add-permission \
  --function-name stablecoin-radar \
  --statement-id EventBridgeTrigger \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --region us-east-2 \
  --source-arn "$RULE_ARN"
```

Map the EventBridge trigger target to the Lambda function:
```bash
# Get the Lambda Function ARN
LAMBDA_ARN=$(aws lambda get-function --function-name stablecoin-radar --region us-east-2 --query "Configuration.FunctionArn" --output text)

# Map the Target to EventBridge
aws events put-targets \
  --rule daily-8am-pacific \
  --region us-east-2 \
  --targets "Id"="1","Arn"="$LAMBDA_ARN"
```

---

## 🔄 Iteration Log (Prompt & System Versioning)

### Prompt v1 (Initial Version)
- Standard classification instruction. Q1-Q4 tags assigned based on simple topic matching. 
- "Direction" left to the LLM's default reasoning without formal definitions.

### Prompt v2 (Tightened Tagging Rules)
- **Problem**: Analysis showed over-tagging (assigning Q1-Q4 tags to tangential news) and ambiguous direction values.
- **Change**: Added explicit `TAGGING & CLASSIFICATION RULES` defining strict criteria:
  - Conservative tagging threshold (material proposals/actionable insights only).
  - Concrete boundaries for "Stricter", "More Permissive", "Clarifying", and "Ambiguous".
- **Result**: Drastically reduced classification noise, improving clarity in daily summary briefs.

### Prompt v3 (Federal Reserve Policy Specialization)
- **Problem**: Coordinated Federal Reserve proposals (Reg D, Reg A, and Payment System Risk policies) regarding special-purpose payment accounts for stablecoin reserves were being under-classified as "None" because they did not explicitly mention "stablecoin" by name.
- **Change**: Added specific instruction directing the LLM to analyze Fed proposals on reserve account access, payment system risk, and discount window eligibility, mapping them directly to Q3 (Capital Requirements) and Q1 (Issuer Definition).
- **Result**: Correctly tags and analyzes coordinated central bank rulemaking impacting stablecoin reserve infrastructure.

### System v3 Upgrade (Active Intelligence Infrastructure)
- **Problem**: Monitoring was purely passive RSS and Federal Register scraping; it missed active regulatory comments (e.g. fromCircle, ABA, Fiserv), could log duplicate items on consecutive runs, lacked structured metrics logging, and would crash if OpenAI failed.
- **Change**: 
  - Integrated **Regulations.gov API v4** for active comment letter monitoring.
  - Implemented Google Sheets-based persistent state deduplication (`SeenItems` worksheet).
  - Created a daily structured metrics logger (`StructuredLog` worksheet) to feed dashboards.
  - Expanded categories to include **Q5 AML/Sanctions** tracking.
  - Introduced **Materiality scoring (1-5)** and conditional **Suggested Outreach BD directives** for Materiality 4-5 items.
  - Wrapped LLM calls in a robust fallback block to generate raw-links briefs on API failures.
- **Result**: Transformed the aggregator into a resilient, production-grade intelligence infrastructure.
