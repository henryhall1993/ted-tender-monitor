import anthropic
import csv
import os
import time

import sys
print("Python version:", sys.version)
print("Starting parser...")
print("API key present:", bool(os.environ.get("ANTHROPIC_API_KEY")))
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

INPUT_CSV = "results/ted_medical_devices.csv"
OUTPUT_CSV = "results/ted_medical_devices_parsed.csv"

OUTPUT_COLUMNS = [
    "quality_score",
    "notice_id",
    "original_title",
    "buyer_name",
    "country",
    "deadline",
    "estimated_value_eur",
    "tender_url",
    "english_summary",
    "what_they_want",
    "eligibility_requirements",
    "evaluation_criteria",
    "language_detected",
]

PROMPT_TEMPLATE = """You are a procurement analyst specialising in medical devices.
Below is a public tender notice from the EU (European Union) or associated countries.
Read it carefully and extract the key commercial details in clear English,
regardless of what language it is written in.

Return ONLY the following fields, each on its own line in this exact format.
If a field is not mentioned in the notice, write NOT FOUND for that field.
Do not add any extra text, headers, or explanation outside these fields.

ENGLISH_SUMMARY: (2-3 sentence overview of what this tender is for)
WHAT_THEY_WANT: (specific medical devices, equipment, or services being procured. Include model numbers or brands if mentioned)
ELIGIBILITY_REQUIREMENTS: (who can bid - certifications, experience, company size requirements)
EVALUATION_CRITERIA: (how bids will be judged - price weighting, quality weighting, etc)
LANGUAGE_DETECTED: (the language the document is written in)

TENDER NOTICE TITLE: {title}
BUYER: {buyer}
COUNTRY: {country}
DESCRIPTION:
{description}
"""

def parse_with_claude(title, buyer, country, description):
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_TEMPLATE.format(
                        title=title,
                        buyer=buyer,
                        country=country,
                        description=description if description else "No description available."
                    )
                }
            ]
        )
        return message.content[0].text
    except Exception as e:
        return f"PARSE_ERROR: {e}"

def extract_field(response_text, field_name):
    for line in response_text.split('\n'):
        if line.startswith(f"{field_name}:"):
            return line[len(f"{field_name}:"):].strip()
    return ""

def score_quality(row):
    score = 0
    if row["english_summary"] and row["english_summary"] != "NOT FOUND":
        score += 1
    if row["what_they_want"] and row["what_they_want"] != "NOT FOUND":
        score += 1
    if row["eligibility_requirements"] and row["eligibility_requirements"] != "NOT FOUND":
        score += 1
    if row["evaluation_criteria"] and row["evaluation_criteria"] != "NOT FOUND":
        score += 1
    return score

def main():
    results = []

    with open(INPUT_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Found {len(rows)} tenders. Processing all...\n")

    for i, row in enumerate(rows):
        notice_id = row.get("notice_id", "")
        title = row.get("title", "")
        buyer = row.get("buyer_name", "")
        country = row.get("country", "")
        description = row.get("description", "")

        print(f"[{i+1}/{len(rows)}] Processing {notice_id} — {title}")

        if not description:
            print(f"  ✗ No description — skipping")
            claude_response = ""
        else:
            print(f"  ✓ Parsing with Claude...")
            claude_response = parse_with_claude(title, buyer, country, description)

        result = {
            "notice_id": notice_id,
            "original_title": title,
            "buyer_name": buyer,
            "country": country,
            "deadline": row.get("deadline", ""),
            "estimated_value_eur": row.get("estimated_value_eur", ""),
            "tender_url": row.get("tender_url", ""),
            "english_summary": extract_field(claude_response, "ENGLISH_SUMMARY"),
            "what_they_want": extract_field(claude_response, "WHAT_THEY_WANT"),
            "eligibility_requirements": extract_field(claude_response, "ELIGIBILITY_REQUIREMENTS"),
            "evaluation_criteria": extract_field(claude_response, "EVALUATION_CRITERIA"),
            "language_detected": extract_field(claude_response, "LANGUAGE_DETECTED"),
        }

        result["quality_score"] = score_quality(result)
        print(f"  → Quality score: {result['quality_score']}/4")
        results.append(result)

        time.sleep(1)

    results.sort(key=lambda x: x["quality_score"], reverse=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone — {len(results)} tenders parsed and saved to {OUTPUT_CSV}")
    print("Quality breakdown:")
    for score in range(4, -1, -1):
        count = sum(1 for r in results if r["quality_score"] == score)
        if count:
            print(f"  {score}/4 stars: {count} tenders")

main()
