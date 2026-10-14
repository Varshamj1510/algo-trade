from uuid import uuid4

import pytest

from backend.app import app
from backend.routes import paper_trading_routes
from backend.services.instrument_catalog import find_demo_instrument


def demo_instrument(symbol, exchange):
    with app.app_context():
        return find_demo_instrument(symbol, exchange)


@pytest.fixture
def quote_prices(monkeypatch):
    overrides = {}

    def mock_get_live_quotes(instruments):
        quotes = {}
        for instrument in instruments:
            identity = (instrument['exchange'], instrument['symbol'])
            stock = demo_instrument(*identity[::-1])
            if stock:
                quotes[identity] = {
                    'price': overrides.get(identity, stock['price']),
                }
        return quotes

    monkeypatch.setattr(paper_trading_routes, 'get_live_quotes', mock_get_live_quotes)
    return overrides


@pytest.fixture
def nifty_future(monkeypatch):
    contract = {
        'symbol': 'NIFTY26DEC25FUT',
        'exchange': 'NFO',
        'name': 'NIFTY 50',
        'expiry': '2999-12-31',
        'lot_size': 10,
    }
    monkeypatch.setattr(paper_trading_routes, 'get_nifty_futures', lambda: [contract])
    monkeypatch.setattr(
        paper_trading_routes,
        'get_live_quotes',
        lambda instruments: _future_test_quotes(instruments),
    )
    return contract


def _future_test_quotes(instruments):
    quotes = {}
    for instrument in instruments:
        identity = (instrument['exchange'], instrument['symbol'])
        stock = demo_instrument(instrument['symbol'], instrument['exchange'])
        quotes[identity] = {'price': 100 if identity[0] == 'NFO' else stock['price']}
    return quotes


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
    assert account['starting_cash'] == 1500000
    assert account['cash_balance'] == 1500000
    assert account['total_equity'] == 1500000
    assert account['holdings'] == []
    assert account['trades'] == []
    assert account['instruments']


def test_virtual_buy_sell_updates_cash_holdings_and_trade_history(quote_prices):
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
    price = demo_instrument(instrument['symbol'], instrument['exchange'])['price']
    expected_value = price * 2
    assert buy_data['account']['cash_balance'] == round(1500000 - expected_value, 2)
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
    assert sell_data['account']['cash_balance'] == round(1500000 - price, 2)
    assert sell_data['account']['holdings'][0]['quantity'] == 1
    assert [trade['side'] for trade in sell_data['account']['trades'][:2]] == ['SELL', 'BUY']


def test_virtual_trading_rejects_overselling_and_insufficient_cash(quote_prices):
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
    assert account['cash_balance'] == 1500000
    assert account['trades'] == []


def test_virtual_trade_rejects_fractional_quantity(quote_prices):
    client, headers = authenticated_client()
    instrument = client.get('/api/paper-trading/account', headers=headers).get_json()['data']['instruments'][0]

    response = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'], 'exchange': instrument['exchange'],
        'side': 'BUY', 'quantity': 1.5,
    })

    assert response.status_code == 400


def test_virtual_trade_uses_kite_quote_not_seeded_display_price(quote_prices):
    client, headers = authenticated_client()
    account = client.get('/api/paper-trading/account', headers=headers).get_json()['data']
    instrument = account['instruments'][0]
    quote_price = demo_instrument(instrument['symbol'], instrument['exchange'])['price'] + 10
    quote_prices[(instrument['exchange'], instrument['symbol'])] = quote_price

    quote = client.get(
        f"/api/paper-trading/quote?symbol={instrument['symbol']}&exchange={instrument['exchange']}",
        headers=headers,
    )
    trade = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'],
        'exchange': instrument['exchange'],
        'side': 'BUY',
        'quantity': 1,
    })

    assert quote.status_code == 200
    assert quote.get_json()['data']['price'] == quote_price
    assert trade.status_code == 201
    assert trade.get_json()['data']['price'] == quote_price
    assert trade.get_json()['account']['cash_balance'] == round(1500000 - quote_price, 2)


