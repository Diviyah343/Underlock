from fastapi import FastAPI

from app.routers import alerts, investigations, settings, transactions

app = FastAPI(
    title="Financial Safety Dashboard API",
    version="0.1.0",
)

app.include_router(alerts.router)
app.include_router(transactions.router)
app.include_router(investigations.router)
app.include_router(settings.router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
