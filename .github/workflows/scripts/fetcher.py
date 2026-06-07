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

def build_query(page):
    six_months_ago = (date.today() - timedelta(days=180)).strftime("%Y%m%d")
    today = date.today().strftime("%Y%m%d")
    print(f"Date range: {six_months_ago} to {today}")
    return {
        "query": f"classification-cpv=33100000 AND publication-date>={six_months_ago} AND publication-date<={today}",
        "fields": REQUESTED_FIELDS,
        "page": page,
        "limit": PAGE_SIZE,
        "scope": "ACTIVE",
        "paginationMode": "PAGE_NUMBER",
    }

def fetch_page(session, page):
    payload = build_query(page)
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

def main():
    import os
    os.makedirs("results", exist_ok=True)

    pages = 3
    session = requests.Session()
    session.headers.update({"User-Agent": "ted-cpv-fetcher/1.0"})
    all_records = []

    for page in range(1, pages + 1):
        try:
            data = fetch_page(session, page)
        except requests.HTTPError as exc:
            log.error("HTTP error on page %d: %s", page, exc)
            break
        except requests.RequestException as exc:
            log.error("Network error on page %d: %s", page, exc)
            break

        notices = data.get("notices", [])
        if not notices:
            log.info("No more results on page %d - stopping.", page)
            break

        total = data.get("total", "unknown")
        log.info("Total available: %s | Retrieved so far: %d", total, len(all_records) + len(notices))

        for notice in notices:
            all_records.append(extract_notice(notice))

        if page < pages:
            time.sleep(SLEEP_BETWEEN_PAGES)

    if not all_records:
        log.warning("No records retrieved.")
        return

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nDone — {len(all_records)} tenders written to: {OUTPUT_CSV}")

main()
