# GeBIZ live opportunities fetcher — UNAVAILABLE
#
# Singapore's only source of currently-open government tenders is the GeBIZ
# opportunities portal (https://www.gebiz.gov.sg/ptn/opportunity/index.xhtml).
# As of June 2026 it has no JSON API, RSS feed, or other machine-readable export.
#
# The portal is a JavaServer Faces (JSF) application: search/filter/pagination is
# done via stateful POST requests carrying a server-side ViewState token that is
# embedded in the previously rendered HTML and tied to a session cookie. There is
# no documented public endpoint that returns results as structured data — every
# request must replay a full browser session.
#
# The data.gov.sg "Government Procurement via GeBIZ" dataset
# (resource_id d_acde1106003906a75c3fa052592f2fcb) does have a clean REST API
# (https://data.gov.sg/api/action/datastore_search), but it only contains
# AWARDED/closed tenders (tender_detail_status is always one of "Awarded to
# Suppliers", "Awarded to No Suppliers", "Awarded by Items", "Award by interface
# record") with no deadline, tender URL, or pre-award value field — it cannot
# serve as an "open tenders" feed. See scripts/singapore_market_intel_fetcher.py
# for a fetcher that uses this dataset as historical market intelligence instead.
#
# To add live Singapore open-tender support in future: use playwright or selenium
# to drive the GeBIZ opportunity search form (filter by category/keyword, sort by
# closing date), then parse the rendered HTML table for title, agency, publication
# date, and closing date.

print("GeBIZ live opportunities API unavailable - skipping Singapore open tenders")
