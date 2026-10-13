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
