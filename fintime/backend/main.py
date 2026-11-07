from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.api import agent_routes, data_routes, forecast_routes

app = FastAPI(title="FinTime API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(data_routes.router)
app.include_router(forecast_routes.router)
app.include_router(agent_routes.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "mock": {"data": config.MOCK_DATA, "forecast": config.MOCK_FORECAST, "agent": config.MOCK_AGENT},
    }