def test_virtual_trade_requires_kite_session_and_never_falls_back(monkeypatch):
    client, headers = authenticated_client()
    account = client.get('/api/paper-trading/account', headers=headers).get_json()['data']
    instrument = account['instruments'][0]

    def no_kite_session(_instruments):
        raise paper_trading_routes.KiteConfigurationError('Kite Connect has no active session.')

    monkeypatch.setattr(paper_trading_routes, 'get_live_quotes', no_kite_session)
    response = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'],
        'exchange': instrument['exchange'],
        'side': 'BUY',
        'quantity': 1,
    })

    assert response.status_code == 503
    assert 'no active session' in response.get_json()['message']
    account_after = client.get('/api/paper-trading/account', headers=headers)
    assert account_after.status_code == 200
    assert account_after.get_json()['data']['trades'] == []


def test_nifty_future_virtual_trade_uses_lot_size_full_notional_and_kite_quote(nifty_future):
    client, headers = authenticated_client()
    contracts = client.get('/api/paper-trading/futures', headers=headers)
    quote = client.get(
        f"/api/paper-trading/quote?symbol={nifty_future['symbol']}&exchange=NFO",
        headers=headers,
    )
    assert contracts.status_code == 200
    assert contracts.get_json()['data'] == [nifty_future]
    assert quote.status_code == 200
    assert quote.get_json()['data']['price'] == 100

    buy = client.post('/api/paper-trading/futures/trades', headers=headers, json={
        'symbol': nifty_future['symbol'], 'side': 'BUY', 'lots': 1,
    })
    assert buy.status_code == 201
    result = buy.get_json()
    assert result['data']['quantity'] == nifty_future['lot_size']
    assert result['data']['value'] == 1000
    assert result['account']['cash_balance'] == 1499000
    assert result['account']['holdings'][0]['instrument_type'] == 'FUT'
    assert result['account']['holdings'][0]['unrealized_pnl'] == 0

    equity = demo_instrument('RELIANCE', 'NSE')
    equity_buy = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': equity['symbol'], 'exchange': 'NSE', 'side': 'BUY', 'quantity': 1,
    })
    assert equity_buy.status_code == 201
    assert {holding['instrument_type'] for holding in equity_buy.get_json()['account']['holdings']} == {'EQUITY', 'FUT'}

    sell = client.post('/api/paper-trading/futures/trades', headers=headers, json={
        'symbol': nifty_future['symbol'], 'side': 'SELL', 'lots': 1,
    })
    assert sell.status_code == 201
    assert sell.get_json()['account']['cash_balance'] == round(1500000 - equity['price'], 2)
    assert [holding['instrument_type'] for holding in sell.get_json()['account']['holdings']] == ['EQUITY']


def test_nifty_future_virtual_trade_requires_full_notional_and_valid_contract(nifty_future, monkeypatch):
    client, headers = authenticated_client()

    too_expensive = client.post('/api/paper-trading/futures/trades', headers=headers, json={
        'symbol': nifty_future['symbol'], 'side': 'BUY', 'lots': 10001,
    })
    assert too_expensive.status_code == 400

    invalid_contract = client.post('/api/paper-trading/futures/trades', headers=headers, json={
        'symbol': 'NIFTYBANK26DECFUT', 'side': 'BUY', 'lots': 1,
    })
    assert invalid_contract.status_code == 404

    fractional_lots = client.post('/api/paper-trading/futures/trades', headers=headers, json={
        'symbol': nifty_future['symbol'], 'side': 'BUY', 'lots': 1.5,
    })
    assert fractional_lots.status_code == 400
    account = client.get('/api/paper-trading/account', headers=headers)
    assert account.status_code == 200
    assert account.get_json()['data']['cash_balance'] == 1500000
    assert account.get_json()['data']['trades'] == []


def test_existing_untouched_legacy_virtual_account_is_upgraded_once():
    client, headers = authenticated_client()
    user_id = int(client.get('/api/auth/me', headers=headers).get_json()['user']['id'])
    with app.app_context():
        account = paper_trading_routes.PaperAccount.query.filter_by(user_id=user_id).first()
        assert account is None
        account = paper_trading_routes.PaperAccount(user_id=user_id, cash_balance=100000)
        paper_trading_routes.db.session.add(account)
        paper_trading_routes.db.session.commit()

    first = client.get('/api/paper-trading/account', headers=headers)
    second = client.get('/api/paper-trading/account', headers=headers)

    assert first.status_code == 200
    assert first.get_json()['data']['cash_balance'] == 1500000
    assert second.get_json()['data']['cash_balance'] == 1500000
