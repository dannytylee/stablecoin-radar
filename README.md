# Stablecoin Regulatory Radar (v1)

A daily agent that monitors primary regulatory sources and key industry press for new stablecoin regulations, scores them against the four open GENIUS Act regulatory questions using GPT-4o, logs updates to Google Sheets, and alerts stakeholders via Gmail.

---

## 🛰️ Architecture Overview

```
               [ AWS EventBridge (Daily at 8am PT) ]
                               │
                               ▼
                   [ AWS Lambda (Python 3.11) ]
                               │
       ┌───────────────────────┼────────────────────────┐
       ▼                       ▼                        ▼
[ Federal Register ]     [ RSS Feeds ]          [ OpenAI GPT-4o ]
  API conditions:          • CoinDesk             • Analyze entries
  "stablecoin",            • Cointelegraph        • Match vs. Q1-Q4
  "digital asset",         • Sheppard Mullin      • Determine direction
  "payment token"          • K&L Gates            • Generate Brief
       │                       │                        │
       └───────────┬───────────┘                        │
                   ▼                                    ▼
           [ Fetch & Filter ] ──────────────► [ Deliver Brief ]
                                                        │
                                     ┌──────────────────┴──────────────────┐
                                     ▼                                     ▼
                              [ Gmail SMTP ]                       [ Google Sheets ]
                              Daily Alert Email                    Append to Log Sheet
```

## 📋 The Five Tracking Questions (GENIUS Act Framework)

Each regulatory development is analyzed and scored against:
1. **Q1: Issuer Definition** — Who qualifies as a "permitted payment stablecoin issuer" in white-label/platform arrangements?
2. **Q2: Attestation Standard** — What does "examined by a registered public accounting firm" require in practice? (AICPA 2025 Criteria vs. Lighter standard)
3. **Q3: Capital Requirements** — What capital, liquidity, and risk management rules apply?
4. **Q4: State Equivalence** — How will Treasury certify state regulatory regimes as "substantially similar" to federal?
5. **Q5: AML/Sanctions Program Requirements** — What AML, KYC, sanctions screening, and suspicious activity reporting (SAR) requirements apply?

---

## 🛠️ Local Installation & Setup

### 1. Clone & Install Dependencies
Ensure you have Python 3.11+ installed.
```bash
pip install -r requirements.txt
```

### 2. Configure Credentials via .env (Automated)
Instead of copy-pasting API keys every time, a local `.env` file is automatically loaded at startup. Create a `.env` file at the root of the workspace:

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

Once this file is filled out, you can run the agent locally without exporting or copy-pasting any commands.

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
Package the zip (using `./package.sh`) and run:
```bash
aws lambda create-function \
  --function-name stablecoin-radar \
  --runtime python3.11 \
  --handler lambda_function.handler \
  --zip-file fileb://deployment.zip \
  --role "$ROLE_ARN" \
  --timeout 120 \
  --memory-size 128 \
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
  --source-arn "$RULE_ARN"
```

Map the EventBridge trigger target to the Lambda function:
```bash
# Get the Lambda Function ARN
LAMBDA_ARN=$(aws lambda get-function --function-name stablecoin-radar --query "Configuration.FunctionArn" --output text)

# Map the Target to EventBridge
aws events put-targets \
  --rule daily-8am-pacific \
  --targets "Id"="1","Arn"="$LAMBDA_ARN"
```

---

---

## 🔮 Roadmap & Future Scope (v2+)

As regulatory frameworks evolve, subsequent versions should integrate the following advanced tracking features:

### 1. Future Agent Integrations
* **Regulations.gov API**: Add docket tracking (e.g., `OCC-2025-0372`, `FDIC RIN 3064-AG19`, and `FinCEN` rules) to scan public comment letters submitted by industry leaders (Circle, ABA, Fiserv). This directly informs attestation and white-label arrangements.
* **Scraper Bypasses for Tier 1 Law Firms**: Build web scrapers (using headless tools or proxies) for **Sullivan & Cromwell**, **Sidley Austin**, and **Davis Polk** insights pages to bypass their programmatic blockages (`403 Forbidden`).
* **Wyoming Stable Token Commission**: Poll and scrape `https://stabletoken.wyo.gov/` for monthly attestation filings and minutes.
* **LegiScan API**: Fetch and filter 50-state bills matching "stablecoin" to monitor local regulatory progress.

### 2. What Users Should Manually Track (Outside the Agent)
* **OFAC Recent Actions**: Treasury has retired the OFAC RSS feed. Users must subscribe to the [U.S. Treasury's Email Delivery Service](https://service.govdelivery.com/service/subscribe.html?code=USTREAS_61) to receive immediate sanctions announcements.
* **AICPA Digital Assets Resource Page**: Since AICPA doesn't offer RSS, check their portal monthly for updates regarding the Stablecoin Reporting Criteria.
* **NCUA Newsroom**: Sign up for [NCUA Express](https://www.ncua.gov/newsroom) updates to monitor credit union stablecoin rules.


---

## 🔄 Iteration Log (Prompt Versioning)

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




