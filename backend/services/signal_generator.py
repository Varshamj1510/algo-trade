from backend.data.stock_data import get_sample_prices
from backend.algorithms.rsi import rsi
from backend.algorithms.macd import macd
from backend.algorithms.moving_average import moving_average


def generate_demo_trade_signals(instruments):
    signals = []
    for instrument in instruments:
        change = float(instrument.get('change') or 0)
        price = float(instrument.get('price') or 0)
        if change >= 1:
            signal = 'BUY'
            target_price = round(price * 1.02, 2)
            stop_loss = round(price * 0.98, 2)
        elif change <= -1:
            signal = 'SELL'
            target_price = round(price * 0.98, 2)
            stop_loss = round(price * 1.02, 2)
        else:
            signal = 'HOLD'
            target_price = None
            stop_loss = None

        signals.append({
            'symbol': instrument['symbol'],
            'signal': signal,
            'strategy': 'Demo daily-change rule',
            'current_price': round(price, 2),
            'target_price': target_price,
            'stop_loss': stop_loss,
            'confidence': min(95, 55 + int(abs(change) * 8)),
            'timestamp': 'Demo sample',
            'reason': f'Demo daily change: {change:+.2f}%.',
        })
    return signals


def generate_trade_decision(symbol, current_price, rsi_value, macd_value, support_level=0, resistance_level=0):
    symbol = (symbol or 'UNKNOWN').upper()
    price = float(current_price or 0)
    rsi_value = float(rsi_value or 50)
    macd_value = float(macd_value or 0)
    support = float(support_level or price)
    resistance = float(resistance_level or price)

    bullish = (rsi_value >= 55 and macd_value > 0) or (price >= resistance and rsi_value > 50)
    bearish = (rsi_value <= 45 and macd_value < 0) or (price <= support and rsi_value < 50)

    if bullish and not bearish:
        signal = 'BUY'
        reason = f'{symbol} shows bullish momentum with RSI {rsi_value:.1f}, positive MACD {macd_value:.2f}, and price holding above support {support:.2f}.'
    elif bearish and not bullish:
        signal = 'SELL'
        reason = f'{symbol} shows bearish pressure with RSI {rsi_value:.1f}, negative MACD {macd_value:.2f}, and price falling toward support {support:.2f}.'
    else:
        signal = 'HOLD'
        reason = f'{symbol} is range-bound; RSI {rsi_value:.1f} and MACD {macd_value:.2f} are mixed, so the system prefers caution until price breaks support or resistance.'

    confidence = 50
    if signal == 'BUY':
        confidence = min(99, max(60, int(55 + (rsi_value - 50) * 0.8 + (macd_value if macd_value > 0 else 0) * 0.3)))
    elif signal == 'SELL':
        confidence = min(99, max(60, int(55 + (50 - rsi_value) * 0.8 + (abs(macd_value) if macd_value < 0 else 0) * 0.3)))
    else:
        confidence = 55 if abs(rsi_value - 50) < 15 else 62

    return {
        'symbol': symbol,
        'signal': signal,
        'confidence': max(50, min(99, confidence)),
        'reason': reason,
        'price': round(price, 2),
    }


def generate_signal_summary():
    symbols = ['AAPL', 'MSFT', 'NVDA']
    results = []

    for symbol in symbols:
        values = get_sample_prices(symbol)
        latest = values[-1]
        rsi_value = rsi(values)
        macd_line, _, _ = macd(values)
        moving = moving_average(values, 5)[-1]

        if rsi_value > 70 and macd_line > 0 and latest > moving:
            signal = 'BUY'
        elif rsi_value < 30 and macd_line < 0 and latest < moving:
            signal = 'SELL'
        else:
            signal = 'HOLD'

        results.append({
            'symbol': symbol,
            'signal': signal,
            'confidence': max(50, min(95, int((rsi_value + 50) / 1.8))),
            'price': round(latest, 2),
        })

    return results
