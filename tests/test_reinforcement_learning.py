from datetime import date, timedelta

import backend.routes.reinforcement_learning_routes as routes
from backend.app import app
from backend.services.reinforcement_learning import run_q_learning_backtest


def make_candles(closes):
    start = date(2024, 1, 1)
    return [
        {'time': (start + timedelta(days=index)).isoformat(), 'close': close}
        for index, close in enumerate(closes)
    ]


def test_q_learning_backtest_splits_history_chronologically_and_is_reproducible():
    closes = [100 + index * 0.2 + (index % 7) for index in range(140)]
    candles = make_candles(closes)

    first = run_q_learning_backtest(candles, 'TEST')
    second = run_q_learning_backtest(candles, 'TEST')

    assert first == second
    assert first['method'] == 'Tabular Q-learning'
    assert first['training_period']['observations'] == 98
    assert first['test_period']['observations'] == 42
    assert first['training_period']['end_date'] < first['test_period']['start_date']
    assert first['episodes'] == 250
    assert len(first['equity_curve']) == first['test_period']['observations']
    assert all(action['action'] in {'buy', 'sell'} for action in first['actions'])
    assert first['transaction_cost_pct_per_side'] == 0.1


def test_q_learning_backtest_rejects_short_or_invalid_history():
    try:
        run_q_learning_backtest(make_candles([100] * 40), 'TEST')
    except ValueError as error:
        assert 'At least 80' in str(error)
    else:
        raise AssertionError('Short historical series must be rejected.')

    try:
        run_q_learning_backtest(make_candles([100] * 80), 'TEST', initial_capital=float('inf'))
    except ValueError as error:
        assert 'positive finite number' in str(error)
    else:
        raise AssertionError('Non-finite starting capital must be rejected.')


def test_reinforcement_learning_api_requires_authentication():
    response = app.test_client().get('/api/reinforcement-learning/instruments')

    assert response.status_code == 401


def test_reinforcement_learning_page_is_served():
    response = app.test_client().get('/reinforcement-learning')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Train &amp; evaluate' in page
    assert 'class="app-shell"' in page
    assert 'class="sidebar-nav"' in page

    navigation = app.test_client().get('/js/api.js')
    assert navigation.status_code == 200
    assert "['reinforcement-learning', 'fa-brain', 'Reinforcement Learning']" in (
        navigation.get_data(as_text=True)
    )


def test_reinforcement_learning_api_runs_authenticated_offline_backtest(monkeypatch):
    candles = make_candles([100 + index * 0.15 + (index % 5) for index in range(140)])
    monkeypatch.setattr(routes, 'get_demo_research_universe', lambda: [
        {'symbol': 'TEST', 'observations': len(candles)},
    ])
    monkeypatch.setattr(
        routes,
        'get_csv_chart_candles',
        lambda symbol, timeframe: candles if symbol == 'TEST' and timeframe == '5Y' else [],
    )
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

    instruments = client.get('/api/reinforcement-learning/instruments', headers=headers)
    response = client.post(
        '/api/reinforcement-learning/backtest',
        headers=headers,
        json={'symbol': 'TEST', 'initial_capital': 50_000},
    )

    assert instruments.status_code == 200
    assert instruments.get_json()['data'][0]['symbol'] == 'TEST'
    assert response.status_code == 200
    assert response.get_json()['data']['data_source'] == (
        'Bundled historical CSV; offline simulation'
    )
    assert response.get_json()['data']['initial_capital'] == 50_000


def test_reinforcement_learning_api_rejects_invalid_capital():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}

    response = client.post(
        '/api/reinforcement-learning/backtest',
        headers=headers,
        json={'symbol': 'TEST', 'initial_capital': 1},
    )

    assert response.status_code == 400
