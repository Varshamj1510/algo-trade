def vwap(prices, volumes):
    if not prices or not volumes or len(prices) != len(volumes):
        return 0.0

    total_price_volume = sum(price * volume for price, volume in zip(prices, volumes))
    total_volume = sum(volumes)
    return round(total_price_volume / total_volume, 2) if total_volume else 0.0
