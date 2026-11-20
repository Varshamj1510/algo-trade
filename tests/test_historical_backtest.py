import csv
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import backend.services.historical_backtest as historical_backtest
from backend.app import app


def write_prices(path, symbol='TEST.NS', closes=None):
    closes = closes or list(range(1, 101))
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(
            output,
            fieldnames=['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume'],
        )
        writer.writeheader()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for index, close in enumerate(closes):
            writer.writerow({
                'timestamp': int((start + timedelta(days=index)).timestamp()),
                'symbol': symbol,
                'open': close - 0.5,
                'high': close + 1,
                'low': close - 1,
                'close': close,
                'volume': 1000 + index,
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
    assert 0 < result['total_return'] < 100
    assert result['total_return'] == result['benchmark_return']
    assert result['commission_pct_per_side'] == 0.05
    assert result['slippage_pct_per_side'] == 0.05
    assert result['period_comparison'][0]['period'] == 'Available history'


def test_historical_universe_and_chart_merge_csv_files(tmp_path, monkeypatch):
    write_prices(tmp_path / 'banking.csv', symbol='BANKTEST.NS', closes=list(range(100, 201)))
    write_prices(tmp_path / 'energy.csv', symbol='ENERGYTEST.NS', closes=list(range(200, 301)))
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', tmp_path)

    universe = historical_backtest.get_historical_universe()
    banking_candles = historical_backtest.get_csv_chart_candles('BANKTEST', '1Y')
    energy_candles = historical_backtest.get_csv_chart_candles('ENERGYTEST', '1Y')

    assert [item['symbol'] for item in universe] == ['BANKTEST', 'ENERGYTEST']
    assert banking_candles[0]['close'] == 100
    assert energy_candles[0]['close'] == 200


def test_historical_loader_rejects_conflicting_duplicate_days(tmp_path, monkeypatch):
    write_prices(tmp_path / 'first.csv', symbol='TEST.NS', closes=[100, 101])
    write_prices(tmp_path / 'second.csv', symbol='TEST.NS', closes=[100, 102])
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', tmp_path)

    try:
        historical_backtest.get_historical_universe()
    except ValueError as error:
        assert 'conflicting closes for TEST on' in str(error)
    else:
        raise AssertionError('Conflicting per-day market data must be rejected.')


def test_close_only_csv_does_not_block_chart_ohlcv_files(tmp_path, monkeypatch):
    close_only_path = tmp_path / 'backtest-only.csv'
    close_only_path.write_text(
        'timestamp,symbol,close\n1735689600,CLOSEONLY.NS,100\n',
        encoding='utf-8',
    )
    write_prices(tmp_path / 'charts.csv', symbol='CHARTTEST.NS', closes=list(range(100, 201)))
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', tmp_path)

    universe = historical_backtest.get_historical_universe()
    candles = historical_backtest.get_csv_chart_candles('CHARTTEST', '1Y')

    assert {item['symbol'] for item in universe} == {'CHARTTEST', 'CLOSEONLY'}
    assert len(candles) == 101


def test_costs_reduce_returns_and_full_history_reports_multiple_windows(tmp_path, monkeypatch):
    path = tmp_path / 'history.csv'
    write_prices(path, closes=list(range(100, 1400)))
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', path)

    gross = historical_backtest.run_historical_backtest('TEST', 100000, 0, 0)
    net = historical_backtest.run_historical_backtest('TEST', 100000)

    assert net['total_return'] < gross['total_return']
    assert [item['period'] for item in net['period_comparison']] == ['1Y', '3Y', '5Y']
    assert [item['observations'] for item in net['period_comparison']] == [252, 756, 1260]
    assert all(item['total_return'] == item['benchmark_return'] for item in net['period_comparison'])


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

    invalid_costs = client.post('/api/backtest', headers=headers, json={
        'symbol': 'TEST',
        'initial_capital': 100000,
        'commission_pct': 1.01,
        'slippage_pct': 0.05,
    })
    assert invalid_costs.status_code == 422

    response = client.post('/api/backtest', headers=headers, json={
        'symbol': 'TEST',
        'initial_capital': 100000,
        'commission_pct': 0.1,
        'slippage_pct': 0.2,
    })
    assert response.status_code == 200
    assert response.get_json()['data']['data_source'] == 'Historical CSV'
    result = response.get_json()['data']
    assert 0 < result['total_return'] < 100
    assert result['benchmark_return'] == result['total_return']
    assert result['commission_pct_per_side'] == 0.1
    assert result['slippage_pct_per_side'] == 0.2
    assert result['period_comparison'][0]['period'] == 'Available history'

    history = client.get('/api/backtest/history', headers=headers)
    assert history.status_code == 200
    assert any(item['symbol'] == 'TEST' for item in history.get_json()['data'])

    other_client = app.test_client()
    suffix = uuid4().hex
    other_registration = other_client.post('/api/auth/register', json={
        'full_name': 'Other Backtest User',
        'email': f'other-backtest-{suffix}@example.test',
        'username': f'other-backtest-{suffix}',
        'password': 'other-backtest-password',
    })
    assert other_registration.status_code == 201
    other_headers = {'Authorization': f"Bearer {other_registration.get_json()['token']}"}
    other_history = other_client.get('/api/backtest/history', headers=other_headers)
    assert other_history.status_code == 200
    assert other_history.get_json()['data'] == []


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


def test_csv_chart_candles_and_pattern_detection(tmp_path, monkeypatch):
    path = tmp_path / 'history.csv'
    write_prices(path, closes=[100, 99, 98, 98, 101, 103])
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', path)

    candles = historical_backtest.get_csv_chart_candles('TEST', '3M')
    patterns = historical_backtest.detect_candlestick_patterns(candles)

    assert len(candles) == 6
    assert candles[0]['time'] == '2025-01-01'
    assert candles[0]['open'] == 99.5
    assert candles[0]['volume'] == 1000
    bullish_engulfing = [
        {'time': '2025-01-01', 'open': 100, 'high': 101, 'low': 98, 'close': 99, 'volume': 10},
        {'time': '2025-01-02', 'open': 98.5, 'high': 102, 'low': 98, 'close': 101, 'volume': 12},
    ]
    assert historical_backtest.detect_candlestick_patterns(bullish_engulfing) == [{
        'index': 1,
        'date': '2025-01-02',
        'name': 'Bullish engulfing',
        'direction': 'bullish',
    }]


def test_candlestick_pattern_detector_recognizes_doji_spinning_top_and_marubozu():
    candles = [
        {'time': '2025-01-01', 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 10},
        {'time': '2025-01-02', 'open': 100, 'high': 104, 'low': 96, 'close': 101, 'volume': 10},
        {'time': '2025-01-03', 'open': 100, 'high': 105, 'low': 100, 'close': 105, 'volume': 10},
    ]

    patterns = historical_backtest.detect_candlestick_patterns(candles)

    assert [(pattern['name'], pattern['direction']) for pattern in patterns] == [
        ('Doji', 'neutral'),
        ('Spinning top', 'neutral'),
        ('Marubozu', 'bullish'),
    ]


def test_csv_chart_rejects_invalid_ohlc_rows(tmp_path, monkeypatch):
    path = tmp_path / 'history.csv'
    write_prices(path, closes=[100])
    with path.open(encoding='utf-8') as source:
        rows = list(csv.DictReader(source))
    rows[0]['high'] = '90'
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', path)

    try:
        historical_backtest.get_csv_chart_candles('TEST', '3M')
    except ValueError as error:
        assert 'invalid demo candle' in str(error)
    else:
        raise AssertionError('Invalid OHLC data must not be charted.')


def test_candlestick_chart_api_returns_csv_candles_and_detected_patterns(tmp_path, monkeypatch):
    path = tmp_path / 'history.csv'
    write_prices(path, closes=[100, 99, 98, 98, 101, 103])
    monkeypatch.setattr(historical_backtest, 'HISTORICAL_DATA_PATH', path)
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com', 'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

    response = client.get(
        '/api/candlestick-chart?symbol=TEST&timeframe=3M',
        headers=headers,
    )

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['provider'] == 'Bundled historical CSV'
    assert len(data['candles']) == 6
