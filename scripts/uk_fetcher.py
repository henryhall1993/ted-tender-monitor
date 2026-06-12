import csv
import json
import logging
import time
import requests
from datetime import date, timedelta

BASE_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
OUTPUT_CSV = "results/uk_medical_devices.csv"
SLEEP_BETWEEN_PAGES = 2
CPV_CODE = "33100000"

CSV_COLUMNS = [
    "title", "deadline", "country", "estimated_value_eur",
    "tender_url", "notice_id", "cpv_codes", "description", "buyer_name"
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

def fetch_page(updated_from, updated_to, cursor=None):
    params = {
        "updatedFrom": updated_from,
        "updatedTo": updated_to,
        "stages": "tender",
        "limit": 100,
    }
    if cursor:
        params["cursor"] = cursor

    response = requests.get(
        BASE_URL,
        params=params,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if not response.ok:
        log.error("API error %s: %s", response.status_code, response.text[:200])
    response.raise_for_status()
    return response.json()

def is_medical_device(release):
    """Check if the release contains CPV code 33100000."""
    tender = release.get("tender", {})
    
    # Check main classification
    main_cpv = tender.get("classification", {}).get("id", "")
    if main_cpv.startswith("331"):
        return True
    
    # Check additional classifications on items
    for item in tender.get("items", []):
        for classification in item.get("additionalClassifications", []):
            if classification.get("id", "").startswith("331"):
                return True
    
    return False

def extract_buyer(release):
    """Extract buyer name and contact from parties list."""
    for party in release.get("parties", []):
        if "buyer" in party.get("roles", []):
            return party.get("name", "")
    return ""

def extract_contact(release):
    """Extract contact details from buyer party."""
    for party in release.get("parties", []):
        if "buyer" in party.get("roles", []):
            contact = party.get("contactPoint", {})
            parts = []
            if contact.get("name"):
                parts.append(contact["name"])
            if contact.get("email"):
                parts.append(contact["email"])
            if contact.get("telephone"):
                parts.append(contact["telephone"])
            return " | ".join(parts)
    return ""

def extract_value(release):
    """Extract estimated value from tender or lots."""
    tender = release.get("tender", {})
    
    # Try top level value first
    value = tender.get("value", {})
    if value.get("amount"):
        return value["amount"]
    
    # Try summing lot values
    total = 0
    for lot in tender.get("lots", []):
        amount = lot.get("value", {}).get("amount", 0)
        if amount:
            total += amount
    
    return total if total > 0 else ""

def extract_description(release):
    """Extract the best available description."""
    tender = release.get("tender", {})
    
    # Try lot descriptions first as they tend to be more detailed
    lot_descriptions = []
    for lot in tender.get("lots", []):
        desc = lot.get("description", "")
        if desc and len(desc) > 50:
            lot_descriptions.append(desc)
    
    if lot_descriptions:
        return " ".join(lot_descriptions)[:4000]
    
    # Fall back to main tender description
    return tender.get("description", "")[:4000]

def extract_deadline(release):
    """Extract submission deadline."""
    tender = release.get("tender", {})
    deadline = tender.get("tenderPeriod", {}).get("endDate", "")
    if deadline and "T" in deadline:
        return deadline.split("T")[0]
    return deadline

def extract_cpv_codes(release):
    """Extract all CPV codes from the release."""
    tender = release.get("tender", {})
    cpv_codes = set()
    
    main_cpv = tender.get("classification", {}).get("id", "")
    if main_cpv:
        cpv_codes.add(main_cpv)
    
    for item in tender.get("items", []):
        for classification in item.get("additionalClassifications", []):
            if classification.get("scheme") == "CPV":
                cpv_codes.add(classification.get("id", ""))
    
    return "|".join(sorted(cpv_codes))

def extract_notice(release):
    """Map a raw OCDS release to our standard CSV format."""
    notice_id = release.get("id", "")
    ocid = release.get("ocid", "")
    tender = release.get("tender", {})
    
    title = tender.get("title", "")
    deadline = extract_deadline(release)
    estimated_value = extract_value(release)
    description = extract_description(release)
    buyer_name = extract_buyer(release)
    cpv_codes = extract_cpv_codes(release)
    
    # Build the tender URL
    tender_url = f"https://www.find-tender.service.gov.uk/Notice/{notice_id}" if notice_id else ""
    
    return {
        "title": title,
        "deadline": deadline,
        "country": "GBR",
        "estimated_value_eur": estimated_value,
        "tender_url": tender_url,
        "notice_id": notice_id,
        "cpv_codes": cpv_codes,
        "description": description,
        "buyer_name": buyer_name,
    }

def main():
    import os
    os.makedirs("results", exist_ok=True)

    six_months_ago = (date.today() - timedelta(days=180)).strftime("%Y-%m-%dT00:00:00")
    today = date.today().strftime("%Y-%m-%dT23:59:59")
    
    print(f"Fetching UK medical device tenders from {six_months_ago} to {today}")
    
    all_records = []
    cursor = None
    page = 1

    while True:
        log.info("Fetching page %d ...", page)
        try:
            data = fetch_page(six_months_ago, today, cursor)
        except requests.HTTPError as exc:
            log.error("HTTP error: %s", exc)
            break
        except requests.RequestException as exc:
            log.error("Network error: %s", exc)
            break

        releases = data.get("releases", [])
        if not releases:
            log.info("No more results — stopping.")
            break

        # Filter to medical device CPV codes
        for release in releases:
            if is_medical_device(release):
                all_records.append(extract_notice(release))

        log.info("Page %d: %d releases checked | %d medical device tenders found so far",
                 page, len(releases), len(all_records))

        # Check for next page cursor
        cursor = data.get("nextCursor")
        if not cursor:
            log.info("No more pages available.")
            break

        page += 1
        time.sleep(SLEEP_BETWEEN_PAGES)

    if not all_records:
        log.warning("No medical device records retrieved.")
        return

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nDone — {len(all_records)} UK medical device tenders written to: {OUTPUT_CSV}")
    print("\nTitle preview:")
    for r in all_records[:5]:
        print(f" - {r['title']} | {r['buyer_name']}")

main()
