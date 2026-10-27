from backend.algorithms.vwap import vwap
from backend.services.historical_backtest import get_csv_chart_candles
from backend.services.indicator_engine import calculate_indicators
from backend.services.instrument_catalog import find_paper_trading_instrument


BUILT_IN_STRATEGIES = [
    {
        'id': 'builtin:daily-change',
        'name': 'Daily Change',
        'description': 'Checks the configured daily percentage move against a 1% entry and exit threshold.',
        'buy_conditions': [{'left': 'daily_change_pct', 'operator': '>=', 'right': 1}],
        'sell_conditions': [{'left': 'daily_change_pct', 'operator': '<=', 'right': -1}],
    },
    {
        'id': 'builtin:ema',
        'name': 'Moving Average / EMA',
        'description': 'Compares the 12-period and 26-period exponential moving averages.',
        'buy_conditions': [{'left': 'ema_12', 'operator': '>', 'right': 'ema_26'}],
        'sell_conditions': [{'left': 'ema_12', 'operator': '<=', 'right': 'ema_26'}],
    },
    {
        'id': 'builtin:macd',
        'name': 'MACD',
        'description': 'Compares the MACD line with its signal line to assess momentum.',
        'buy_conditions': [{'left': 'macd', 'operator': '>', 'right': 'macd_signal'}],
        'sell_conditions': [{'left': 'macd', 'operator': '<=', 'right': 'macd_signal'}],
    },
    {
        'id': 'builtin:rsi',
        'name': 'RSI',
        'description': 'Checks for oversold entry and overbought exit conditions.',
        'buy_conditions': [{'left': 'rsi', 'operator': '<=', 'right': 30}],
        'sell_conditions': [{'left': 'rsi', 'operator': '>=', 'right': 70}],
    },
    {
        'id': 'builtin:vwap',
        'name': 'VWAP',
        'description': 'Compares the latest historical close with volume-weighted average price.',
        'buy_conditions': [{'left': 'price', 'operator': '>', 'right': 'vwap'}],
        'sell_conditions': [{'left': 'price', 'operator': '<=', 'right': 'vwap'}],
    },
    {
        'id': 'builtin:bollinger',
        'name': 'Bollinger Bands',
        'description': 'Checks whether price has reached the lower or upper volatility band.',
        'buy_conditions': [{'left': 'price', 'operator': '<=', 'right': 'bollinger_lower'}],
        'sell_conditions': [{'left': 'price', 'operator': '>=', 'right': 'bollinger_upper'}],
    },
]

_COMPARISONS = {
    '>': lambda left, right: left > right,
    '>=': lambda left, right: left >= right,
    '<': lambda left, right: left < right,
    '<=': lambda left, right: left <= right,
    '=': lambda left, right: left == right,
}


def _indicator_values(candles):
    indicators, _series = calculate_indicators(candles)
    closes = [float(candle['close']) for candle in candles]
    volumes = [float(candle['volume']) for candle in candles]
    indicators.update({
        'price': closes[-1],
        'rsi': indicators['rsi_14'],
        'ema': indicators['ema_20'],
        'sma': indicators['sma_50'],
        'moving_average': indicators['sma_20'],
        'atr': indicators['atr_14'],
        'vwap': vwap(closes, volumes),
    })
    return indicators


def _check_conditions(conditions, values):
    results = []
    for condition in conditions:
        left_name = condition['left']
        right_value = condition['right']
        left = values.get(left_name)
        right = values.get(right_value) if isinstance(right_value, str) else right_value
        if left is None or right is None:
            raise ValueError(f'{left_name} or {right_value} is unavailable for this instrument.')
        comparison = condition['operator']
        matched = _COMPARISONS[comparison](left, right)
        right_label = (
            right_value.replace('_', ' ').upper()
            if isinstance(right_value, str)
            else f'{right_value:g}'
        )
        label = f'{left_name.replace("_", " ").upper()} {comparison} {right_label}'
        results.append({
            'label': label,
            'actual': round(left, 4),
            'comparison_value': round(right, 4),
            'matched': matched,
        })
    return results


def review_strategy(symbol, strategy, is_builtin):
    if is_builtin and strategy['id'] == 'builtin:daily-change':
        instrument = find_paper_trading_instrument(symbol, 'NSE')
        if instrument is None:
            raise LookupError(f'No seeded virtual price is available for {symbol}.')
        values = {'daily_change_pct': float(instrument['change'])}
        return {
            'strategy_name': strategy['name'],
            'description': strategy['description'],
            'symbol': symbol,
            'history_through': 'app-provided market snapshot',
            'buy_logic': 'AND',
            'sell_logic': 'AND',
            'buy_conditions': _check_conditions(strategy['buy_conditions'], values),
            'sell_conditions': _check_conditions(strategy['sell_conditions'], values),
            'indicators': {
                'price': round(float(instrument['price']), 4),
                'daily_change_pct': round(values['daily_change_pct'], 4),
            },
        }

    candles = get_csv_chart_candles(symbol, '1Y')
    if not candles:
        raise LookupError(f'No historical candles are available for {symbol}.')
    values = _indicator_values(candles)
    if is_builtin:
        buy_results = _check_conditions(strategy['buy_conditions'], values)
        sell_results = _check_conditions(strategy['sell_conditions'], values)
        buy_logic = sell_logic = 'AND'
    else:
        from backend.services.condition_evaluator import evaluate_condition_group

        required_conditions = [strategy['buy_conditions'], strategy['sell_conditions']]
        required_values = {
            condition['indicator']
            for group in required_conditions
            for condition in group
        }
        available = {
            'price': values.get('price'),
            'rsi': values.get('rsi'),
            'macd': values.get('macd'),
            'ema': values.get('ema'),
            'sma': values.get('sma'),
            'bollinger_upper': values.get('bollinger_upper'),
            'bollinger_middle': values.get('bollinger_middle'),
            'bollinger_lower': values.get('bollinger_lower'),
            'moving_average': values.get('moving_average'),
            'vwap': values.get('vwap'),
            'atr': values.get('atr'),
            'obv': values.get('obv'),
            'volume': values.get('volume'),
        }
        missing = sorted(name for name in required_values if available.get(name) is None)
        if missing:
            raise ValueError(f"Required indicator data is unavailable: {', '.join(missing)}.")
        _buy_matches, buy_results = evaluate_condition_group(
            strategy['buy_conditions'], strategy['buy_logic'], available,
        )
        _sell_matches, sell_results = evaluate_condition_group(
            strategy['sell_conditions'], strategy['sell_logic'], available,
        )
        buy_logic = strategy['buy_logic']
        sell_logic = strategy['sell_logic']

    return {
        'strategy_name': strategy['name'],
        'description': strategy.get('description') or '',
        'symbol': symbol,
        'history_through': candles[-1]['time'],
        'buy_logic': buy_logic,
        'sell_logic': sell_logic,
        'buy_conditions': buy_results,
        'sell_conditions': sell_results,
        'indicators': {
            key: round(values[key], 4) if values.get(key) is not None else None
            for key in (
                'price', 'rsi', 'macd', 'macd_signal', 'ema_12', 'ema_26',
                'sma_20', 'sma_50', 'bollinger_upper', 'bollinger_lower',
                'vwap', 'atr', 'volume', 'obv',
            )
        },
    }
