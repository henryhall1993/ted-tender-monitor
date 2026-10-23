import csv
import json
import logging
import time
import requests
from datetime import date, timedelta

BASE_URL = "https://api.ted.europa.eu/v3/notices/search"
PAGE_SIZE = 100
SLEEP_BETWEEN_PAGES = 1
OUTPUT_CSV = "results/ted_medical_devices.csv"

# Specific CPV codes for medical gas systems, pipelines/outlets, suction &
# vacuum, and gas delivery. These are queried as their OWN pass (see
# GAS_SUCTION_PAGES below) because the broad "33100000 - Medical equipments"
# query below is dominated by high-volume categories (implants, consumables,
# diagnostics, etc.) — with only 3 pages / 300 records pulled per run, niche
# gas/suction notices were getting crowded out and effectively never surfaced.
GAS_SUCTION_CPV_CODES = [
    "33157000",  # Gas-therapy and respiratory devices (parent)
    "33157100",  # Oxygen breathing apparatus
    "33157110",  # Oxygen masks
    "33157200",  # Ventilation equipment / respiratory assistance
    "33157300",  # Oxygen tents
    "33157400",  # Medical breathing devices / ventilators
    "33157500",  # Hyperbaric chambers
    "33157700",  # Humidifiers for oxygen therapy
    "33157800",  # Oxygen administration unit
    "33157810",  # Oxygen therapy unit / installation
    "33172000",  # Anaesthesia and resuscitation devices (parent)
    "33172100",  # Anaesthesia devices
    "33172200",  # Resuscitation devices
]
GAS_SUCTION_PAGES = 5  # up to 500 targeted records per run

REQUESTED_FIELDS = [
    "ND", "TI", "DT", "CY", "TVH", "TVL", "PC", "DD",
    "description-lot", "description-part", "description-proc",
    "title-lot", "title-part",
    "organisation-name-buyer", "organisation-email-buyer",
    "organisation-tel-buyer", "organisation-city-buyer",
    "buyer-country", "deadline-date-lot", "deadline-date-part",
    "award-criterion-type-lot", "selection-criterion-description-lot",
]

CSV_COLUMNS = [
    "title", "deadline", "country", "estimated_value_eur",
    "tender_url", "notice_id", "cpv_codes", "description", "buyer_name"
]

TED_NOTICE_URL = "https://ted.europa.eu/en/notice/-/detail/{notice_id}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

def build_query(page, cpv_clause="classification-cpv=33100000"):
    six_months_ago = (date.today() - timedelta(days=180)).strftime("%Y%m%d")
    today = date.today().strftime("%Y%m%d")
    return {
        "query": f"{cpv_clause} AND publication-date>={six_months_ago} AND publication-date<={today}",
        "fields": REQUESTED_FIELDS,
        "page": page,
        "limit": PAGE_SIZE,
        "scope": "ACTIVE",
        "paginationMode": "PAGE_NUMBER",
    }

def fetch_page(session, page, cpv_clause="classification-cpv=33100000"):
    payload = build_query(page, cpv_clause)
    log.info("Fetching page %d ...", page)
    response = session.post(
        BASE_URL,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps(payload),
        timeout=30,
    )
    if not response.ok:
        log.error("API error %s: %s", response.status_code, response.text)
    response.raise_for_status()
    return response.json()

def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value

def get_english_title(ti_field):
    if not ti_field:
        return ""
    if isinstance(ti_field, str):
        return ti_field.strip()
    if isinstance(ti_field, dict):
        preferred = ["eng", "en", "fra", "deu", "spa", "ita", "por", "nld", "pol"]
        for lang in preferred:
            candidate = ti_field.get(lang, "")
            if candidate and isinstance(candidate, str):
                parts = candidate.strip().split(" \u2013 ")
                if len(parts) >= 2:
                    return f"{parts[0]} \u2013 {parts[1]}"
                return candidate.strip()
        for val in ti_field.values():
            if val and isinstance(val, str):
                return val.strip()
    return ""

def get_description(notice):
    for field in ["description-lot", "description-part", "description-proc"]:
        raw = notice.get(field)
        if not raw:
            continue
        if isinstance(raw, dict):
            for lang in ["eng", "en", "fra", "deu", "spa", "ita", "por", "nld", "pol", "ces", "hrv", "ron"]:
                val = raw.get(lang)
                if val:
                    if isinstance(val, list):
                        text = " ".join(str(v) for v in val if v)
                    else:
                        text = str(val)
                    if len(text) > 50:
                        return text[:4000]
            for val in raw.values():
                if val:
                    if isinstance(val, list):
                        text = " ".join(str(v) for v in val if v)
                    else:
                        text = str(val)
                    if len(text) > 50:
                        return text[:4000]
        elif isinstance(raw, str) and len(raw) > 50:
            return raw[:4000]
    return ""

