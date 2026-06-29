import csv
import logging
import re
import time
import requests

BASE_URL = "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices/json"
OUTPUT_CSV = "results/uk_medical_devices.csv"
PAGE_SIZE = 100
MAX_PAGES_PER_KEYWORD = 5  # safety cap (~500 results per keyword)

CPV_CODES = [
    "33000000",
    "33100000", "33110000", "33111000", "33112000", "33113000",
    "33114000", "33115000", "33116000", "33120000", "33121000",
    "33122000", "33123000", "33124000", "33125000", "33126000",
    "33127000", "33128000", "33130000", "33131000", "33132000",
    "33133000", "33134000", "33135000", "33136000", "33137000",
    "33138000", "33140000", "33141000", "33141100", "33141200",
    "33141300", "33141400", "33141500", "33141600", "33141700",
    "33141800", "33141900", "33150000", "33151000", "33152000",
    "33153000", "33154000", "33155000", "33156000", "33157000",
    "33158000", "33159000", "33160000", "33161000", "33162000",
    "33163000", "33164000", "33165000", "33166000", "33167000",
    "33168000", "33169000", "33170000", "33171000", "33172000",
    "33180000", "33181000", "33182000", "33183000", "33184000",
    "33185000", "33186000", "33190000", "33191000", "33192000",
    "33193000", "33194000", "33195000", "33196000", "33197000",
    "33198000", "33199000",
    "33600000", "33610000", "33620000", "33630000", "33640000",
    "33650000", "33651000", "33651600", "33660000", "33670000",
    "33680000", "33690000", "33700000", "33710000", "33720000",
    "33730000", "33740000", "33750000", "33760000", "33770000",
    "33790000", "33900000", "33930000", "33940000", "33950000",
    "33960000", "33970000", "33980000", "33990000",
    # Health services (clinical only — excludes broad social care codes)
    "85100000", "85110000", "85111000", "85111200", "85120000",
    "85130000", "85140000", "85150000", "85160000",
]

KEYWORDS = [
    "medical device",
    "surgical equipment",
    "patient monitoring",
    "medical gas",
    "diagnostic imaging",
    "wound care",
    "infusion pump",
    "medical supplies",
    "hospital equipment",
    "theatre equipment",
]

NOISE_KEYWORDS = [
    "tree", "waste", "cleaning", "catering", "security guard", "grounds",
    "landscaping", "pest control", "parking", "printing", "translation",
    "legal services", "insurance", "software", "it services", "consultancy",
]

_NOISE_RE   = [re.compile(r"\b" + re.escape(nk) + r"\b") for nk in NOISE_KEYWORDS]
_KEYWORD_RE = [re.compile(r"\b" + re.escape(kw) + r"\b") for kw in KEYWORDS]

# Set of accepted CPV codes for fast membership testing in is_relevant.
# A notice passes if ANY of its space-separated CPV codes is in this set
# or starts with "33" (medical equipment — too many sub-codes to enumerate).
_ACCEPTED_CPV_SET = set(CPV_CODES)

CSV_COLUMNS = [
    "title", "deadline", "country", "estimated_value_eur",
    "tender_url", "notice_id", "cpv_codes", "description", "buyer_name",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _post(payload):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=30)
    if not resp.ok:
        log.error("API error %s: %s", resp.status_code, resp.text[:200])
        resp.raise_for_status()
    return resp.json()


def fetch_cpv():
    """Fetch all open notices that carry a medical CPV code."""
    items = []
    page  = 1
    while True:
        data = _post({
            "searchCriteria": {"types": ["Contract"], "statuses": ["Open"], "cpvCodes": CPV_CODES},
            "size": PAGE_SIZE,
            "page": page,
        })
        batch = data.get("noticeList", [])
        if not batch:
            break
        items.extend(e["item"] for e in batch)
        log.info("CPV page %d: +%d (total %d)", page, len(batch), len(items))
        if len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(1)
    return items


