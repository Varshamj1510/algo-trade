import math


def _ema(values, period):
    result = [None] * len(values)
    if len(values) < period:
        return result
    current = sum(values[:period]) / period
    result[period - 1] = current
    smoothing = 2 / (period + 1)
    for index in range(period, len(values)):
        current = values[index] * smoothing + current * (1 - smoothing)
        result[index] = current
    return result


def _sma(values, period):
    result = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        result[index] = sum(window) / period
    return result


def _rsi(values, period=14):
    result = [None] * len(values)
    if len(values) <= period:
        return result
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    average_gain = sum(max(change, 0) for change in changes[:period]) / period
    average_loss = sum(max(-change, 0) for change in changes[:period]) / period

    def value(gain, loss):
        if loss == 0:
            return 100.0 if gain else 50.0
        relative_strength = gain / loss
        return 100 - 100 / (1 + relative_strength)

    result[period] = value(average_gain, average_loss)
    for index in range(period + 1, len(values)):
        change = changes[index - 1]
        average_gain = (average_gain * (period - 1) + max(change, 0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0)) / period
        result[index] = value(average_gain, average_loss)
    return result


def _bollinger(values, period=20):
    middle = _sma(values, period)
    upper = [None] * len(values)
    lower = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        mean = middle[index]
        deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
        upper[index] = mean + 2 * deviation
        lower[index] = mean - 2 * deviation
    return upper, middle, lower


def _atr(candles, period=14):
    true_ranges = []
    for index, candle in enumerate(candles):
        previous_close = candles[index - 1]['close'] if index else candle['close']
        true_ranges.append(max(
            candle['high'] - candle['low'],
            abs(candle['high'] - previous_close),
            abs(candle['low'] - previous_close),
        ))
    return _sma(true_ranges, period)


def _obv(candles):
    values = [0.0] if candles else []
    for index in range(1, len(candles)):
        previous = candles[index - 1]['close']
        current = candles[index]['close']
        direction = 1 if current > previous else -1 if current < previous else 0
        values.append(values[-1] + direction * candles[index]['volume'])
    return values


def _macd(values):
    fast = _ema(values, 12)
    slow = _ema(values, 26)
    line = [
        fast_value - slow_value if fast_value is not None and slow_value is not None else None
        for fast_value, slow_value in zip(fast, slow)
    ]
    first_valid = next((index for index, value in enumerate(line) if value is not None), None)
    signal = [None] * len(values)
    histogram = [None] * len(values)
    if first_valid is None:
        return line, signal, histogram
    valid_line = [value for value in line[first_valid:] if value is not None]
    valid_signal = _ema(valid_line, 9)
    for offset, value in enumerate(valid_signal):
        index = first_valid + offset
        if value is not None:
            signal[index] = value
            histogram[index] = line[index] - value
    return line, signal, histogram


def _latest(values):
    return values[-1] if values else None


def _rounded(values, digits=4):
    return [round(value, digits) if value is not None else None for value in values]


def calculate_indicators(candles):
    closes = [float(candle['close']) for candle in candles]
    volumes = [float(candle['volume']) for candle in candles]
    ema_12 = _ema(closes, 12)
    ema_20 = _ema(closes, 20)
    ema_26 = _ema(closes, 26)
    sma_20 = _sma(closes, 20)
    sma_50 = _sma(closes, 50)
    upper, middle, lower = _bollinger(closes)
    macd_line, macd_signal, macd_histogram = _macd(closes)
    atr_14 = _atr(candles)
    obv = _obv(candles)
    indicators = {
        'rsi_14': _latest(_rsi(closes)),
        'macd': _latest(macd_line),
        'macd_signal': _latest(macd_signal),
        'macd_histogram': _latest(macd_histogram),
        'ema_12': _latest(ema_12),
        'ema_20': _latest(ema_20),
        'ema_26': _latest(ema_26),
        'sma_20': _latest(sma_20),
        'sma_50': _latest(sma_50),
        'bollinger_upper': _latest(upper),
        'bollinger_middle': _latest(middle),
        'bollinger_lower': _latest(lower),
        'atr_14': _latest(atr_14),
        'obv': _latest(obv),
        'vwap': None,
        'volume': _latest(volumes),
        'average_volume_20': (
            sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None
        ),
    }
    for name, value in indicators.items():
        if name != 'vwap' and value is not None:
            indicators[name] = round(value, 4)
    series = {
        'times': [candle['time'] for candle in candles],
        'close': _rounded(closes, 2),
        'ema_20': _rounded(ema_20, 2),
        'sma_20': _rounded(sma_20, 2),
        'bollinger_upper': _rounded(upper, 2),
        'bollinger_middle': _rounded(middle, 2),
        'bollinger_lower': _rounded(lower, 2),
        'volume': _rounded(volumes, 2),
        'rsi_14': _rounded(_rsi(closes), 2),
        'macd': _rounded(macd_line),
        'macd_signal': _rounded(macd_signal),
        'macd_histogram': _rounded(macd_histogram),
        'atr_14': _rounded(atr_14, 2),
        'obv': _rounded(obv, 2),
    }
    return indicators, series
