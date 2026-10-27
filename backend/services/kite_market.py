import csv
import gzip
import io
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests

try:
    from kiteconnect.exceptions import KiteException, TokenException
except ModuleNotFoundError:  # pragma: no cover - optional SDK in lightweight environments
    class KiteException(Exception):
        pass

    class TokenException(Exception):
        pass

from backend.algorithms.vwap import vwap
from backend.services.indicator_engine import calculate_indicators
from backend.services.kite_session import (
    KiteSessionError,
    clear_access_token,
    create_kite_client,
    create_login_url,
    exchange_request_token as sdk_exchange_request_token,
    load_access_token,
    save_access_token,
)
from backend.services.signal_generator import generate_trade_decision


API_BASE = 'https://api.kite.trade'
LOGIN_URL = 'https://kite.zerodha.com/connect/login'
INSTRUMENTS_URL = f'{API_BASE}/instruments'
INDEXES = {
    'NIFTY 50': ('NSE', 'NIFTY 50'),
    'BANK NIFTY': ('NSE', 'NIFTY BANK'),
    'SENSEX': ('BSE', 'SENSEX'),
}
CACHE_SECONDS = 30
HISTORY_CACHE_SECONDS = 300
INSTRUMENT_CACHE_SECONDS = 24 * 60 * 60

_cache_lock = threading.Lock()
_overview_cache = {}
_detail_cache = {}
_history_cache = {}
_quote_cache = {}
_instrument_cache = None
_instrument_cache_at = 0
_runtime_access_token = None


class KiteConfigurationError(Exception):
    pass


class KiteAPIError(Exception):
    pass


class KiteAuthenticationError(KiteAPIError):
    pass


class KiteEntitlementError(KiteAPIError):
    pass


def _credentials():
    api_key = os.getenv('KITE_API_KEY', '').strip()
    api_secret = os.getenv('KITE_API_SECRET', '').strip()
    redirect_uri = os.getenv('KITE_REDIRECT_URI', '').strip()
    if not api_key or not api_secret or not redirect_uri:
        raise KiteConfigurationError(
            'Set KITE_API_KEY, KITE_API_SECRET, and KITE_REDIRECT_URI in the project .env file.'
        )
    return api_key, api_secret, redirect_uri


def build_login_url(state):
    try:
        return create_login_url(state)
    except KiteSessionError as error:
        raise KiteConfigurationError(str(error)) from error


def exchange_request_token(request_token):
    global _runtime_access_token
    try:
        access_token = sdk_exchange_request_token(request_token)
    except KiteSessionError as error:
        if 'not configured' in str(error):
            raise KiteConfigurationError(str(error)) from error
        raise KiteAPIError(str(error)) from error
    _runtime_access_token = access_token
    return access_token


def set_access_token(access_token):
    global _runtime_access_token
    try:
        save_access_token(access_token)
    except KiteSessionError as error:
        raise KiteConfigurationError(str(error)) from error
    _runtime_access_token = access_token


def _auth():
    api_key = os.getenv('KITE_API_KEY', '').strip()
    if not api_key:
        raise KiteConfigurationError(
            'Kite Connect API key is missing. Set KITE_API_KEY in the project .env file.'
        )
    try:
        access_token = _runtime_access_token or load_access_token()
    except KiteSessionError as error:
        raise KiteConfigurationError(str(error)) from error
    if not access_token:
        raise KiteConfigurationError(
            'Kite Connect has no active session. Click Open Kite Connect login on the Market page '
            'and authorize the account; Kite access tokens expire and must be renewed. '
            'If Kite says the user is not enabled for the app, the app owner or Kite support must enable access.'
        )
    return api_key, access_token


def get_instrument_token(symbol, exchange='NSE'):
    identity = (exchange.strip().upper(), symbol.strip().upper())
    if identity[0] not in ('NSE', 'BSE') or not identity[1]:
        raise ValueError('Provide a valid NSE or BSE symbol.')
    instrument = _load_instruments().get(identity)
    if not instrument:
        raise KiteAPIError(f'No Kite instrument token found for {identity[0]}:{identity[1]}.')
    return instrument['instrument_token']


