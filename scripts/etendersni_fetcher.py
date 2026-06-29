# eTendersNI fetcher — UNAVAILABLE
#
# eTendersNI (https://www.etendersni.gov.uk) has no working public API as of June 2026.
# The site runs on European Dynamics' EPPS platform, a closed commercial e-procurement
# system with no REST API, OCDS data feed, or bulk download capability.
#
# All unknown paths redirect to the homepage. The EPPS search endpoint
# (/epps/cft/listContractNotices.do) returns a 500 error. Northern Ireland is not
# listed in the OCP Data Registry and NI public bodies do not cross-post to
# Contracts Finder or Find a Tender Service.
#
# To add Northern Ireland support in future: use playwright or selenium to scrape
# the search results at /epps/prepareAdvancedSearch.do?type=cftFTS, filtering by
# CPV code 33 (medical/surgical equipment). Results would need HTML parsing as there
# is no structured data format available.

print("eTendersNI API unavailable - skipping Northern Ireland")
