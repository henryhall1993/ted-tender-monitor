import requests

url = "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices/json"

CPV_CODES = [
    # Root medical/pharma/personal care
    "33000000",
    # Medical equipment
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
]

payload = {
    "searchCriteria": {
        "types": ["Contract"],
        "statuses": ["Open"],
        "cpvCodes": CPV_CODES,
    },
    "size": 100
}

headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

resp = requests.post(url, json=payload, headers=headers, timeout=30)
data = resp.json()

all_notices = data.get("noticeList", [])

print(f"Status code  : {resp.status_code}")
print(f"API hit count: {data.get('hitCount')}")
print(f"Returned     : {len(all_notices)}\n")

for i, entry in enumerate(all_notices[:5], 1):
    item = entry["item"]
    print(f"[{i}] {item.get('title')}")
    print(f"     Organisation : {item.get('organisationName')}")
    print(f"     Value low    : {item.get('valueLow')}")
    print(f"     Value high   : {item.get('valueHigh')}")
    print(f"     Deadline     : {item.get('deadlineDate', '')[:10]}")
    print(f"     Notice ID    : {item.get('noticeIdentifier')}")
    print(f"     CPV codes    : {item.get('cpvCodes')} | {item.get('cpvDescription')}")
    print()
