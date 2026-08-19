"""FastAPI application entrypoint for agent-macaroon backend service."""

from fastapi import FastAPI

from audit.api import router as audit_router

app = FastAPI(title="agent-macaroon backend")
app.include_router(audit_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint for container liveness/readiness probes."""
    return {"status": "ok"}
