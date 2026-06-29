import csv
import json
import os
from datetime import date

def csv_to_list(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath} — skipping")
        return []
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def main():
    os.makedirs("results", exist_ok=True)

    eu       = csv_to_list("results/ted_medical_devices_parsed.csv")
    uk       = csv_to_list("results/uk_medical_devices.csv")
    scotland = csv_to_list("results/scotland_medical_devices_parsed.csv")

    # Tag each record with its source
    for r in eu:
        r["source"] = "EU"
    for r in uk:
        r["source"] = "UK"
    for r in scotland:
        r["source"] = "Scotland"

    combined = eu + uk + scotland

    # Sort by quality score descending, then by deadline ascending
    def sort_key(r):
        score = int(r.get("quality_score", 0) or 0)
        deadline = r.get("deadline", "") or "9999"
        return (-score, deadline)

    combined.sort(key=sort_key)

    output = {
        "generated": date.today().isoformat(),
        "total": len(combined),
        "tenders": combined
    }

    output_path = "results/tenders.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Done — {len(combined)} tenders written to {output_path}")
    print(f"  EU: {len(eu)} | UK: {len(uk)} | Scotland: {len(scotland)}")

main()
