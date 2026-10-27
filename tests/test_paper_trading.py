from uuid import uuid4

import pytest

from backend.app import app
from backend.routes import paper_trading_routes
from backend.services.instrument_catalog import find_demo_instrument, find_paper_trading_instrument


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


def test_adding_demo_money_only_increases_the_virtual_account_balance():
    client, headers = authenticated_client()

    response = client.post('/api/paper-trading/account/add-virtual-cash', headers=headers, json={
        'amount': 5000,
    })

    assert response.status_code == 200
    result = response.get_json()
    assert result['account']['cash_balance'] == 1505000
    assert result['account']['total_equity'] == 1505000
    assert result['account']['trades'] == []
    assert 'No payment was made' in result['message']


def test_demo_money_can_fund_a_confirmed_virtual_buy():
    client, headers = authenticated_client()
    instrument = client.get('/api/paper-trading/account', headers=headers).get_json()['data']['instruments'][0]
    top_up = client.post('/api/paper-trading/account/add-virtual-cash', headers=headers, json={
        'amount': 5000,
    })
    assert top_up.status_code == 200

    buy = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'],
        'exchange': instrument['exchange'],
        'side': 'BUY',
        'quantity': 1,
    })

    assert buy.status_code == 201
    result = buy.get_json()
    price = find_paper_trading_instrument(instrument['symbol'], instrument['exchange'])['price']
    assert result['account']['cash_balance'] == round(1505000 - price, 2)
    assert result['account']['holdings'][0]['symbol'] == instrument['symbol']
    assert result['account']['holdings'][0]['quantity'] == 1
    assert result['account']['trades'][0]['side'] == 'BUY'


@pytest.mark.parametrize('amount', [0, -1, 1.5, 1000001, True, 'invalid'])
def test_adding_demo_money_rejects_invalid_amounts(amount):
    client, headers = authenticated_client()

    response = client.post('/api/paper-trading/account/add-virtual-cash', headers=headers, json={
        'amount': amount,
    })

    assert response.status_code == 400
    account = client.get('/api/paper-trading/account', headers=headers).get_json()['data']
    assert account['cash_balance'] == 1500000


def test_virtual_stock_list_uses_configured_csv_prices():
    client, headers = authenticated_client()

    response = client.get('/api/paper-trading/account', headers=headers)

    assert response.status_code == 200
    instruments = response.get_json()['data']['instruments']
    assert len(instruments) == 10
    assert {instrument['symbol'] for instrument in instruments} == {
        'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
        'SBIN', 'ITC', 'LT', 'TATASTEEL', 'ADANIENT',
    }
    assert find_paper_trading_instrument('RELIANCE')['price'] == 2895.5


def test_market_top_gainer_can_be_opened_and_traded_in_the_demo_account():
    client, headers = authenticated_client()
    overview = client.get('/api/market/overview', headers=headers)
    assert overview.status_code == 200
    gainers = overview.get_json()['data']['gainers']
    assert gainers
    gainer = gainers[0]
    exchange = gainer.get('exchange', 'NSE')

    details = client.get(
        f"/api/instruments/{gainer['symbol']}?exchange={exchange}",
        headers=headers,
    )
    quote = client.get(
        f"/api/paper-trading/quote?symbol={gainer['symbol']}&exchange={exchange}",
        headers=headers,
    )
    assert details.status_code == 200
    assert quote.status_code == 200
    assert quote.get_json()['data']['price'] == details.get_json()['data']['price']

    buy = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': gainer['symbol'],
        'exchange': exchange,
        'side': 'BUY',
        'quantity': 1,
    })

    assert buy.status_code == 201
    account = buy.get_json()['account']
    assert account['holdings'][0]['symbol'] == gainer['symbol']
    assert account['holdings'][0]['quantity'] == 1
    assert account['trades'][0]['side'] == 'BUY'


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
    price = find_paper_trading_instrument(instrument['symbol'], instrument['exchange'])['price']
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


