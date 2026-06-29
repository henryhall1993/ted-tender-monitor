# Sell2Wales fetcher — UNAVAILABLE
#
# Sell2Wales (https://www.sell2wales.gov.wales) has no working public API as of June 2026.
# The OCDS API at https://api.sell2wales.gov.wales/v1/Notices returns a 500 SQL error
# ("Error converting data type nvarchar to float") for all requests, including the
# vendor's own documented example URLs.
#
# A bulk download portal exists at /Notice/Download/Download.aspx offering JSON/XML/CSV
# exports by month, but it is an ASP.NET WebForms page that requires a live browser
# session (ViewState + server-side session cookies) to complete the form submission.
# Programmatic POST requests return "An error has occurred" with no data.
#
# Welsh NHS trusts do not appear to post on Contracts Finder or Find a Tender Service —
# Sell2Wales is their exclusive procurement portal. There is no accessible fallback.
#
# To add Wales support in future: use playwright or selenium to automate the download
# form, selecting OCDS JSON format for each month, then parse the downloaded files using
# the same CPV-33 filter strategy as the Scotland fetcher.

print("Sell2Wales API unavailable - skipping Wales")
