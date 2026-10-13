import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.models import Stock


BASE_DIR = Path(__file__).resolve().parents[2]


def _number(value, default=0.0):
    try:
        return float(str(value).replace(',', '').replace('%', '').strip())
    except (TypeError, ValueError):
        return default


def _csv_files():
    configured = os.getenv('INSTRUMENTS_CSV')
    files = [Path(configured)] if configured else [BASE_DIR / 'backend' / 'data' / 'instruments.csv']
    directories = [BASE_DIR / 'backend' / 'data' / 'instruments', BASE_DIR / 'symbols.csv']
    for directory in directories:
        if directory.is_dir():
            files.extend(sorted(directory.glob('*.csv')))
    return [path for path in files if path.is_file()]


def _stock_instrument(stock):
    return {
        'symbol': stock.symbol,
        'name': stock.name,
        'exchange': 'NSE',
        'instrument_type': 'EQUITY',
        'sector': stock.sector or '',
        **stock.to_dict(),
    }


def _csv_instrument(row):
    values = {str(key or '').strip().lower(): str(value or '').strip() for key, value in row.items()}
    symbol = (values.get('symbol') or values.get('ticker') or '').upper()
    exchange = values.get('exchange', '').upper()
    if not exchange:
        if symbol.endswith('.NS'):
            exchange = 'NSE'
            symbol = symbol[:-3]
        elif symbol.endswith('.BO'):
            exchange = 'BSE'
            symbol = symbol[:-3]
        else:
            exchange = 'NSE'
    name = values.get('name') or values.get('company_name') or values.get('company') or symbol
    if not symbol:
        return None

    price = _number(values.get('price') or values.get('last_price') or values.get('close'))
    return {
        'symbol': symbol,
        'name': name,
        'exchange': exchange,
        'instrument_type': (values.get('instrument_type') or values.get('type') or 'EQUITY').upper(),
        'sector': values.get('sector', ''),
        'price': round(price, 2),
        'change': round(_number(values.get('change') or values.get('change_percent')), 2),
        'volume': int(_number(values.get('volume'), 0)),
        'high': round(_number(values.get('high')), 2),
        'low': round(_number(values.get('low')), 2),
        'open': round(_number(values.get('open') or values.get('open_price')), 2),
        'previous_close': round(_number(values.get('previous_close') or values.get('prev_close')), 2),
        '_timestamp': _number(values.get('timestamp'), 0),
    }


def get_instruments(query='', exchange=''):
    instruments = {
        f"{stock['exchange']}:{stock['symbol']}": stock
        for stock in (_stock_instrument(item) for item in Stock.query.order_by(Stock.symbol.asc()).all())
    }

    for csv_path in _csv_files():
        try:
            with csv_path.open('r', encoding='utf-8-sig', newline='') as source:
                csv_instruments = {}
                for row in csv.DictReader(source):
                    instrument = _csv_instrument(row)
                    if instrument:
                        key = f"{instrument['exchange']}:{instrument['symbol']}"
                        csv_instruments.setdefault(key, []).append(instrument)

                for key, records in csv_instruments.items():
                    records.sort(key=lambda record: record['_timestamp'], reverse=True)
                    instrument = records[0]
                    if instrument['previous_close'] == 0 and len(records) > 1:
                        instrument['previous_close'] = records[1]['price']
                        if instrument['previous_close']:
                            instrument['change'] = round(
                                (instrument['price'] - instrument['previous_close'])
                                / instrument['previous_close'] * 100,
                                2,
                            )
                    instrument.pop('_timestamp', None)
                    instruments[key] = {**instruments.get(key, {}), **instrument}
        except (OSError, csv.Error):
            continue

    search = query.strip().casefold()
    exchange_filter = exchange.strip().casefold()
    results = [instrument for instrument in instruments.values()
               if (not exchange_filter or instrument['exchange'].casefold() == exchange_filter)
               and (not search or any(search in str(instrument.get(field, '')).casefold()
                                      for field in ('symbol', 'name', 'exchange', 'sector', 'instrument_type')))]

    def rank(instrument):
        if not search:
            return (0, instrument['symbol'])
        symbol = instrument['symbol'].casefold()
        name = instrument['name'].casefold()
        return (0 if symbol.startswith(search) else 1 if name.startswith(search) else 2, symbol)

    return sorted(results, key=rank)


