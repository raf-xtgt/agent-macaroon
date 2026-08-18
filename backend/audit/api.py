"""FastAPI router for F6 replay data: GET /audit/replay?chain_id=... returns the ordered
span timeline as JSON (queries Firestore server-side via audit/replay.py). Consumed by the
Next.js frontend (../../frontend/) — no login, no credential entry, single-tenant
(see agent-specification.md §8). This module never renders HTML; the UI lives in frontend/.
"""

# TODO: implemented in a later milestone — see AGENTS.md
