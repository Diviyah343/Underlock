from fastapi import FastAPI

from shared.schemas import HealthResponse

app = FastAPI(title="Underlock Scoring Service", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
