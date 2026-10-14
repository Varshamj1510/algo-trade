import csv
import math
from datetime import date, datetime, timezone
from pathlib import Path


HISTORICAL_DATA_PATH = Path(__file__).resolve().parents[2] / 'symbols.csv' / 'adani.csv'
FAST_WINDOW = 20
SLOW_WINDOW = 50
STRATEGY_NAME = '20/50 SMA crossover'


def _read_history(path: Path | None = None) -> dict[str, list[tuple[date, float]]]:
    path = path or HISTORICAL_DATA_PATH
    with path.open('r', encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        required = {'timestamp', 'symbol', 'close'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('Historical CSV must contain timestamp, symbol, and close columns.')

        prices: dict[str, list[tuple[date, float]]] = {}
        for row in reader:
            try:
                symbol = row['symbol'].strip().upper()
                close = float(row['close'])
                timestamp = int(row['timestamp'])
            except (AttributeError, TypeError, ValueError) as error:
                raise ValueError('Historical CSV contains an invalid symbol, close, or timestamp.') from error
            if symbol.endswith('.NS'):
                symbol = symbol[:-3]
            elif symbol.endswith('.BO'):
                symbol = symbol[:-3]
            if not symbol or not math.isfinite(close) or close <= 0:
                raise ValueError('Historical CSV contains a missing symbol or non-positive close.')
            date = datetime.fromtimestamp(timestamp, timezone.utc).date()
            prices.setdefault(symbol, []).append((date, close))

    for values in prices.values():
        values.sort(key=lambda item: item[0])
    return prices


def get_historical_universe() -> list[dict[str, str | int]]:
    return [
        {
            'symbol': symbol,
            'observations': len(values),
            'start_date': values[0][0].isoformat(),
            'end_date': values[-1][0].isoformat(),
        }
        for symbol, values in sorted(_read_history().items())
    ]


def _read_demo_research_history() -> dict[str, list[dict[str, str | float | int]]]:
    candles_by_symbol: dict[str, list[dict[str, str | float | int]]] = {}
    with HISTORICAL_DATA_PATH.open('r', encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        required = {'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('Historical CSV must contain timestamp, symbol, OHLC, and volume columns.')
        for row in reader:
            try:
                raw_symbol = row['symbol'].strip().upper()
                if not raw_symbol.endswith('.NS'):
                    continue
                timestamp = int(row['timestamp'])
                candle = {
                    'time': datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(),
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row['volume']),
                }
            except (AttributeError, TypeError, ValueError, OverflowError) as error:
                raise ValueError('Historical CSV contains an invalid demo candle.') from error
            prices = [candle[key] for key in ('open', 'high', 'low', 'close', 'volume')]
            if (
                not all(math.isfinite(value) for value in prices)
                or min(prices[:4]) <= 0
                or candle['volume'] < 0
                or candle['high'] < max(candle['open'], candle['close'])
                or candle['low'] > min(candle['open'], candle['close'])
                or candle['high'] < candle['low']
            ):
                raise ValueError('Historical CSV contains an invalid demo candle.')
            symbol = raw_symbol[:-3]
            candles_by_symbol.setdefault(symbol, []).append(candle)
    for candles in candles_by_symbol.values():
        candles.sort(key=lambda candle: str(candle['time']))
    return candles_by_symbol


def get_demo_research_universe() -> list[dict[str, str | int]]:
    return [
        {'symbol': symbol, 'exchange': 'NSE', 'observations': len(candles)}
        for symbol, candles in sorted(_read_demo_research_history().items())
        if len(candles) >= 190
    ]


def get_demo_research_candles(symbol: str, exchange: str, timeframe: str) -> list[dict[str, str | float | int]]:
    normalized_symbol = symbol.strip().upper()
    normalized_exchange = exchange.strip().upper()
    if normalized_exchange != 'NSE':
        raise LookupError('Bundled demo history is available for NSE instruments only.')
    if timeframe not in {'1Y', '5Y'}:
        raise ValueError('Choose a supported historical period.')

    candles_by_symbol = _read_demo_research_history()
    available_candles = candles_by_symbol.get(normalized_symbol, [])
    if len(available_candles) < 190:
        raise LookupError(f'{normalized_symbol} is not available in the bundled demo history.')

    return available_candles[-(252 if timeframe == '1Y' else 1260):]


def get_csv_chart_candles(symbol: str, timeframe: str) -> list[dict[str, str | float | int]]:
    normalized_symbol = symbol.strip().upper()
    if timeframe not in {'3M', '6M', '1Y', '5Y'}:
        raise ValueError('Choose a supported chart period.')
    candles = _read_demo_research_history().get(normalized_symbol, [])
    if not candles:
        raise LookupError(f'{normalized_symbol} is not available in the bundled historical CSV.')
    windows = {'3M': 63, '6M': 126, '1Y': 252, '5Y': 1260}
    return candles[-windows[timeframe]:]


def detect_candlestick_patterns(candles: list[dict[str, str | float | int]]) -> list[dict[str, str | int]]:
    patterns = []
    for index, candle in enumerate(candles):
        open_price = float(candle['open'])
        high = float(candle['high'])
        low = float(candle['low'])
        close = float(candle['close'])
        candle_range = high - low
        if candle_range <= 0:
            continue
        body = abs(close - open_price)
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        previous = candles[index - 1] if index else None
        prior_trend = candles[max(0, index - 5):index]
        rising = len(prior_trend) >= 3 and float(prior_trend[-1]['close']) > float(prior_trend[0]['close'])
        falling = len(prior_trend) >= 3 and float(prior_trend[-1]['close']) < float(prior_trend[0]['close'])
        found = []

        if body <= candle_range * 0.1:
            found.append(('Doji', 'neutral'))
        elif (
            body <= candle_range * 0.3
            and upper_shadow > body
            and lower_shadow > body
        ):
            found.append(('Spinning top', 'neutral'))
        elif (
            body >= candle_range * 0.9
            and upper_shadow <= candle_range * 0.05
            and lower_shadow <= candle_range * 0.05
        ):
            found.append(('Marubozu', 'bullish' if close > open_price else 'bearish'))
        if (
            falling and lower_shadow >= max(body * 2, candle_range * 0.55)
            and upper_shadow <= candle_range * 0.15
            and close >= low + candle_range * 0.6
        ):
            found.append(('Hammer', 'bullish'))
        if (
            rising and upper_shadow >= max(body * 2, candle_range * 0.55)
            and lower_shadow <= candle_range * 0.15
            and close <= low + candle_range * 0.4
        ):
            found.append(('Shooting star', 'bearish'))

        if previous:
            previous_open = float(previous['open'])
            previous_close = float(previous['close'])
            previous_body_high = max(previous_open, previous_close)
            previous_body_low = min(previous_open, previous_close)
            current_body_high = max(open_price, close)
            current_body_low = min(open_price, close)
            if previous_close < previous_open and close > open_price and (
                open_price <= previous_close and close >= previous_open
            ):
                found.append(('Bullish engulfing', 'bullish'))
            elif previous_close > previous_open and close < open_price and (
                open_price >= previous_close and close <= previous_open
            ):
                found.append(('Bearish engulfing', 'bearish'))
            elif (
                previous_close < previous_open and close > open_price
                and current_body_low >= previous_body_low
                and current_body_high <= previous_body_high
            ):
                found.append(('Bullish harami', 'bullish'))
            elif (
                previous_close > previous_open and close < open_price
                and current_body_low >= previous_body_low
                and current_body_high <= previous_body_high
            ):
                found.append(('Bearish harami', 'bearish'))

        if index >= 2:
            first, middle = candles[index - 2:index]
            first_open, first_close = float(first['open']), float(first['close'])
            middle_open, middle_close = float(middle['open']), float(middle['close'])
            midpoint = (first_open + first_close) / 2
            middle_range = float(middle['high']) - float(middle['low'])
            if (
                first_close < first_open and middle_range > 0
                and abs(middle_close - middle_open) <= middle_range * 0.35
                and close > open_price and close > midpoint
            ):
                found.append(('Morning star', 'bullish'))
            elif (
                first_close > first_open and middle_range > 0
                and abs(middle_close - middle_open) <= middle_range * 0.35
                and close < open_price and close < midpoint
            ):
                found.append(('Evening star', 'bearish'))

        for name, direction in found:
            patterns.append({
                'index': index,
                'date': str(candle['time']),
                'name': name,
                'direction': direction,
            })
    return patterns


def run_historical_backtest(symbol: str, initial_capital: float) -> dict[str, str | int | float]:
    normalized_symbol = symbol.strip().upper()
    values: list[tuple[date, float]] | None = _read_history().get(normalized_symbol)
    if values is None:
        raise LookupError(f'{normalized_symbol} is not available in the historical CSV.')
    if len(values) <= SLOW_WINDOW:
        raise ValueError(f'{normalized_symbol} needs more than {SLOW_WINDOW} historical observations.')

    cash = initial_capital
    quantity = 0.0
    entry_equity = 0.0
    equity_curve = []
    closed_trade_returns = []
    gross_profit = 0.0
    gross_loss = 0.0

    closes = [close for _, close in values]
    for index, close in enumerate(closes):
        if index < SLOW_WINDOW - 1:
            continue

        fast_average = sum(closes[index - FAST_WINDOW + 1:index + 1]) / FAST_WINDOW
        slow_average = sum(closes[index - SLOW_WINDOW + 1:index + 1]) / SLOW_WINDOW
        bullish = fast_average > slow_average
        if bullish and quantity == 0:
            entry_equity = cash
            quantity = cash / close
        elif not bullish and quantity:
            cash = quantity * close
            trade_return = (cash / entry_equity - 1) * 100
            closed_trade_returns.append(trade_return)
            if trade_return > 0:
                gross_profit += cash - entry_equity
            else:
                gross_loss += entry_equity - cash
            quantity = 0.0

        equity_curve.append(quantity * close if quantity else cash)

    if quantity:
        cash = quantity * closes[-1]
        trade_return = (cash / entry_equity - 1) * 100
        closed_trade_returns.append(trade_return)
        if trade_return > 0:
            gross_profit += cash - entry_equity
        else:
            gross_loss += entry_equity - cash
        equity_curve[-1] = cash

    peak = initial_capital
    maximum_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak:
            maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak * 100)

    total_return = (cash / initial_capital - 1) * 100
    winning_trades = sum(trade_return > 0 for trade_return in closed_trade_returns)
    return {
        'strategy_name': STRATEGY_NAME,
        'symbol': normalized_symbol,
        'initial_capital': round(initial_capital, 2),
        'final_value': round(cash, 2),
        'total_return': round(total_return, 2),
        'win_rate': round(winning_trades / len(closed_trade_returns) * 100, 2) if closed_trade_returns else 0,
        'total_trades': len(closed_trade_returns),
        'max_drawdown': round(maximum_drawdown, 2),
        'profit_factor': round(gross_profit / gross_loss, 2) if gross_loss else 0,
        'start_date': values[0][0].isoformat(),
        'end_date': values[-1][0].isoformat(),
        'observations': len(values),
        'data_source': 'Historical CSV',
    }
