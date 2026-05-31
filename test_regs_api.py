import os
import json
from lambda_function import fetch_regulations_gov

print("=== Running Regulations.gov API Verification Script ===")

# Query comments since May 1, 2026
comments = fetch_regulations_gov("2026-05-01")

print(f"\nTotal comment letters fetched: {len(comments)}")

if comments:
    print("\nSurfacing the first 5 comment letters retrieved:")
    print("=" * 60)
    for idx, c in enumerate(comments[:5], 1):
        print(f"Comment #{idx}")
        print(f"Title: {c['title']}")
        print(f"Date: {c['date']}")
        print(f"URL: {c['url']}")
        print(f"Docket ID / Doc ID: {c['doc_number']}")
        print(f"Abstract Snippet: {c['abstract'][:250]}...")
        print("-" * 60)
else:
    print("\nNo comments retrieved. Verify your REGULATIONS_GOV_API_KEY in .env.")