def fetch_keyword(keyword, published_from):
    """Fetch notices for a single keyword, limited to the last 6 months."""
    items = []
    page  = 1
    while page <= MAX_PAGES_PER_KEYWORD:
        data = _post({
            "searchCriteria": {
                "types": ["Contract"],
                "statuses": ["Open"],
                "keyword": keyword,
                "publishedFrom": published_from,
            },
            "size": PAGE_SIZE,
            "page": page,
        })
        batch = data.get("noticeList", [])
        if not batch:
            break
        items.extend(e["item"] for e in batch)
        log.info("  keyword='%s' page=%d: +%d (total %d)", keyword, page, len(batch), len(items))
        if len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(1)
    if page > MAX_PAGES_PER_KEYWORD:
        log.warning("  keyword='%s' hit page cap (%d); results may be incomplete", keyword, MAX_PAGES_PER_KEYWORD)
    return items


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_notice(item):
    deadline = item.get("deadlineDate", "")
    if deadline and "T" in deadline:
        deadline = deadline.split("T")[0]

    return {
        "title":               item.get("title", ""),
        "deadline":            deadline,
        "country":             "GBR",
        "estimated_value_eur": item.get("valueLow") or item.get("valueHigh") or "",
        "tender_url": (
            f"https://www.contractsfinder.service.gov.uk/Notice/Notice/Details/{item['id']}"
            if item.get("id") else ""
        ),
        "notice_id":  item.get("noticeIdentifier", ""),
        "cpv_codes":  item.get("cpvCodes", ""),
        "description": (item.get("description", "") or "")[:4000],
        "buyer_name": item.get("organisationName", ""),
        # Internal fields for relevance filtering — stripped before CSV write
        "_cpv_description": " ".join(filter(None, [
            item.get("cpvDescription", ""),
            item.get("cpvDescriptionExpanded", ""),
        ])),
        "_from_cpv_search": False,  # set by caller
    }


# ---------------------------------------------------------------------------
# Relevance & noise filters
# ---------------------------------------------------------------------------

def is_relevant(record):
    """Keep if an accepted CPV code is present, OR title contains a medical keyword."""
    title_lower = record["title"].lower()

    # Noise in title → always drop
    if any(p.search(title_lower) for p in _NOISE_RE):
        return False

    # Check each CPV code on the notice (space-separated field)
    for code in (record.get("cpv_codes") or "").split():
        if code.startswith("33") or code in _ACCEPTED_CPV_SET:
            return True

    # Medical keyword in title (word-boundary matched)
    if any(p.search(title_lower) for p in _KEYWORD_RE):
        return True

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import os
    from datetime import date, timedelta
    os.makedirs("results", exist_ok=True)

    published_from = (date.today() - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00")
    print(f"Date range: last 6 months (from {published_from[:10]})\n")

    all_items = []

    # --- Phase 1: CPV search ---
    log.info("=== Phase 1: CPV-based search ===")
    cpv_items = fetch_cpv()
    for item in cpv_items:
        r = extract_notice(item)
        r["_from_cpv_search"] = True
        all_items.append(r)
    log.info("CPV search returned %d notices", len(cpv_items))

    # --- Phase 2: Keyword searches ---
    log.info("=== Phase 2: Keyword searches (last 6 months) ===")
    for kw in KEYWORDS:
        log.info("Searching keyword: '%s'", kw)
        try:
            kw_items = fetch_keyword(kw, published_from)
        except requests.RequestException as exc:
            log.error("Failed for keyword '%s': %s", kw, exc)
            time.sleep(2)
            continue
        for item in kw_items:
            all_items.append(extract_notice(item))
        time.sleep(2)

    # --- Deduplicate by notice_id ---
    seen = {}
    for r in all_items:
        nid = r["notice_id"]
        if nid and nid not in seen:
            seen[nid] = r
    records = list(seen.values())
    log.info("After deduplication: %d unique notices", len(records))

    # --- Relevance filter — track each stage separately ---
    total_before = len(records)

    noise_dropped = [r for r in records if any(
        p.search(r["title"].lower()) for p in _NOISE_RE)]
    after_noise   = [r for r in records if not any(
        p.search(r["title"].lower()) for p in _NOISE_RE)]

    # Among non-noise records, categorise what kept them
    def _cpv_match(r):
        return any(
            c.startswith("33") or c in _ACCEPTED_CPV_SET
            for c in (r.get("cpv_codes") or "").split()
        )

    cpv_kept          = [r for r in after_noise if _cpv_match(r)]
    keyword_kept      = [r for r in after_noise if not _cpv_match(r)
                         and any(p.search(r["title"].lower()) for p in _KEYWORD_RE)]
    relevance_dropped = [r for r in after_noise if not _cpv_match(r)
                         and not any(p.search(r["title"].lower()) for p in _KEYWORD_RE)]

    records = cpv_kept + keyword_kept  # same logic as is_relevant, post noise-drop

    print(f"\n--- Filter summary ---")
    print(f"Total unique (before filter)        : {total_before}")
    print(f"Dropped — noise keyword in title    : {len(noise_dropped)}")
    print(f"Dropped — no accepted CPV & no kw   : {len(relevance_dropped)}")
    print(f"Kept — accepted CPV code            : {len(cpv_kept)}")
    print(f"Kept — medical keyword in title     : {len(keyword_kept)}")
    print(f"Final count                         : {len(records)}")

    print("First 15 titles:")
    for r in records[:15]:
        print(f"  [{r['cpv_codes'] or 'no-cpv':12s}] {r['title']} | {r['buyer_name']}")
    print()

    # Strip internal fields before writing
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows({k: v for k, v in r.items() if k in CSV_COLUMNS} for r in records)

    print(f"Done — {len(records)} UK medical device tenders written to: {OUTPUT_CSV}")


main()
