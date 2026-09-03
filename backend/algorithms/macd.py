def macd(values, fast=12, slow=26, signal=9):
    if len(values) < slow:
        return 0.0, 0.0, 0.0

    ema_fast = sum(values[-fast:]) / fast
    ema_slow = sum(values[-slow:]) / slow
    macd_line = ema_fast - ema_slow
    signal_line = macd_line * 0.5
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
