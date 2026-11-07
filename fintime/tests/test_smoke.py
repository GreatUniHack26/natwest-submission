"""Run: pytest -q.  Guards the contracts and the API in mock mode."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from contracts import schemas

client = TestClient(app)
FIXTURES = Path(__file__).parent.parent / "contracts" / "fixtures"

# fixture file -> (model, is_list)
FIXTURE_MODELS = {
    "user": (schemas.User, False),
    "transactions": (schemas.Transaction, True),
    "pots": (schemas.Pot, True),
    "forecast": (schemas.Forecast, False),
    "safe_to_spend": (schemas.SafeToSpend, False),
    "verdict": (schemas.PurchaseVerdict, False),
    "alerts": (schemas.Alert, True),
    "chat": (schemas.ChatReply, False),
}


@pytest.mark.parametrize("name", FIXTURE_MODELS)
def test_fixture_matches_contract(name):
    model, is_list = FIXTURE_MODELS[name]
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    for item in data if is_list else [data]:
        model(**item)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/health", None),
        ("get", "/users/sam", None),
        ("get", "/users/sam/transactions", None),
        ("get", "/users/sam/pots", None),
        ("get", "/users/sam/forecast?days=56", None),
        ("get", "/users/sam/safe-to-spend", None),
        ("get", "/users/sam/alerts", None),
        ("post", "/users/sam/simulate", {"amount": 30}),
        ("post", "/users/sam/chat", {"message": "Can I afford this shirt?"}),
    ],
)
def test_endpoints_in_mock_mode(method, path, body):
    r = getattr(client, method)(path, **({"json": body} if body else {}))
    assert r.status_code == 200, r.text
