"""
Exploratory script — pulls together two Singapore data sources for review:

1. MOH's "Upcoming Healthcare Facilities from 2026 onwards" page: new/redeveloped
   hospitals, polyclinics, and nursing homes (demand-side signal — where future
   medical equipment tenders are likely to originate).
2. results/singapore_market_intelligence.csv: historical awarded medical-device
   contracts from data.gov.sg (supply-side signal — who already wins this work).

This is throwaway/inspection tooling, not part of the production pipeline.
"""

import csv
import html
import re
from collections import Counter

import requests

MOH_URL = (
    "https://www.moh.gov.sg/seeking-healthcare/find-a-facility-or-service/"
    "types-of-medical-facilities-and-services/find-a-medical-facility/"
    "facilities-from-2026-onwards/"
)
MARKET_INTEL_CSV = "results/singapore_market_intelligence.csv"


# ---------------------------------------------------------------------------
# Part 1 — MOH upcoming facilities
# ---------------------------------------------------------------------------

def fetch_moh_facilities():
    resp = requests.get(MOH_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # server doesn't declare charset; page is UTF-8
    return parse_moh_facilities(resp.text)


def parse_moh_facilities(page_html):
    """
    The page structure is a flat sequence of <h2> category headings, each
    followed by one or more <h3> facility names, each immediately followed by
    a <p> giving the address/location. There is no completion-year or bed-count
    data anywhere on the page as of June 2026 (Updated as of 19 March 2026).
    """
    tag_pattern = re.compile(
        r"<h2[^>]*>(.*?)</h2>|<h3[^>]*>(.*?)</h3>|<p[^>]*>(.*?)</p>",
        re.DOTALL,
    )

    def clean(raw):
        text = re.sub(r"<[^>]+>", "", raw)
        return html.unescape(text).strip()

    facilities = []
    current_category = None
    current_name = None

    for match in tag_pattern.finditer(page_html):
        h2, h3, p = match.groups()
        if h2 is not None:
            current_category = clean(h2)
            current_name = None
        elif h3 is not None:
            current_name = clean(h3)
        elif p is not None and current_name is not None:
            location = clean(p)
            if not location or "Updated as of" in location:
                continue
            bed_match = re.search(r"(\d+)\s*-?\s*bed", location, re.IGNORECASE)
            facilities.append({
                "name": current_name,
                "category": current_category,
                "location": location,
                "completion_year": None,  # not published on this page
                "bed_count": bed_match.group(1) if bed_match else None,
            })
            current_name = None  # consume — next <p> belongs to the next <h3>

    return facilities


def print_moh_facilities(facilities):
    print("=" * 80)
    print(f"MOH UPCOMING HEALTHCARE FACILITIES ({len(facilities)} found)")
    print("=" * 80)

    by_category = {}
    for f in facilities:
        by_category.setdefault(f["category"], []).append(f)

    for category, items in by_category.items():
        print(f"\n--- {category} ({len(items)}) ---")
        for f in items:
            year = f["completion_year"] or "not published"
            beds = f["bed_count"] or "not mentioned"
            print(f"  {f['name']}")
            print(f"      Location: {f['location']}")
            print(f"      Expected completion: {year} | Beds: {beds}")


# ---------------------------------------------------------------------------
# Part 2 — historical awarded medical-device contracts
# ---------------------------------------------------------------------------

def load_market_intelligence(filepath):
    with open(filepath, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def categorize_device(title):
    """Very rough keyword bucket for an at-a-glance category breakdown."""
    title_lower = title.lower()
    buckets = {
        "Imaging": ["imaging", "ultrasound", "mri", "ct scan", "x-ray", "fluoroscop", "fnirs", "neuroimaging"],
        "Monitoring": ["monitoring", "monitor"],
        "Surgical": ["surgical", "surgery", "operating"],
        "Diagnostic": ["diagnostic", "laboratory", "lab "],
        "Ventilation/Respiratory": ["ventilator", "respirat", "anaesthesia", "anesthesia"],
        "Infusion": ["infusion", "catheter"],
        "Orthopaedic/Prosthetic": ["orthopaedic", "orthopedic", "prosthetic"],
        "Defibrillator": ["defibrillator"],
    }
    for category, keywords in buckets.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return "Other/Unclassified"


def print_market_intelligence(records):
    print("\n" + "=" * 80)
    print(f"SINGAPORE HISTORICAL AWARDED MEDICAL DEVICE CONTRACTS ({len(records)} found)")
    print("=" * 80)

    if not records:
        print(f"  No records found in {MARKET_INTEL_CSV} — run "
              f"scripts/singapore_market_intel_fetcher.py first.")
        return

    category_counts = Counter(categorize_device(r["title"]) for r in records)
    supplier_counts = Counter(r["supplier_name"] for r in records if r.get("supplier_name"))
    buyer_counts = Counter(r["buyer_name"] for r in records if r.get("buyer_name"))

    print("\n--- Device categories ---")
    for category, count in category_counts.most_common():
        print(f"  {category}: {count}")

    print("\n--- Suppliers who have won contracts ---")
    for supplier, count in supplier_counts.most_common():
        print(f"  {supplier}: {count}")

    print("\n--- Buying agencies ---")
    for buyer, count in buyer_counts.most_common():
        print(f"  {buyer}: {count}")

    print("\n--- Individual contracts ---")
    for r in records:
        value = r.get("awarded_value_eur") or "n/a"
        print(f"  [{r.get('award_date', '?')}] {r['title'][:90]}")
        print(f"      Buyer: {r.get('buyer_name', '?')} | Supplier: {r.get('supplier_name', '?')} | Value (EUR): {value}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    facilities = fetch_moh_facilities()
    print_moh_facilities(facilities)

    records = load_market_intelligence(MARKET_INTEL_CSV)
    print_market_intelligence(records)


if __name__ == "__main__":
    main()
