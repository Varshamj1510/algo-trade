import os


class MarketDataUnavailableError(Exception):
    pass


def get_market_overview():
    provider = os.getenv('MARKET_DATA_PROVIDER', 'none').strip()
    if not provider or provider.casefold() == 'none':
        raise MarketDataUnavailableError(
            'Market data unavailable. Configure a non-live market-data source to populate this section.'
        )
    raise MarketDataUnavailableError(
        f'Market data unavailable. The configured provider "{provider}" has no non-live adapter.'
    )
