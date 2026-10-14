import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

import backend.app as app_module
import backend.services.kite_market as kite_market
import backend.services.kite_session as kite_session
from backend.app import app


def test_market_overview_uses_kite_quotes_and_aggregates(monkeypatch):
    monkeypatch.setattr(kite_market, '_auth', lambda: ('test-key', 'test-token'))
    monkeypatch.setattr(kite_market, '_load_instruments', lambda: {
        ('NSE', 'ALPHA'): {'instrument_token': '101'},
        ('NSE', 'NIFTY 50'): {'instrument_token': '201'},
        ('NSE', 'NIFTY BANK'): {'instrument_token': '202'},
        ('BSE', 'SENSEX'): {'instrument_token': '203'},
    })
    monkeypatch.setattr(kite_market, '_overview_cache', {})

    def fetch_quotes(keys):
        return {
            'NSE:NIFTY 50': {'last_price': 22000, 'ohlc': {'close': 21900}},
            'NSE:NIFTY BANK': {'last_price': 48000, 'ohlc': {'close': 48100}},
            'BSE:SENSEX': {'last_price': 72000, 'ohlc': {'close': 71800}},
            'NSE:ALPHA': {
                'last_price': 110, 'volume': 2500,
                'ohlc': {'open': 104, 'high': 112, 'low': 103, 'close': 100},
            },
        }

    monkeypatch.setattr(kite_market, '_fetch_quotes', fetch_quotes)
    monkeypatch.setattr(kite_market, '_fetch_candles', lambda token, timeframe: [
        {'time': '2026-10-07T09:15:00+05:30', 'open': 21900, 'high': 22000,
         'low': 21890, 'close': 22000, 'volume': 100},
    ])

    overview = kite_market.get_market_overview([{
        'symbol': 'ALPHA', 'name': 'Alpha Limited', 'exchange': 'NSE', 'sector': 'Technology',
    }])

    assert overview['provider'] == 'Kite Connect'
    assert overview['indices'][0]['price'] == 22000
    assert overview['indices'][0]['absolute_change'] == 100
    assert overview['indices'][0]['candles'][0]['close'] == 22000
    assert overview['gainers'][0]['symbol'] == 'ALPHA'
    assert overview['gainers'][0]['change'] == 10
    assert overview['most_active'][0]['volume'] == 2500
    assert overview['sectors'][0]['name'] == 'Technology'


def test_market_overview_requires_kite_auth(monkeypatch):
    def missing_auth():
        raise kite_market.KiteConfigurationError('missing Kite credentials')

    monkeypatch.setattr(kite_market, '_auth', missing_auth)
    with pytest.raises(kite_market.KiteConfigurationError, match='missing Kite credentials'):
        kite_market.get_market_overview([])


def test_auth_explains_missing_session_separately_from_missing_api_key(monkeypatch):
    monkeypatch.setenv('KITE_API_KEY', 'test-key')
    monkeypatch.delenv('KITE_ACCESS_TOKEN', raising=False)
    monkeypatch.setattr(kite_market, '_runtime_access_token', None)

    with pytest.raises(kite_market.KiteConfigurationError, match='no active session'):
        kite_market._auth()


def test_live_quotes_use_kite_and_cache_recent_results(monkeypatch):
    monkeypatch.setattr(kite_market, '_auth', lambda: ('test-key', 'test-token'))
    monkeypatch.setattr(kite_market, '_load_instruments', lambda: {
        ('NSE', 'ALPHA'): {'instrument_token': '101'},
    })
    monkeypatch.setattr(kite_market, '_quote_cache', {})
    requests = []

    def fetch_quotes(keys):
        requests.append(keys)
        return {'NSE:ALPHA': {
            'last_price': 110, 'volume': 2500,
            'ohlc': {'open': 104, 'high': 112, 'low': 103, 'close': 100},
        }}

    monkeypatch.setattr(kite_market, '_fetch_quotes', fetch_quotes)
    instrument = {'symbol': 'ALPHA', 'exchange': 'NSE'}

    first = kite_market.get_live_quotes([instrument])
    second = kite_market.get_live_quotes([instrument])

    assert first[('NSE', 'ALPHA')]['price'] == 110
    assert first[('NSE', 'ALPHA')]['change'] == 10
    assert second == first
    assert requests == [['NSE:ALPHA']]


