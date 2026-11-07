import datetime as dt
import json

import pytest

from backend import forecast
from backend.agent import tools
from backend.forecast import sales


def test_one_calendar_and_black_friday(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert forecast.upcoming_sales(42)[0]['date'] == '2026-11-27'
    assert tools.get_upcoming_sales(42) == forecast.upcoming_sales(42)


def test_sort_boundaries_and_no_mutation(monkeypatch, tmp_path):
    path = tmp_path / 'sales.json'
    rows = [{'name':'Later','date':'2026-11-09','categories':['general']},
            {'name':'Today','date':'2026-11-07','categories':['general']},
            {'name':'Outside','date':'2026-11-10','categories':['general']}]
    path.write_text(json.dumps(rows))
    monkeypatch.setattr(sales, 'CALENDAR_PATH', path)
    assert [s['name'] for s in forecast.upcoming_sales(2)] == ['Today','Later']
    assert len(forecast.upcoming_sales(0)) == 1
    assert forecast.upcoming_sales(2, as_of=dt.date(2027,1,1)) == []
    assert json.loads(path.read_text()) == rows


@pytest.mark.parametrize('content', [None, '{}', 'bad json', '[{}]', '[{"name":"Sale","date":"bad"}]'])
def test_unavailable_calendar(monkeypatch, tmp_path, content):
    path = tmp_path/'sales.json'
    if content is not None: path.write_text(content)
    monkeypatch.setattr(sales, 'CALENDAR_PATH', path)
    with pytest.raises(sales.CalendarUnavailable): forecast.upcoming_sales()


@pytest.mark.parametrize('days', [-1,366,True,3.5])
def test_invalid_window(days):
    with pytest.raises(ValueError): forecast.upcoming_sales(days)
