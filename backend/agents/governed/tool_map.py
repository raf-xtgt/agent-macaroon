"""Custom tool-to-action-verb mapping for the target fleet (global-kyc-agent).

If this file exists, the governed wrapper uses TOOL_ACTION_MAP instead of the
default (all tools -> "read"). Delete this file to use the default.

Export TOOL_ACTION_MAP (required) and optionally INITIAL_SCOPE.
"""

TOOL_ACTION_MAP: dict[str, str] = {
    # UK Companies House
    "search_companies": "search",
    "get_company_profile": "retrieve",
    "get_company_officers": "retrieve",
    "get_company_charges": "retrieve",
    "get_company_insolvency": "retrieve",
    "get_company_exemptions": "retrieve",
    "get_company_filing_history": "retrieve",
    "get_company_filing_detail": "retrieve",
    "get_corporate_officer_disqualifications": "retrieve",
    "get_natural_officer_disqualifications": "retrieve",
    "get_office_appointments": "retrieve",
    "get_company_establishments": "retrieve",
    "get_company_registers": "retrieve",
    # USA SEC
    "full_text_search": "search",
    "get_recent_filings": "retrieve",
    "extract_filing_section": "retrieve",
    "get_insider_transactions": "retrieve",
    # Shared
    "google_search": "search",
    "get_current_date": "read",
}

INITIAL_SCOPE: set[str] = {"search", "retrieve", "read", "delegate"}