def get_demo_instruments(query='', exchange=''):
    instruments = [
        _stock_instrument(stock)
        for stock in Stock.query.order_by(Stock.symbol.asc()).all()
    ]
    search = query.strip().casefold()
    exchange_filter = exchange.strip().casefold()
    results = [
        instrument for instrument in instruments
        if (not exchange_filter or instrument['exchange'].casefold() == exchange_filter)
        and (not search or any(
            search in str(instrument.get(field, '')).casefold()
            for field in ('symbol', 'name', 'exchange', 'sector', 'instrument_type')
        ))
    ]

    def rank(instrument):
        if not search:
            return (0, instrument['symbol'])
        symbol = instrument['symbol'].casefold()
        name = instrument['name'].casefold()
        return (0 if symbol.startswith(search) else 1 if name.startswith(search) else 2, symbol)

    return sorted(results, key=rank)


def find_demo_instrument(symbol, exchange=''):
    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    return next((instrument for instrument in get_demo_instruments()
                 if instrument['symbol'].upper() == symbol
                 and (not exchange or instrument['exchange'].upper() == exchange)), None)


def get_demo_market_overview(instruments):
    stocks = []
    for instrument in instruments:
        previous_close = instrument.get('previous_close') or 0
        price = instrument.get('price') or 0
        absolute_change = round(price - previous_close, 2) if previous_close else None
        stocks.append({
            **instrument,
            'absolute_change': absolute_change,
            'trading_value': round(price * (instrument.get('volume') or 0), 2),
        })

    gainers = sorted(
        (stock for stock in stocks if stock.get('change', 0) > 0),
        key=lambda stock: stock['change'],
        reverse=True,
    )[:5]
    losers = sorted(
        (stock for stock in stocks if stock.get('change', 0) < 0),
        key=lambda stock: stock['change'],
    )[:5]
    most_active = sorted(stocks, key=lambda stock: stock.get('volume', 0), reverse=True)[:5]
    sector_groups = {}
    for stock in stocks:
        sector_groups.setdefault(stock.get('sector') or 'Other', []).append(stock)
    sectors = [{
        'name': name,
        'change': round(sum(stock.get('change', 0) for stock in members) / len(members), 2),
        'stocks': len(members),
        'gainers': sum(stock.get('change', 0) > 0 for stock in members),
        'losers': sum(stock.get('change', 0) < 0 for stock in members),
    } for name, members in sector_groups.items()]
    sectors.sort(key=lambda sector: sector['change'], reverse=True)

    now = datetime.now(timezone.utc)
    index_samples = (
        ('NIFTY 50', 24850.25, 0.64),
        ('SENSEX', 81235.40, 0.52),
        ('BANK NIFTY', 56214.70, -0.28),
    )
    indices = []
    for name, price, change in index_samples:
        previous_close = round(price / (1 + change / 100), 2)
        absolute_change = round(price - previous_close, 2)
        candles = []
        for step in range(24):
            progress = step / 23
            close = round(previous_close + absolute_change * progress, 2)
            candles.append({
                'time': (now - timedelta(minutes=(23 - step) * 30)).isoformat(),
                'open': close,
                'high': round(close * 1.001, 2),
                'low': round(close * 0.999, 2),
                'close': close,
                'volume': 100000 + step * 1250,
            })
        indices.append({
            'name': name,
            'price': price,
            'absolute_change': absolute_change,
            'change': change,
            'candles': candles,
        })

    return {
        'provider': 'Dashboard demo data · not live',
        'updated_at': now.isoformat(),
        'indices': indices,
        'gainers': gainers,
        'losers': losers,
        'most_active': most_active,
        'sectors': sectors,
        'summary': {
            'instruments': len(stocks),
            'advancers': sum(stock.get('change', 0) > 0 for stock in stocks),
            'decliners': sum(stock.get('change', 0) < 0 for stock in stocks),
        },
        'coverage': {
            'quoted_stocks': len(stocks),
            'sampled_stocks': len(stocks),
            'available_stocks': len(stocks),
        },
    }


def find_instrument(symbol, exchange=''):
    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    return next((instrument for instrument in get_instruments()
                 if instrument['symbol'].upper() == symbol
                 and (not exchange or instrument['exchange'].upper() == exchange)), None)