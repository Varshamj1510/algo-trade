from uuid import uuid4

from backend.app import app


def authenticated_client():
    client = app.test_client()
    email = f'paper-{uuid4().hex}@example.test'
    registration = client.post('/api/auth/register', json={
        'full_name': 'Paper Trader',
        'email': email,
        'username': f'paper-{uuid4().hex}',
        'password': 'paper-test-password',
    })
    assert registration.status_code == 201
    token = registration.get_json()['token']
    return client, {'Authorization': f'Bearer {token}'}


def test_new_paper_account_starts_with_virtual_cash_and_no_positions():
    client, headers = authenticated_client()

    response = client.get('/api/paper-trading/account', headers=headers)

    assert response.status_code == 200
    account = response.get_json()['data']
    assert account['starting_cash'] == 100000
    assert account['cash_balance'] == 100000
    assert account['total_equity'] == 100000
    assert account['holdings'] == []
    assert account['trades'] == []
    assert account['instruments']


def test_virtual_buy_sell_updates_cash_holdings_and_trade_history():
    client, headers = authenticated_client()
    account = client.get('/api/paper-trading/account', headers=headers).get_json()['data']
    instrument = account['instruments'][0]

    buy = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'],
        'exchange': instrument['exchange'],
        'side': 'BUY',
        'quantity': 2,
    })

    assert buy.status_code == 201
    buy_data = buy.get_json()
    expected_value = instrument['price'] * 2
    assert buy_data['account']['cash_balance'] == round(100000 - expected_value, 2)
    assert buy_data['account']['holdings'][0]['quantity'] == 2
    assert buy_data['account']['trades'][0]['side'] == 'BUY'

    sell = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'],
        'exchange': instrument['exchange'],
        'side': 'SELL',
        'quantity': 1,
    })

    assert sell.status_code == 201
    sell_data = sell.get_json()
    assert sell_data['account']['cash_balance'] == round(100000 - instrument['price'], 2)
    assert sell_data['account']['holdings'][0]['quantity'] == 1
    assert [trade['side'] for trade in sell_data['account']['trades'][:2]] == ['SELL', 'BUY']


def test_virtual_trading_rejects_overselling_and_insufficient_cash():
    client, headers = authenticated_client()
    instrument = client.get('/api/paper-trading/account', headers=headers).get_json()['data']['instruments'][0]

    oversell = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'], 'exchange': instrument['exchange'],
        'side': 'SELL', 'quantity': 1,
    })
    assert oversell.status_code == 400

    too_large = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'], 'exchange': instrument['exchange'],
        'side': 'BUY', 'quantity': 1000000000,
    })
    assert too_large.status_code == 400

    account = client.get('/api/paper-trading/account', headers=headers).get_json()['data']
    assert account['cash_balance'] == 100000
    assert account['trades'] == []


def test_virtual_trade_rejects_fractional_quantity():
    client, headers = authenticated_client()
    instrument = client.get('/api/paper-trading/account', headers=headers).get_json()['data']['instruments'][0]

    response = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'], 'exchange': instrument['exchange'],
        'side': 'BUY', 'quantity': 1.5,
    })

    assert response.status_code == 400