def get_market_quote(symbol='RELIANCE', exchange='NSE'):
    global _runtime_access_token
    identity = (exchange.strip().upper(), symbol.strip().upper())
    if identity[0] not in ('NSE', 'BSE') or not identity[1]:
        raise ValueError('Provide a valid NSE or BSE symbol.')
    quote_key = _quote_key(*identity)
    try:
        client = create_kite_client()
        quote = client.quote([quote_key]).get(quote_key)
    except KiteSessionError as error:
        raise KiteConfigurationError(str(error)) from error
    except TokenException as error:
        _runtime_access_token = None
        try:
            clear_access_token()
        except KiteSessionError as clear_error:
            raise KiteConfigurationError(
                'Kite session expired, but the saved session file could not be cleared.'
            ) from clear_error
        raise KiteAuthenticationError('Kite session expired. Reauthorize to continue.') from error
    except KiteException as error:
        message = str(error).lower()
        if 'permission' in message or 'entitlement' in message or 'access denied' in message:
            raise KiteEntitlementError(
                'Kite account is not entitled to this market-data request.'
            ) from error
        raise KiteAPIError('Kite quote request failed. Check Kite Connect availability and retry.') from error
    if not quote:
        return None

    metrics = _quote_metrics(quote)
    if not metrics or metrics['price'] <= 0:
        return None
    timestamp = quote.get('timestamp') or quote.get('last_trade_time')
    if hasattr(timestamp, 'isoformat'):
        timestamp = timestamp.isoformat()
    return {
        'symbol': identity[1],
        'exchange': identity[0],
        'last_traded_price': metrics['price'],
        'open': metrics['open'],
        'high': metrics['high'],
        'low': metrics['low'],
        'previous_close': metrics['previous_close'],
        'volume': metrics['volume'],
        'timestamp': timestamp,
    }


def _request(method, path, params=None, json_body=None, timeout=15):
    api_key, access_token = _auth()
    headers = {
        'X-Kite-Version': '3',
        'Authorization': f'token {api_key}:{access_token}',
        'Accept': 'application/json',
    }
    if json_body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        response = requests.request(
            method, f'{API_BASE}{path}', params=params, json=json_body,
            headers=headers, timeout=timeout,
        )
    except requests.RequestException as error:
        raise KiteAPIError('Could not reach Kite Connect. Check the server network and retry.') from error
    if response.status_code == 401:
        raise KiteAPIError('Kite session expired. Reauthorize to continue.')
    if response.status_code == 403:
        raise KiteAPIError('Kite account is not entitled to this market-data request.')
    if response.status_code >= 400:
        raise KiteAPIError(f'Kite Connect request failed ({response.status_code}).')
    try:
        payload = response.json()
    except ValueError as error:
        raise KiteAPIError('Kite returned an unreadable response.') from error
    if payload.get('status') != 'success':
        raise KiteAPIError(payload.get('message') or 'Kite Connect request failed.')
    return payload.get('data')


def _load_instruments():
    global _instrument_cache, _instrument_cache_at
    now = time.monotonic()
    with _cache_lock:
        if _instrument_cache is not None and now - _instrument_cache_at < INSTRUMENT_CACHE_SECONDS:
            return _instrument_cache
        try:
            api_key, access_token = _auth()
            response = requests.get(
                INSTRUMENTS_URL,
                headers={
                    'X-Kite-Version': '3',
                    'Authorization': f'token {api_key}:{access_token}',
                    'Accept': 'text/csv',
                },
                timeout=30,
            )
            if response.status_code == 401:
                raise KiteAPIError('Kite session expired. Reauthorize to continue.')
            if response.status_code == 403:
                raise KiteAPIError('Kite account is not entitled to download the instrument list.')
            response.raise_for_status()
            content = response.content
            if content.startswith(b'\x1f\x8b'):
                content = gzip.decompress(content)
            rows = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        except KiteAPIError:
            raise
        except (requests.RequestException, OSError, UnicodeDecodeError) as error:
            raise KiteAPIError('Could not load the Kite instrument list.') from error

        instruments = {}
        for row in rows:
            exchange = (row.get('exchange') or '').upper()
            symbol = (row.get('tradingsymbol') or '').upper()
            instrument_type = (row.get('instrument_type') or '').upper()
            segment = (row.get('segment') or '').upper()
            is_equity_or_index = exchange in ('NSE', 'BSE') and (
                instrument_type == 'EQ' or segment == 'INDICES'
            )
            is_nifty_future = (
                exchange == 'NFO'
                and segment == 'NFO-FUT'
                and instrument_type == 'FUT'
                and (row.get('name') or '').strip().upper() == 'NIFTY 50'
            )
            if not symbol or not row.get('instrument_token') or not (is_equity_or_index or is_nifty_future):
                continue
            instrument = {
                'instrument_token': str(row['instrument_token']),
                'name': row.get('name') or symbol,
                'instrument_type': instrument_type or 'INDEX',
                'exchange': exchange,
                'symbol': symbol,
            }
            if is_nifty_future:
                instrument['expiry'] = row.get('expiry')
                instrument['lot_size'] = int(row.get('lot_size') or 0)
            instruments[(exchange, symbol)] = instrument

        _instrument_cache = instruments
        _instrument_cache_at = now
        return instruments