def test_live_quote_requests_are_batched_at_two_hundred_instruments(monkeypatch):
    instruments = [{'symbol': f'STOCK{index}', 'exchange': 'NSE'} for index in range(201)]
    monkeypatch.setattr(kite_market, '_auth', lambda: ('test-key', 'test-token'))
    monkeypatch.setattr(kite_market, '_load_instruments', lambda: {
        ('NSE', instrument['symbol']): {'instrument_token': str(index)}
        for index, instrument in enumerate(instruments)
    })
    monkeypatch.setattr(kite_market, '_quote_cache', {})
    request_sizes = []

    def fetch_quotes(keys):
        request_sizes.append(len(keys))
        return {
            key: {'last_price': 100, 'ohlc': {'close': 99}}
            for key in keys
        }

    monkeypatch.setattr(kite_market, '_fetch_quotes', fetch_quotes)

    quotes = kite_market.get_live_quotes(instruments)

    assert request_sizes == [200, 1]
    assert len(quotes) == 201


def test_kite_instrument_master_includes_only_active_nifty_50_futures(monkeypatch):
    csv_data = (
        'instrument_token,exchange,tradingsymbol,name,expiry,lot_size,instrument_type,segment\n'
        '101,NFO,NIFTY26DECFUT,NIFTY 50,2099-12-31,65,FUT,NFO-FUT\n'
        '102,NFO,NIFTYBANK26DECFUT,NIFTY BANK,2099-12-31,30,FUT,NFO-FUT\n'
        '103,NFO,RELIANCE26DECFUT,RELIANCE,2099-12-31,250,FUT,NFO-FUT\n'
        '201,NSE,RELIANCE,RELIANCE INDUSTRIES,,1,EQ,NSE\n'
    ).encode()

    class InstrumentResponse:
        status_code = 200
        content = csv_data

        def raise_for_status(self):
            return None

    monkeypatch.setattr(kite_market, '_auth', lambda: ('test-key', 'test-token'))
    monkeypatch.setattr(kite_market, '_instrument_cache', None)
    monkeypatch.setattr(kite_market.requests, 'get', lambda *args, **kwargs: InstrumentResponse())

    instruments = kite_market._load_instruments()
    futures = kite_market.get_nifty_futures()

    assert ('NSE', 'RELIANCE') in instruments
    assert ('NFO', 'NIFTY26DECFUT') in instruments
    assert ('NFO', 'NIFTYBANK26DECFUT') not in instruments
    assert ('NFO', 'RELIANCE26DECFUT') not in instruments
    assert futures == [{
        'symbol': 'NIFTY26DECFUT',
        'exchange': 'NFO',
        'name': 'NIFTY 50',
        'expiry': '2099-12-31',
        'lot_size': 65,
    }]


def test_exchange_request_token_posts_kite_checksum(monkeypatch):
    monkeypatch.setenv('KITE_API_KEY', 'kite-key')
    monkeypatch.setenv('KITE_API_SECRET', 'kite-secret')
    monkeypatch.setenv('KITE_REDIRECT_URI', 'http://127.0.0.1:5000/kite/callback')
    monkeypatch.setattr(kite_session, 'save_access_token', lambda access_token: None)
    monkeypatch.setattr(kite_market, '_runtime_access_token', None)

    class TokenResponse:
        status_code = 200

        @staticmethod
        def json():
            return {'status': 'success', 'data': {'access_token': 'issued-token'}}

    def post(url, headers, data, timeout):
        assert url == f'{kite_market.API_BASE}/session/token'
        assert headers['X-Kite-Version'] == '3'
        assert data == {
            'api_key': 'kite-key',
            'request_token': 'single-use-token',
            'checksum': hashlib.sha256(b'kite-keysingle-use-tokenkite-secret').hexdigest(),
        }
        return TokenResponse()

    monkeypatch.setattr(kite_market.requests, 'post', post)
    assert kite_market.exchange_request_token('single-use-token') == 'issued-token'


def test_kite_connect_and_callback_validate_state(monkeypatch):
    monkeypatch.setenv('KITE_API_KEY', 'kite-key')
    monkeypatch.setenv('KITE_API_SECRET', 'kite-secret')
    monkeypatch.setenv('KITE_REDIRECT_URI', 'http://127.0.0.1:5000/kite/callback')
    monkeypatch.setattr(app_module, 'exchange_request_token', lambda request_token: 'issued-token')
    monkeypatch.setattr(app_module, 'set_access_token', lambda token: None)
    app_module.app.config['TESTING'] = True
    client = app.test_client()

    connect = client.get('/kite/connect')
    assert connect.status_code == 302
    authorization = urlparse(connect.location)
    assert authorization.hostname == 'kite.zerodha.com'
    assert parse_qs(authorization.query)['api_key'] == ['kite-key']
    state = parse_qs(parse_qs(authorization.query)['redirect_params'][0])['state'][0]

    invalid = client.get('/kite/callback?request_token=single-use-token&state=wrong-state')
    assert invalid.status_code == 400

    connect = client.get('/kite/connect')
    params = parse_qs(urlparse(connect.location).query)
    state = parse_qs(params['redirect_params'][0])['state'][0]
    denied = client.get(
        f'/kite/callback?status=error&error_type=InputException&message=The+user+is+not+enabled+for+the+app.&state={state}'
    )
    assert denied.status_code == 403
    assert b'Kite did not authorize this account' in denied.data
    assert b'AlgoTrade cannot grant this permission' in denied.data

    connect = client.get('/kite/connect')
    params = parse_qs(urlparse(connect.location).query)
    state = parse_qs(params['redirect_params'][0])['state'][0]
    callback = client.get(f'/kite/callback?request_token=single-use-token&state={state}')
    assert callback.status_code == 302
    assert callback.location.endswith('/market?kite=connected')


