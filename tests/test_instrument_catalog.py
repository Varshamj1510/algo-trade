from urllib.parse import urlencode

import backend.app as app_module
from backend.app import app


def authenticated_client():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    return client, {'Authorization': f"Bearer {login.get_json()['token']}"}


def test_instrument_search_details_and_watchlist_use_demo_values(monkeypatch, tmp_path):
    csv_path = tmp_path / 'adani.csv'
    csv_path.write_text(
        'timestamp,symbol,company,open,high,low,close,volume\n'
        '2,QTEST.NS,Quant Test Holdings,40,45,39,42.50,100\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('INSTRUMENTS_CSV', str(csv_path))
    monkeypatch.setattr(
        app_module,
        'get_live_quotes',
        lambda _instruments: (_ for _ in ()).throw(AssertionError('Kite must not be requested')),
    )
    client, headers = authenticated_client()

    search = client.get(
        f"/api/instruments/search?{urlencode({'q': 'QTEST', 'exchange': 'NSE'})}",
        headers=headers,
    )
    assert search.status_code == 200
    assert search.get_json()['data'] == []

    missing_detail = client.get('/api/instruments/QTEST?exchange=NSE', headers=headers)
    assert missing_detail.status_code == 404

    detail = client.get('/api/instruments/RELIANCE?exchange=NSE', headers=headers)
    assert detail.status_code == 200
    assert detail.get_json()['data']['price'] == 2856.40
    assert detail.get_json()['data']['quote_source'] == 'Illustrative market data'

    listed = client.get('/api/watchlist', headers=headers)
    assert listed.status_code == 200
    reliance = next(item for item in listed.get_json()['data'] if item['symbol'] == 'RELIANCE')
    assert reliance['price'] == 2856.40
    assert reliance['quote_source'] == 'Illustrative market data'

    rejected = client.post('/api/watchlist', json={'symbol': 'QTEST', 'exchange': 'NSE'}, headers=headers)
    assert rejected.status_code == 404


def test_stock_directory_lists_instruments_by_initial_with_pagination(monkeypatch):
    instruments = [
        {'symbol': 'ALPHA', 'name': 'Alpha Holdings', 'exchange': 'NSE'},
        {'symbol': 'BETA', 'name': 'Beta Industries', 'exchange': 'NSE'},
        {'symbol': 'ATOM', 'name': 'Atom Systems', 'exchange': 'NSE'},
    ]
    monkeypatch.setattr(app_module, 'get_demo_instruments', lambda: instruments)
    client, headers = authenticated_client()

    first_page = client.get('/api/instruments/initial/a?page=1', headers=headers)
    assert first_page.status_code == 200
    result = first_page.get_json()['data']
    assert result['letter'] == 'A'
    assert result['total'] == 2
    assert [item['symbol'] for item in result['instruments']] == ['ALPHA', 'ATOM']

    invalid_initial = client.get('/api/instruments/initial/1', headers=headers)
    assert invalid_initial.status_code == 400
    invalid_page = client.get('/api/instruments/initial/A?page=0', headers=headers)
    assert invalid_page.status_code == 400


def test_stock_directory_page_is_available():
    response = app.test_client().get('/stocks?letter=A')
    assert response.status_code == 200
    assert b'Stocks starting with' in response.data
