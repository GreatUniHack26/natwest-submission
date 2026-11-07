"""Shared API change: requires all-five approval before merge."""
from fastapi import APIRouter, HTTPException, Query

from backend import forecast as fc
from backend.forecast.inputs import ForecastDataUnavailable
from contracts.schemas import Forecast, SafeToSpend

router = APIRouter(prefix='/households/{household_id}', tags=['forecast'])


@router.get('/forecast', response_model=Forecast)
def get_household_forecast(household_id: str, days: int = Query(90, ge=7, le=365)):
    try:
        return fc.household_forecast(household_id, days)
    except ForecastDataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, 'Unknown or empty household') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/safe-to-spend', response_model=SafeToSpend)
def get_household_safe_to_spend(household_id: str):
    try:
        return fc.household_safe_to_spend(household_id)
    except ForecastDataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, 'Unknown or empty household') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
