from backend.services.indicator_engine import calculate_indicators


def candle(index, close, volume=10):
    return {
        'time': f'2026-01-{index + 1:02d}T09:15:00+05:30',
        'open': close, 'high': close + 2, 'low': close - 2,
        'close': close, 'volume': volume,
    }


def test_calculate_indicators_returns_values_and_aligned_chart_series():
    candles = [candle(index, 100 + index) for index in range(50)]

    indicators, series = calculate_indicators(candles)

    assert indicators['rsi_14'] == 100
    assert indicators['ema_20'] is not None
    assert indicators['sma_50'] == 124.5
    assert indicators['bollinger_upper'] > indicators['bollinger_middle']
    assert indicators['bollinger_lower'] < indicators['bollinger_middle']
    assert indicators['atr_14'] == 4
    assert indicators['obv'] == 490
    assert indicators['average_volume_20'] == 10
    assert all(len(values) == len(candles) for values in series.values())
    assert series['sma_20'][18] is None
    assert series['sma_20'][19] is not None


def test_calculate_indicators_marks_insufficient_history_unavailable():
    indicators, series = calculate_indicators([candle(index, 100 + index) for index in range(10)])

    assert indicators['ema_20'] is None
    assert indicators['bollinger_upper'] is None
    assert indicators['atr_14'] is None
    assert indicators['average_volume_20'] is None
    assert len(series['close']) == 10
    assert all(value is None for value in series['rsi_14'])


def test_calculate_indicators_handles_empty_candles():
    indicators, series = calculate_indicators([])

    assert indicators['rsi_14'] is None
    assert indicators['obv'] is None
    assert all(values == [] for values in series.values())
