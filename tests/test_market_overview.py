import backend.app as app_module
import backend.services.kite_market as kite_market
from backend.app import app


def authenticated_client():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com', 'password': 'demo123',
    })
    return client, {'Authorization': f"Bearer {login.get_json()['token']}"}


def test_market_overview_endpoint_uses_seeded_dashboard_demo_data(monkeypatch):
    instruments = [{'symbol': 'ALPHA', 'name': 'Alpha', 'exchange': 'NSE'}]
    expected = {
        'provider': 'Dashboard demo data · not live',
        'gainers': [],
        'coverage': {'available_stocks': 1},
    }
    monkeypatch.setattr(app_module, 'get_demo_instruments', lambda *args: instruments)
    monkeypatch.setattr(app_module, 'get_demo_market_overview', lambda listed: expected)
    monkeypatch.setattr(
        app_module,
        'get_market_overview',
        lambda _instruments: (_ for _ in ()).throw(AssertionError('Kite must not be requested')),
    )
    client, headers = authenticated_client()

    response = client.get('/api/market/overview', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data'] == expected


def test_market_overview_includes_demo_indices_and_chart_candles():
    client, headers = authenticated_client()

    response = client.get('/api/market/overview', headers=headers)
    payload = response.get_json()['data']

    assert response.status_code == 200
    assert payload['provider'] == 'Dashboard demo data · not live'
    assert [index['name'] for index in payload['indices']] == [
        'NIFTY 50', 'SENSEX', 'BANK NIFTY',
    ]
    assert all(index['price'] > 0 for index in payload['indices'])
    assert all(len(index['candles']) == 24 for index in payload['indices'])
    assert payload['indices'][0]['candles'][-1]['close'] == payload['indices'][0]['price']
    assert payload['updated_at']


def test_market_overview_section_uses_demo_data(monkeypatch):
    expected = {'sectors': [{'name': 'Technology', 'change': 1.2}]}
    monkeypatch.setattr(app_module, 'get_demo_instruments', lambda *args: [])
    monkeypatch.setattr(app_module, 'get_demo_market_overview', lambda listed: expected)
    client, headers = authenticated_client()

    response = client.get('/api/market/sectors', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data'] == expected['sectors']


def test_market_list_uses_seeded_dashboard_demo_data_without_kite(monkeypatch):
    catalog_item = {
        'symbol': 'ALPHA', 'name': 'Alpha', 'exchange': 'NSE',
        'price': 999, 'change': 99, 'volume': 999,
    }
    monkeypatch.setattr(app_module, 'get_demo_instruments', lambda *args: [catalog_item])
    monkeypatch.setattr(
        app_module,
        'get_live_quotes',
        lambda _instruments: (_ for _ in ()).throw(AssertionError('Kite must not be requested')),
    )
    client, headers = authenticated_client()

    response = client.get('/api/market', headers=headers)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['data'][0]['price'] == 999
    assert payload['data'][0]['change'] == 99
    assert payload['data'][0]['quote_source'] == 'Dashboard demo data (not live)'
    assert payload['coverage'] == {
        'demo_instruments': 1, 'listed_instruments': 1, 'available_instruments': 1,
    }


def test_trade_signals_use_seeded_dashboard_demo_data_without_kite(monkeypatch):
    monkeypatch.setattr(app_module, 'get_demo_instruments', lambda *args: [
        {'symbol': 'ALPHA', 'price': 100, 'change': 1.5},
        {'symbol': 'BETA', 'price': 200, 'change': -1.5},
    ])
    monkeypatch.setattr(
        app_module,
        'get_live_quotes',
        lambda _instruments: (_ for _ in ()).throw(AssertionError('Kite must not be requested')),
    )
    client, headers = authenticated_client()

    response = client.get('/api/signals', headers=headers)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['source'] == 'dashboard-demo'
    assert [signal['symbol'] for signal in payload['data']] == ['ALPHA', 'BETA']
    assert [signal['signal'] for signal in payload['data']] == ['BUY', 'SELL']


def test_portfolio_marks_holdings_using_seeded_demo_prices():
    client, headers = authenticated_client()

    response = client.get('/api/portfolio', headers=headers)
    payload = response.get_json()

    assert response.status_code == 200
    reliance = next(holding for holding in payload['holdings'] if holding['symbol'] == 'RELIANCE')
    assert reliance['current_price'] == 2856.40
    assert reliance['current_value'] == round(reliance['quantity'] * 2856.40, 2)
    assert payload['total_value'] == round(sum(holding['current_value'] for holding in payload['holdings']), 2)


def test_empty_portfolio_shows_seeded_demo_holdings():
    client = app.test_client()
    with app.app_context():
        token = app_module.create_access_token(identity='99999999')
    response = client.get('/api/portfolio', headers={'Authorization': f'Bearer {token}'})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['holdings_source'] == 'seeded-demo'
    assert [holding['symbol'] for holding in payload['holdings']] == [
        'RELIANCE', 'TCS', 'INFY', 'HDFCBANK',
    ]
    assert payload['total_value'] > 0


def test_reports_endpoint_includes_seeded_demo_report_examples():
    client, headers = authenticated_client()

    response = client.get('/api/reports', headers=headers)
    reports = response.get_json()['data']

    assert response.status_code == 200
    assert len(reports) >= 6
    assert any(report['name'] == 'Momentum Strategy Review' for report in reports)


def test_ai_signal_endpoint_uses_kite_analysis_not_manual_indicators(monkeypatch):
    expected = {
        'instrument': {'symbol': 'ALPHA', 'exchange': 'NSE'},
        'quote': {'price': 101},
        'analysis': {'signal': 'BUY', 'confidence': 70, 'reason': 'test'},
        'candles': [{'close': 101}],
        'timeframe': '1Y',
        'updated_at': '2026-10-07T12:00:00Z',
    }
    received = {}

    def get_details(instrument, timeframe):
        received['symbol'] = instrument['symbol']
        received['timeframe'] = timeframe
        return expected

    monkeypatch.setattr(app_module, 'find_instrument', lambda symbol, exchange: {
        'symbol': symbol, 'exchange': exchange,
    })
    monkeypatch.setattr(app_module, 'get_stock_details', get_details)
    client, headers = authenticated_client()

    response = client.post('/api/ai-signal', headers=headers, json={
        'symbol': 'ALPHA', 'exchange': 'NSE', 'timeframe': '1Y', 'price': 1, 'rsi': 1,
    })

    assert response.status_code == 200
    assert response.get_json()['data'] == expected
    assert received == {'symbol': 'ALPHA', 'timeframe': '1Y'}


def test_ai_signal_endpoint_reports_missing_kite_connection(monkeypatch):
    def unavailable(_instrument, _timeframe):
        raise kite_market.KiteConfigurationError('Kite Connect is not connected.')

    monkeypatch.setattr(app_module, 'get_stock_details', unavailable)
    client, headers = authenticated_client()

    response = client.post('/api/ai-signal', headers=headers, json={'symbol': 'RELIANCE'})

    assert response.status_code == 503
    assert 'Kite Connect is not connected' in response.get_json()['message']
