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
    assert detail.get_json()['data']['quote_source'] == 'Dashboard demo data (not live)'

    listed = client.get('/api/watchlist', headers=headers)
    assert listed.status_code == 200
    reliance = next(item for item in listed.get_json()['data'] if item['symbol'] == 'RELIANCE')
    assert reliance['price'] == 2856.40
    assert reliance['quote_source'] == 'Dashboard demo data (not live)'

    rejected = client.post('/api/watchlist', json={'symbol': 'QTEST', 'exchange': 'NSE'}, headers=headers)
    assert rejected.status_code == 404
