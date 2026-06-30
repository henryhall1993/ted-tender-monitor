"""
Singapore market intelligence fetcher — data.gov.sg GeBIZ awarded-tenders dataset.

GeBIZ (https://www.gebiz.gov.sg) has no public API for *open* tenders (see
scripts/singapore_fetcher.py for why). It does, however, publish a clean REST API
for AWARDED government contracts via data.gov.sg:

    https://data.gov.sg/api/action/datastore_search?resource_id=d_acde1106003906a75c3fa052592f2fcb

This script pulls recently awarded medical-device-related contracts from that
dataset as historical market intelligence (who buys what, from whom, at what
price) rather than as live procurement opportunities.
"""

import csv
import os
import re
from datetime import date, datetime, timedelta

import requests

API_URL = "https://data.gov.sg/api/action/datastore_search"
RESOURCE_ID = "d_acde1106003906a75c3fa052592f2fcb"
OUTPUT_CSV = "results/singapore_market_intelligence.csv"
PAGE_SIZE = 1000

MONTHS_BACK = 6

# Rough fixed SGD->EUR conversion rate (no live FX API in this pipeline; other
# fetchers in this repo pass through raw notice currency without conversion too).
SGD_TO_EUR = 0.68

KEYWORDS = [
    "medical device", "medical equipment", "surgical", "diagnostic",
    "patient monitoring", "hospital equipment", "ventilator", "imaging",
    "ultrasound", "defibrillator", "infusion", "catheter", "orthopaedic",
    "prosthetic",
]

CSV_COLUMNS = [
    "title", "award_date", "country", "awarded_value_eur",
    "supplier_name", "tender_url", "notice_id", "cpv_codes",
    "description", "buyer_name",
]

_KEYWORD_RE = [re.compile(re.escape(kw), re.IGNORECASE) for kw in KEYWORDS]


def fetch_records():
    """Page through the full datastore_search result set."""
    records = []
    offset = 0
    while True:
        resp = requests.get(API_URL, params={
            "resource_id": RESOURCE_ID,
            "limit": PAGE_SIZE,
            "offset": offset,
        }, timeout=30)
        resp.raise_for_status()
        batch = resp.json()["result"]["records"]
        if not batch:
            break
        records.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return records


def parse_award_date(raw):
    """GeBIZ dates are 'D/M/YYYY' — normalise to ISO 'YYYY-MM-DD'."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def is_relevant(description):
    return any(p.search(description) for p in _KEYWORD_RE)


def extract_record(rec):
    award_date = parse_award_date(rec.get("award_date", ""))
    try:
        value_sgd = float(rec.get("awarded_amt") or 0)
    except ValueError:
        value_sgd = 0

    return {
        "title": rec.get("tender_description", "")[:300],
        "award_date": award_date.isoformat() if award_date else "",
        "country": "SGP",
        "awarded_value_eur": round(value_sgd * SGD_TO_EUR, 2) if value_sgd else "",
        "supplier_name": rec.get("supplier_name", ""),
        "tender_url": "",
        "notice_id": rec.get("tender_no", ""),
        "cpv_codes": "",
        "description": rec.get("tender_description", "")[:4000],
        "buyer_name": rec.get("agency", ""),
    }, award_date


def main():
    os.makedirs("results", exist_ok=True)

    cutoff = date.today() - timedelta(days=30 * MONTHS_BACK)
    print(f"Fetching GeBIZ awarded-tenders dataset (cutoff: {cutoff.isoformat()})")

    raw_records = fetch_records()
    print(f"Fetched {len(raw_records)} total awarded records")

    results = []
    for rec in raw_records:
        description = rec.get("tender_description", "") or ""
        if not is_relevant(description):
            continue
        row, award_date = extract_record(rec)
        if award_date is None or award_date < cutoff:
            continue
        results.append(row)

    results.sort(key=lambda r: r["award_date"], reverse=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nCount: {len(results)}")
    print("First 10 titles:")
    for r in results[:10]:
        print(f"  [{r['award_date']}] {r['title'][:90]}")

    print(f"\nDone — {len(results)} Singapore medical device awards written to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
