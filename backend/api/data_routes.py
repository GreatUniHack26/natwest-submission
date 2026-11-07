import datetime as dt
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend import data
from backend.data.repository import DuplicatePotError, UnknownUserError
from contracts.schemas import CategoryOverride, Pot, Transaction, User

router = APIRouter(prefix="/users/{user_id}", tags=["data"])


@router.get("", response_model=User)
def get_user(user_id: str):
    try:
        return data.get_user(user_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=e.args[0])


@router.get("/transactions", response_model=list[Transaction])
def get_transactions(user_id: str, start: Optional[dt.date] = None, end: Optional[dt.date] = None):
    return data.get_transactions(user_id, start, end)


@router.patch("/transactions/{transaction_id}", response_model=Transaction)
def override_transaction(user_id: str, transaction_id: str, body: CategoryOverride):
    try:
        return data.set_override(user_id, transaction_id, body.category, body.kind)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=e.args[0])
    except ValueError as e:  # e.g. category is only whitespace
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/pots", response_model=list[Pot])
def get_pots(user_id: str):
    return data.get_pots(user_id)


@router.post("/pots", response_model=Pot)
def add_pot(user_id: str, pot: Pot):
    try:
        return data.add_pot(pot)
    except UnknownUserError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicatePotError as e:
        raise HTTPException(status_code=409, detail=str(e))
