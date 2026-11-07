from fastapi import APIRouter, Query

from backend import config
from backend import forecast as fc
from contracts.schemas import Alert, Forecast, PurchaseVerdict, SafeToSpend, SimulateRequest

router = APIRouter(prefix="/users/{user_id}", tags=["forecast"])


@router.get("/forecast", response_model=Forecast)
def get_forecast(user_id: str, days: int = Query(90, ge=7, le=365)):
    return fc.forecast(user_id, days)


@router.get("/safe-to-spend", response_model=SafeToSpend)
def get_safe_to_spend(user_id: str):
    return fc.safe_to_spend(user_id, config.TODAY)


@router.get("/alerts", response_model=list[Alert])
def get_alerts(user_id: str):
    return fc.detect_alerts(user_id)


@router.post("/simulate", response_model=PurchaseVerdict)
def simulate(user_id: str, req: SimulateRequest):
    return fc.simulate_purchase(user_id, req.amount, req.date or config.TODAY)
