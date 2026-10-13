import csv
from datetime import datetime, timedelta, timezone

import backend.services.historical_backtest as historical_backtest
from backend.app import app


def write_prices(path, symbol='TEST.NS', closes=None):
    closes = closes or list(range(1, 101))
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=['timestamp', 'symbol', 'close'])
        writer.writeheader()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for index, close in enumerate(closes):
            writer.writerow({
                'timestamp': int((start + timedelta(days=index)).timestamp()),
                'symbol': symbol,
                'close': close,
            })


def test_historical_backtest_calculates_from_csv_closes(tmp_path, monkeypatch):
    path = tmp_path / 'history.csv'
    write_prices(path)
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', path)

    result = historical_backtest.run_historical_backtest('TEST', 100000)

    assert result['data_source'] == 'Historical CSV'
    assert result['observations'] == 100
    assert result['start_date'] == '2025-01-01'
    assert result['end_date'] == '2025-04-10'
    assert result['total_trades'] == 1
    assert result['total_return'] == 100
    assert result['final_value'] == 200000


def test_backtest_api_lists_and_runs_historical_symbols(tmp_path, monkeypatch):
    path = tmp_path / 'history.csv'
    write_prices(path)
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', path)
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

    symbols = client.get('/api/backtest/instruments', headers=headers)
    assert symbols.status_code == 200
    assert symbols.get_json()['data_source'] == 'Historical CSV'
    assert symbols.get_json()['data'][0]['symbol'] == 'TEST'

    response = client.post('/api/backtest', headers=headers, json={
        'symbol': 'TEST',
        'initial_capital': 100000,
    })
    assert response.status_code == 200
    assert response.get_json()['data']['data_source'] == 'Historical CSV'
    assert response.get_json()['data']['total_return'] == 100


def test_historical_backtest_rejects_unknown_symbols(tmp_path, monkeypatch):
    path = tmp_path / 'history.csv'
    write_prices(path)
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', path)

    try:
        historical_backtest.run_historical_backtest('MISSING', 100000)
    except LookupError as error:
        assert 'not available in the historical CSV' in str(error)
    else:
        raise AssertionError('Unknown historical symbols must be rejected.')