def test_stock_details_combines_quote_candles_indicators_and_news(monkeypatch):
    monkeypatch.setattr(kite_market, '_auth', lambda: ('kite-key', 'test-token'))
    monkeypatch.setattr(kite_market, '_load_instruments', lambda: {
        ('NSE', 'ALPHA'): {'instrument_token': '101'},
    })
    monkeypatch.setattr(kite_market, '_detail_cache', {})
    monkeypatch.setattr(kite_market, '_fetch_quotes', lambda keys: {
        'NSE:ALPHA': {'last_price': 125, 'volume': 5000, 'ohlc': {'close': 120}},
    })
    monkeypatch.setattr(kite_market, '_fetch_candles', lambda token, timeframe: [
        {'time': f'2026-10-{day:02d}T09:15:00+05:30', 'open': day, 'high': day + 2,
         'low': day - 1, 'close': float(day), 'volume': day * 100}
        for day in range(1, 51)
    ])
    monkeypatch.setattr(kite_market, '_fetch_stock_news', lambda instrument: [
        {'title': 'Alpha results', 'link': 'https://example.com/news', 'source': 'Example', 'published_at': None},
    ])

    detail = kite_market.get_stock_details({
        'symbol': 'ALPHA', 'name': 'Alpha Limited', 'exchange': 'NSE', 'sector': 'Technology',
    }, '1Y')

    assert detail['provider'] == 'Kite Connect'
    assert detail['timeframe'] == '1Y'
    assert detail['quote']['price'] == 125
    assert len(detail['candles']) == 50
    assert detail['indicators']['rsi_14'] is not None
    assert detail['indicators']['macd'] is not None
    assert detail['indicators']['sma_50'] == 25.5
    assert detail['indicators']['ema_20'] is not None
    assert detail['indicators']['bollinger_upper'] > detail['indicators']['bollinger_lower']
    assert detail['indicators']['atr_14'] is not None
    assert detail['indicators']['obv'] is not None
    assert len(detail['indicator_series']['close']) == len(detail['candles'])
    assert len(detail['indicator_series']['rsi_14']) == len(detail['candles'])
    assert detail['analysis']['symbol'] == 'ALPHA'
    assert detail['news'][0]['title'] == 'Alpha results'


def test_instrument_details_route_passes_selected_timeframe(monkeypatch):
    expected = {'timeframe': '1Y', 'candles': [], 'news': []}
    received = {}

    def fake_details(instrument, timeframe):
        received['instrument'] = instrument
        received['timeframe'] = timeframe
        return expected

    monkeypatch.setattr(app_module, 'get_stock_details', fake_details)
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com', 'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}
    response = client.get('/api/instruments/RELIANCE/details?exchange=NSE&timeframe=1Y', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['data'] == expected
    assert received['instrument']['symbol'] == 'RELIANCE'
    assert received['timeframe'] == '1Y'


def test_brokerage_estimate_uses_kite_virtual_contract_note(monkeypatch):
    monkeypatch.setattr(kite_market, '_auth', lambda: ('kite-key', 'test-token'))
    captured = {}

    def request(method, path, params=None, json_body=None, timeout=15):
        captured.update({'method': method, 'path': path, 'json_body': json_body})
        return [{'charges': {'total': 8.5}}]

    monkeypatch.setattr(kite_market, '_request', request)
    result = kite_market.get_brokerage_estimate(
        {'symbol': 'ALPHA', 'exchange': 'NSE'}, 10, 'CNC', 'BUY', 13.7,
    )

    assert result[0]['charges']['total'] == 8.5
    assert captured['method'] == 'POST'
    assert captured['path'] == '/charges/orders'
    assert captured['json_body'][0]['tradingsymbol'] == 'ALPHA'
    assert captured['json_body'][0]['product'] == 'CNC'
    assert captured['json_body'][0]['average_price'] == 13.7


def test_brokerage_route_rejects_invalid_order_inputs():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com', 'password': 'demo123',
    })
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}
    response = client.get(
        '/api/instruments/RELIANCE/brokerage?exchange=NSE&quantity=0&product=CNC&transaction_type=BUY&price=13.7',
        headers=headers,
    )
    assert response.status_code == 400
    assert 'greater than zero' in response.get_json()['message']