def get_nifty_futures():
    today = datetime.now(ZoneInfo('Asia/Kolkata')).date()
    contracts = []
    for (exchange, symbol), instrument in _load_instruments().items():
        if exchange != 'NFO' or instrument['instrument_type'] != 'FUT':
            continue
        try:
            expiry = datetime.fromisoformat(instrument['expiry']).date()
            lot_size = int(instrument['lot_size'])
        except (TypeError, ValueError):
            continue
        if expiry < today or lot_size <= 0:
            continue
        contracts.append({
            'symbol': symbol,
            'exchange': exchange,
            'name': instrument['name'],
            'expiry': expiry.isoformat(),
            'lot_size': lot_size,
        })
    return sorted(contracts, key=lambda contract: (contract['expiry'], contract['symbol']))


def _instrument_lookup_key(instrument):
    return (instrument.get('exchange') or 'NSE').upper(), instrument['symbol'].upper()


def _quote_key(exchange, symbol):
    return f'{exchange}:{symbol}'


def _fetch_quotes(quote_keys):
    if not quote_keys:
        return {}
    params = [('i', key) for key in quote_keys]
    return _request('GET', '/quote', params=params)


def _quote_metrics(quote_data):
    if not quote_data:
        return None
    ohlc = quote_data.get('ohlc') or {}
    price = float(quote_data.get('last_price') or 0)
    previous_close = float(ohlc.get('close') or 0)
    change = ((price - previous_close) / previous_close * 100) if previous_close else 0
    return {
        'price': round(price, 2), 'previous_close': round(previous_close, 2),
        'change': round(change, 2), 'absolute_change': round(price - previous_close, 2),
        'volume': int(quote_data.get('volume') or 0),
        'open': round(float(ohlc.get('open') or 0), 2),
        'high': round(float(ohlc.get('high') or 0), 2),
        'low': round(float(ohlc.get('low') or 0), 2),
    }


def get_live_quotes(instruments):
    _auth()
    requested = list(instruments)
    identities = list(dict.fromkeys(_instrument_lookup_key(item) for item in requested))
    now = time.monotonic()
    with _cache_lock:
        cached = {
            identity: value[1]
            for identity in identities
            if (value := _quote_cache.get(identity)) and now - value[0] < CACHE_SECONDS
        }

    missing = [identity for identity in identities if identity not in cached]
    if missing:
        instrument_master = _load_instruments()
        quote_keys = [
            _quote_key(*identity) for identity in missing
            if identity in instrument_master
        ]
        quotes = {}
        for start in range(0, len(quote_keys), 200):
            quotes.update(_fetch_quotes(quote_keys[start:start + 200]))
        fetched_at = time.monotonic()
        with _cache_lock:
            for identity in missing:
                key = _quote_key(*identity)
                metrics = _quote_metrics(quotes.get(key))
                if metrics:
                    _quote_cache[identity] = (fetched_at, metrics)
                    cached[identity] = metrics

    return {
        identity: cached[identity]
        for identity in identities
        if identity in cached
    }


