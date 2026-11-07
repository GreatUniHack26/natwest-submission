from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend import config
from backend import forecast as fc
from backend.forecast.inputs import ForecastDataUnavailable
from contracts.schemas import Alert, Forecast, PurchaseVerdict, SafeToSpend, SimulateRequest

router = APIRouter(prefix="/users/{user_id}", tags=["forecast"])


@router.get("/forecast", response_model=Forecast)
def get_forecast(user_id: str, days: int = Query(90, ge=7, le=365)):
    return _call(fc.forecast, user_id, days)


@router.get("/safe-to-spend", response_model=SafeToSpend)
def get_safe_to_spend(user_id: str):
    return _call(fc.safe_to_spend, user_id, config.TODAY)


@router.get("/alerts", response_model=list[Alert])
def get_alerts(user_id: str):
    return _call(fc.detect_alerts, user_id)


@router.post("/simulate", response_model=PurchaseVerdict)
def simulate(user_id: str, req: SimulateRequest):
    return _call(fc.simulate_purchase, user_id, req.amount, req.date or config.TODAY)


class WhatIfRequest(BaseModel):
    days: int = Field(default=90, ge=7, le=365, strict=True)
    overrides: dict[str, Any] = Field(default_factory=dict)


def _call(function, *args):
    try:
        return function(*args)
    except ForecastDataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, 'Unknown user') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/forecast/what-if', response_model=Forecast)
def what_if(user_id: str, req: WhatIfRequest):
    # A mock fixture cannot represent a supplied scenario.
    if config.MOCK_FORECAST:
        raise HTTPException(503, 'What-if scenarios require real forecast mode')
    return _call(fc.forecast, user_id, req.days, req.overrides)


@router.get('/spending-forecast')
def get_spending_forecast(user_id: str):
    return _call(fc.spending_forecast, user_id)


@router.get('/deposit-ideas')
def get_deposit_ideas(user_id: str):
    return _call(fc.deposit_ideas, user_id)


@router.get('/simulations')
def get_simulations(user_id: str, days: int = Query(90, ge=7, le=180), sims: int = Query(1000, ge=100, le=5000)):
    return _call(fc.simulate_futures, user_id, days, sims)


class TimelineRequest(BaseModel):
    days: int = Field(default=90, ge=7, le=180, strict=True)
    overrides: dict[str, Any] = Field(default_factory=dict)


@router.post('/timeline')
def post_timeline(user_id: str, req: TimelineRequest):
    return _call(fc.timeline, user_id, req.days, req.overrides or None)