def test_virtual_trade_uses_seeded_price_not_external_quote(quote_prices):
    client, headers = authenticated_client()
    account = client.get('/api/paper-trading/account', headers=headers).get_json()['data']
    instrument = account['instruments'][0]
    seeded_price = find_paper_trading_instrument(instrument['symbol'], instrument['exchange'])['price']
    quote_prices[(instrument['exchange'], instrument['symbol'])] = seeded_price + 10

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
    assert quote.get_json()['data']['price'] == seeded_price
    assert trade.status_code == 201
    assert trade.get_json()['data']['price'] == seeded_price
    assert trade.get_json()['account']['cash_balance'] == round(1500000 - seeded_price, 2)


def test_virtual_equity_account_quote_and_trade_do_not_require_kite(monkeypatch):
    client, headers = authenticated_client()

    def no_kite_session(_instruments):
        raise paper_trading_routes.KiteConfigurationError('Kite Connect has no active session.')

    monkeypatch.setattr(paper_trading_routes, 'get_live_quotes', no_kite_session)
    account_response = client.get('/api/paper-trading/account', headers=headers)
    assert account_response.status_code == 200
    account = account_response.get_json()['data']
    instrument = account['instruments'][0]
    quote = client.get(
        f"/api/paper-trading/quote?symbol={instrument['symbol']}&exchange={instrument['exchange']}",
        headers=headers,
    )
    response = client.post('/api/paper-trading/trades', headers=headers, json={
        'symbol': instrument['symbol'],
        'exchange': instrument['exchange'],
        'side': 'BUY',
        'quantity': 1,
    })

    assert quote.status_code == 200
    assert response.status_code == 201
    assert response.get_json()['account']['trades']


def test_daily_change_strategy_review_explains_conditions_without_ordering():
    client, headers = authenticated_client()

    strategies = client.get('/api/paper-trading/strategies', headers=headers)
    assert strategies.status_code == 200
    assert any(item['id'] == 'builtin:daily-change' for item in strategies.get_json()['data'])

    response = client.post('/api/paper-trading/strategy-review', headers=headers, json={
        'strategy_id': 'builtin:daily-change',
        'symbol': 'RELIANCE',
    })

    assert response.status_code == 200
    review = response.get_json()['data']
    assert review['strategy_name'] == 'Daily Change'
    assert review['buy_conditions'][0]['actual'] == 1.84
    assert review['buy_conditions'][0]['matched'] is True
    assert review['sell_conditions'][0]['matched'] is False
    assert 'signal' not in review


def test_saved_strategy_review_uses_historical_indicators_and_user_scope():
    client, headers = authenticated_client()
    created = client.post('/api/strategies', headers=headers, json={
        'name': 'Virtual test rules',
        'description': 'A test strategy for virtual trading.',
        'buy_logic': 'AND',
        'buy_conditions': [
            {'indicator': 'price', 'operator': 'gt', 'value': 0},
            {'indicator': 'rsi', 'operator': 'lte', 'value': 100},
        ],
        'sell_logic': 'AND',
        'sell_conditions': [
            {'indicator': 'price', 'operator': 'lt', 'value': 100000},
        ],
    })
    assert created.status_code == 201
    strategy_id = f"saved:{created.get_json()['data']['id']}"

    response = client.post('/api/paper-trading/strategy-review', headers=headers, json={
        'strategy_id': strategy_id,
        'symbol': 'ADANIENT',
    })

    assert response.status_code == 200
    review = response.get_json()['data']
    assert review['buy_logic'] == 'AND'
    assert len(review['buy_conditions']) == 2
    assert review['buy_conditions'][0]['actual'] > 0
    assert review['sell_conditions'][0]['matched'] is True
    assert 'signal' not in review


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

    equity = find_paper_trading_instrument('RELIANCE', 'NSE')
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
