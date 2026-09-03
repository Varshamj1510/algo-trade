import random


def get_sample_prices(symbol):
    base = {
        'AAPL': 214.60,
        'MSFT': 432.10,
        'NVDA': 128.90,
        'AMZN': 189.20,
        'GOOGL': 178.55,
    }

    base_value = base.get(symbol, 100.0)
    values = []
    current = base_value

    for _ in range(20):
        move = random.uniform(-3.5, 3.5)
        current = max(current + move, 10.0)
        values.append(round(current, 2))

    return values