def get_buyer_name(notice):
    raw = notice.get("organisation-name-buyer", "")
    if isinstance(raw, dict):
        for val in raw.values():
            if isinstance(val, list) and val:
                return val[0]
            elif isinstance(val, str):
                return val
    if isinstance(raw, list):
        return raw[0] if raw else ""
    return str(raw) if raw else ""

def extract_notice(notice):
    notice_id = _first(notice.get("ND", ""))
    title = get_english_title(notice.get("TI", ""))
    deadline = _first(notice.get("DT", "")) or ""
    if deadline and "T" in deadline:
        deadline = deadline.split("T")[0]
    country = _first(notice.get("CY", "")) or ""
    value_high = _first(notice.get("TVH", None))
    value_low = _first(notice.get("TVL", None))
    estimated_value = value_high if value_high is not None else value_low
    cpv_raw = notice.get("PC", [])
    cpv_codes = "|".join(cpv_raw) if isinstance(cpv_raw, list) else str(cpv_raw)
    tender_url = TED_NOTICE_URL.format(notice_id=notice_id) if notice_id else ""
    description = get_description(notice)
    buyer_name = get_buyer_name(notice)
    return {
        "title": title,
        "deadline": deadline,
        "country": country,
        "estimated_value_eur": estimated_value,
        "tender_url": tender_url,
        "notice_id": notice_id,
        "cpv_codes": cpv_codes,
        "description": description,
        "buyer_name": buyer_name,
    }

def run_pass(session, cpv_clause, pages, label):
    """Fetch up to `pages` pages for a given CPV query clause."""
    records = []
    for page in range(1, pages + 1):
        try:
            data = fetch_page(session, page, cpv_clause)
        except requests.HTTPError as exc:
            log.error("[%s] HTTP error on page %d: %s", label, page, exc)
            break
        except requests.RequestException as exc:
            log.error("[%s] Network error on page %d: %s", label, page, exc)
            break

        notices = data.get("notices", [])
        if not notices:
            log.info("[%s] No more results on page %d - stopping.", label, page)
            break

        total = data.get("total", "unknown")
        log.info("[%s] Total available: %s | Retrieved so far: %d", label, total, len(records) + len(notices))

        for notice in notices:
            records.append(extract_notice(notice))

        if page < pages:
            time.sleep(SLEEP_BETWEEN_PAGES)
    return records

def main():
    import os
    os.makedirs("results", exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "ted-cpv-fetcher/1.0"})

    # Pass 1: broad general-medical sweep (unchanged behaviour)
    log.info("=== Pass 1: broad medical equipment (CPV 33100000), 3 pages ===")
    broad_records = run_pass(session, "classification-cpv=33100000", 3, "broad")

    # Pass 2: targeted gas-therapy / suction / anaesthesia sweep so these
    # niche categories get dedicated page budget instead of being crowded
    # out by higher-volume general medical device notices in Pass 1.
    # NOTE: using repeated "classification-cpv=X OR ..." rather than an IN(...)
    # clause — this OR/AND/= syntax is the form confirmed in TED's own expert
    # query examples; IN(...) support for this field was not confirmed, and a
    # malformed clause would silently return zero rather than erroring loudly.
    gas_cpv_clause = "(" + " OR ".join(f"classification-cpv={c}" for c in GAS_SUCTION_CPV_CODES) + ")"
    log.info("=== Pass 2: gas/suction/vacuum/anaesthesia CPV codes, %d pages ===", GAS_SUCTION_PAGES)
    gas_records = run_pass(session, gas_cpv_clause, GAS_SUCTION_PAGES, "gas-suction")

    # Merge + de-duplicate by notice_id (a record can appear in both passes)
    combined = {}
    for r in broad_records + gas_records:
        if r["notice_id"]:
            combined[r["notice_id"]] = r
    all_records = list(combined.values())

    log.info("Broad pass: %d | Gas/suction pass: %d | Combined unique: %d",
              len(broad_records), len(gas_records), len(all_records))

    if not all_records:
        log.warning("No records retrieved.")
        return

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nDone — {len(all_records)} tenders written to: {OUTPUT_CSV}")

main()
