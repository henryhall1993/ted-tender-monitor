"""
Fetches medical device tenders from Public Contracts Scotland (PCS).

PCS exposes an OCDS API at https://api.publiccontractsscotland.gov.uk/v1/notices
that returns all contract notices published in a given month. There is no
server-side CPV or keyword filter, so we fetch every month in the window and
filter locally.

Strategy:
  1. Fetch all contract notices (noticeType=2) for each month in the last 6 months.
  2. Keep a release if it has at least one CPV code starting with "33" (medical
     equipment / pharmaceuticals) — primary signal.
  3. If CPV filtering yields nothing, fall back to keyword matching on title and
     description for: "medical device", "surgical equipment", "diagnostic imaging",
     "wound care".
  4. Apply a noise filter (word-boundary) to drop obvious non-medical results.
  5. Save to results/scotland_medical_devices.csv.
"""

import csv
import logging
import re
import time
from datetime import date, timedelta

import urllib3
import requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE   = "https://api.publiccontractsscotland.gov.uk/v1/notices"
OUTPUT_CSV = "results/scotland_medical_devices.csv"

KEYWORDS = [
    "medical device",
    "surgical equipment",
    "diagnostic imaging",
    "wound care",
]

NOISE_KEYWORDS = [
    "tree", "waste", "cleaning", "catering", "security guard", "grounds",
    "landscaping", "pest control", "parking", "printing", "translation",
    "legal services", "insurance", "software", "it services", "consultancy",
]

CSV_COLUMNS = [
    "title", "deadline", "country", "estimated_value_eur",
    "tender_url", "notice_id", "cpv_codes", "description", "buyer_name",
]

_NOISE_RE   = [re.compile(r"\b" + re.escape(nk) + r"\b") for nk in NOISE_KEYWORDS]
_KEYWORD_RE = [re.compile(r"\b" + re.escape(kw) + r"\b") for kw in KEYWORDS]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def months_in_range(start: date, end: date):
    """Yield 'mm-yyyy' strings for every month from start to end inclusive."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield f"{m:02d}-{y}"
        m += 1
        if m > 12:
            m, y = 1, y + 1


def fetch_month(month_str: str):
    """Fetch all contract notices published in the given month (mm-yyyy)."""
    resp = requests.get(
        API_BASE,
        params={"dateFrom": month_str, "noticeType": 2, "outputType": 0},
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
        timeout=30,
        verify=False,
    )
    if not resp.ok:
        log.error("HTTP %s for month %s: %s", resp.status_code, month_str, resp.text[:200])
        resp.raise_for_status()
    return resp.json().get("releases", [])


# ---------------------------------------------------------------------------
# OCDS extraction helpers
# ---------------------------------------------------------------------------

def _cpv_codes(release):
    """Return a space-separated string of all CPV codes on this release."""
    tender = release.get("tender", {})
    codes = set()
    main = tender.get("classification", {}).get("id", "")
    if main:
        codes.add(main)
    for item in tender.get("items", []):
        for cls in item.get("additionalClassifications", []):
            if cls.get("scheme", "").upper() == "CPV":
                codes.add(cls.get("id", ""))
    return " ".join(sorted(codes))


def _buyer(release):
    for party in release.get("parties", []):
        if "buyer" in party.get("roles", []):
            return party.get("name", "")
    return ""


def _value(release):
    tender = release.get("tender", {})
    v = tender.get("value", {})
    if v.get("amount"):
        return v["amount"]
    total = sum(lot.get("value", {}).get("amount", 0) or 0 for lot in tender.get("lots", []))
    return total if total else ""


def _deadline(release):
    dl = release.get("tender", {}).get("tenderPeriod", {}).get("endDate", "")
    return dl.split("T")[0] if dl and "T" in dl else dl


def _description(release):
    tender = release.get("tender", {})
    lot_descs = [lot.get("description", "") for lot in tender.get("lots", []) if len(lot.get("description", "")) > 50]
    if lot_descs:
        return " ".join(lot_descs)[:4000]
    return (tender.get("description", "") or "")[:4000]


def extract_notice(release):
    notice_id = release.get("id", "")
    ocid      = release.get("ocid", "")
    cpv       = _cpv_codes(release)
    tender_url = (
        f"https://www.publiccontractsscotland.gov.uk/search/show/{ocid}"
        if ocid else ""
    )
    return {
        "title":               release.get("tender", {}).get("title", ""),
        "deadline":            _deadline(release),
        "country":             "SCT",
        "estimated_value_eur": _value(release),
        "tender_url":          tender_url,
        "notice_id":           notice_id,
        "cpv_codes":           cpv,
        "description":         _description(release),
        "buyer_name":          _buyer(release),
    }


# ---------------------------------------------------------------------------
# Relevance filter
# ---------------------------------------------------------------------------

def has_medical_cpv(record):
    return any(c.startswith("33") for c in (record["cpv_codes"] or "").split())


def has_keyword_in_title(record):
    title = record["title"].lower()
    return any(p.search(title) for p in _KEYWORD_RE)


def has_noise_in_title(record):
    title = record["title"].lower()
    return any(p.search(title) for p in _NOISE_RE)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import os
    os.makedirs("results", exist_ok=True)

    today      = date.today()
    six_ago    = today - timedelta(days=180)
    month_list = list(months_in_range(six_ago, today))

    print(f"Fetching PCS contract notices: {month_list[0]} to {month_list[-1]}\n")

    all_releases = []
    for month_str in month_list:
        log.info("Fetching month %s ...", month_str)
        try:
            releases = fetch_month(month_str)
        except requests.RequestException as exc:
            log.error("Skipping %s: %s", month_str, exc)
            time.sleep(2)
            continue
        all_releases.extend(releases)
        log.info("  → %d releases (running total: %d)", len(releases), len(all_releases))
        time.sleep(1)

    log.info("Total releases fetched: %d", len(all_releases))

    # Extract and deduplicate
    seen = {}
    for release in all_releases:
        record = extract_notice(release)
        nid = record["notice_id"]
        if nid and nid not in seen:
            seen[nid] = record
    records = list(seen.values())
    log.info("Unique notices after dedup: %d", len(records))

    # --- Phase 1: CPV filter ---
    cpv_records = [r for r in records if has_medical_cpv(r) and not has_noise_in_title(r)]
    log.info("After CPV 33* filter: %d", len(cpv_records))

    # --- Phase 2: keyword fallback ---
    if cpv_records:
        final = cpv_records
        strategy = "CPV 33*"
    else:
        log.warning("CPV filter returned nothing — falling back to keyword search")
        final = [r for r in records if has_keyword_in_title(r) and not has_noise_in_title(r)]
        strategy = "keyword fallback"

    # --- Print summary ---
    cpv_count     = len([r for r in records if has_medical_cpv(r)])
    keyword_count = len([r for r in records if has_keyword_in_title(r)])
    noise_count   = len([r for r in records if has_noise_in_title(r)])

    print(f"\n--- Filter summary (strategy: {strategy}) ---")
    print(f"Total unique notices              : {len(records)}")
    print(f"  with CPV 33*                   : {cpv_count}")
    print(f"  with medical keyword in title  : {keyword_count}")
    print(f"  with noise in title            : {noise_count}")
    print(f"Final kept                        : {len(final)}\n")

    print("First 10 titles:")
    for r in final[:10]:
        print(f"  [{r['cpv_codes'][:12]:12s}] {r['title']} | {r['buyer_name']}")
    print()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(r for r in final)

    print(f"Done — {len(final)} Scotland medical device tenders written to: {OUTPUT_CSV}")


main()