def _fetch_candles(instrument_token, timeframe):
    timezone_india = ZoneInfo('Asia/Kolkata')
    now = datetime.now(timezone_india)
    today = now.date()
    if timeframe == '1D':
        interval = '5minute'
        start = datetime.combine(today, datetime.min.time(), timezone_india).replace(hour=9, minute=15)
    else:
        days = {'1W': 7, '1M': 31, '3M': 93, '1Y': 366, '5Y': 1826}[timeframe]
        interval = '30minute' if timeframe == '1W' else 'day'
        start = datetime.combine(today - timedelta(days=days), datetime.min.time(), timezone_india)
    params = {
        'from': start.strftime('%Y-%m-%d %H:%M:%S'),
        'to': now.strftime('%Y-%m-%d %H:%M:%S'),
    }
    data = _request('GET', f'/instruments/historical/{instrument_token}/{interval}', params=params)
    candles = []
    for row in (data or {}).get('candles', []):
        if len(row) < 6 or any(value is None for value in row[1:6]):
            continue
        candles.append({
            'time': row[0], 'open': float(row[1]), 'high': float(row[2]),
            'low': float(row[3]), 'close': float(row[4]), 'volume': int(row[5]),
        })
    return candles


def _fetch_stock_news(instrument):
    query = f'"{instrument.get("name", instrument["symbol"])}" stock'
    try:
        response = requests.get(
            'https://news.google.com/rss/search',
            params={'q': query, 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'},
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=8,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except (requests.RequestException, ElementTree.ParseError, OSError):
        return []
    articles = []
    for item in root.findall('.//item')[:8]:
        title, link = item.findtext('title'), item.findtext('link')
        if not title or not link:
            continue
        published = item.findtext('pubDate')
        try:
            published_at = parsedate_to_datetime(published).isoformat() if published else None
        except (TypeError, ValueError, OverflowError):
            published_at = None
        articles.append({
            'title': unescape(title), 'link': link,
            'source': item.findtext('source') or 'Google News', 'published_at': published_at,
        })
    return articles


def _detail_indicators(candles):
    indicators, _ = calculate_indicators(candles)
    closes = [candle['close'] for candle in candles]
    volumes = [candle['volume'] for candle in candles]
    indicators['vwap'] = vwap(closes, volumes) if volumes else None
    return indicators


def get_market_overview(instruments):
    _auth()
    instruments = list(instruments)
    available_instruments = len(instruments)
    instruments = instruments[:200]
    cache_key = (
        available_instruments,
        tuple(sorted((item.get('exchange', 'NSE'), item['symbol']) for item in instruments)),
    )
    now = time.monotonic()
    with _cache_lock:
        cached = _overview_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]

    instrument_master = _load_instruments()
    stock_keys = []
    for item in instruments:
        identity = _instrument_lookup_key(item)
        if identity in instrument_master:
            stock_keys.append(_quote_key(*identity))
    index_keys = [_quote_key(*identity) for identity in INDEXES.values()]
    quotes = _fetch_quotes(list(dict.fromkeys(index_keys + stock_keys)))

    with ThreadPoolExecutor(max_workers=3) as executor:
        candle_tasks = {
            name: executor.submit(_fetch_candles, instrument_master[identity]['instrument_token'], '1D')
            if identity in instrument_master else None
            for name, identity in INDEXES.items()
        }
        indices = []
        for name, identity in INDEXES.items():
            metrics = _quote_metrics(quotes.get(_quote_key(*identity)))
            task = candle_tasks[name]
            candles = task.result() if task else []
            indices.append({
                'name': name, 'instrument_key': _quote_key(*identity), **(metrics or {}),
                'candles': [{'time': candle['time'], 'close': candle['close']} for candle in candles],
            })

    stocks = []
    for item in instruments:
        identity = _instrument_lookup_key(item)
        metrics = _quote_metrics(quotes.get(_quote_key(*identity)))
        if metrics:
            stocks.append({
                'symbol': item['symbol'], 'name': item.get('name') or item['symbol'],
                'exchange': identity[0], 'sector': item.get('sector') or 'Other', **metrics,
            })
    gainers = sorted((stock for stock in stocks if stock['change'] > 0), key=lambda stock: stock['change'], reverse=True)[:5]
    losers = sorted((stock for stock in stocks if stock['change'] < 0), key=lambda stock: stock['change'])[:5]
    most_active = sorted(stocks, key=lambda stock: stock['volume'], reverse=True)[:5]
    sector_groups = {}
    for stock in stocks:
        sector_groups.setdefault(stock['sector'], []).append(stock)
    sectors = [{
        'name': name,
        'change': round(sum(stock['change'] for stock in members) / len(members), 2),
        'stocks': len(members),
        'gainers': sum(stock['change'] > 0 for stock in members),
        'losers': sum(stock['change'] < 0 for stock in members),
    } for name, members in sector_groups.items()]
    sectors.sort(key=lambda sector: sector['change'], reverse=True)
    result = {
        'provider': 'Kite Connect', 'updated_at': datetime.now(timezone.utc).isoformat(),
        'indices': indices, 'gainers': gainers, 'losers': losers,
        'most_active': most_active, 'sectors': sectors,
        'coverage': {
            'quoted_stocks': len(stocks),
            'sampled_stocks': len(instruments),
            'available_stocks': available_instruments,
        },
    }
    with _cache_lock:
        _overview_cache[cache_key] = (time.monotonic(), result)
    return result


def get_stock_details(instrument, timeframe='1D'):
    timeframe = timeframe.upper()
    if timeframe not in ('1D', '1W', '1M', '3M', '1Y', '5Y'):
        raise ValueError('Unsupported timeframe')
    _auth()
    identity = _instrument_lookup_key(instrument)
    cache_key = (*identity, timeframe)
    now = time.monotonic()
    with _cache_lock:
        cached = _detail_cache.get(cache_key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
    master_item = _load_instruments().get(identity)
    if not master_item:
        raise KiteAPIError(f'No Kite instrument token found for {identity[0]}:{identity[1]}.')
    quote_key = _quote_key(*identity)
    metrics = _quote_metrics(_fetch_quotes([quote_key]).get(quote_key))
    if not metrics:
        raise KiteAPIError(f'Kite returned no current quote for {identity[1]}.')
    candles = _fetch_candles(master_item['instrument_token'], timeframe)
    indicators, indicator_series = calculate_indicators(candles)
    closes = [candle['close'] for candle in candles]
    volumes = [candle['volume'] for candle in candles]
    indicators['vwap'] = vwap(closes, volumes) if volumes else None
    if len(candles) >= 26:
        support = min(candle['low'] for candle in candles[-20:])
        resistance = max(candle['high'] for candle in candles[-20:])
        analysis = generate_trade_decision(
            identity[1], metrics['price'], indicators['rsi_14'], indicators['macd'], support, resistance,
        )
    else:
        analysis = {
            'symbol': identity[1], 'signal': 'N/A', 'confidence': None,
            'reason': 'Not enough candle history to produce a reliable technical analysis.',
            'price': metrics['price'],
        }
    result = {
        'provider': 'Kite Connect', 'timeframe': timeframe,
        'updated_at': datetime.now(timezone.utc).isoformat(), 'instrument': instrument,
        'quote': metrics, 'candles': candles, 'indicators': indicators,
        'indicator_series': indicator_series,
        'analysis': analysis, 'news': _fetch_stock_news(instrument),
    }
    with _cache_lock:
        _detail_cache[cache_key] = (time.monotonic(), result)
    return result


def get_historical_candles(instrument, timeframe='1Y'):
    timeframe = timeframe.upper()
    if timeframe not in ('1D', '1W', '1M', '3M', '1Y', '5Y'):
        raise ValueError('Unsupported timeframe')
    _auth()
    identity = _instrument_lookup_key(instrument)
    cache_key = (*identity, timeframe)
    now = time.monotonic()
    with _cache_lock:
        cached = _history_cache.get(cache_key)
        if cached and now - cached[0] < HISTORY_CACHE_SECONDS:
            return cached[1]
    master_item = _load_instruments().get(identity)
    if not master_item:
        raise KiteAPIError(f'No Kite instrument token found for {identity[0]}:{identity[1]}.')
    candles = _fetch_candles(master_item['instrument_token'], timeframe)
    with _cache_lock:
        _history_cache[cache_key] = (time.monotonic(), candles)
    return candles


def get_brokerage_estimate(instrument, quantity, product, transaction_type, price):
    identity = _instrument_lookup_key(instrument)
    order = {
        'order_id': f'market-estimate-{secrets.token_hex(8)}',
        'exchange': identity[0], 'tradingsymbol': identity[1],
        'transaction_type': transaction_type, 'variety': 'regular',
        'product': product, 'order_type': 'MARKET', 'quantity': quantity,
        'average_price': price,
    }
    return _request('POST', '/charges/orders', json_body=[order])