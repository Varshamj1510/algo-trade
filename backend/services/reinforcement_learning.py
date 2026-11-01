import math
import random
from collections import defaultdict


MIN_CANDLES = 80
TRAIN_RATIO = 0.7
DEFAULT_EPISODES = 250
TRANSACTION_COST_RATE = 0.001
LOOKBACK = 5
ACTIONS = ('hold', 'buy', 'sell')


def _market_state(closes, index, position):
    if index < LOOKBACK:
        trend = 0
    else:
        change = closes[index] / closes[index - LOOKBACK] - 1
        trend = 1 if change >= 0.01 else -1 if change <= -0.01 else 0
    return trend, position


def _target_position(action, position):
    if action == 1:
        return 1
    if action == 2:
        return 0
    return position


def _best_action(q_values):
    return max(range(len(ACTIONS)), key=lambda action: q_values[action])


def _train_q_table(closes, episodes):
    q_table = defaultdict(lambda: [0.0] * len(ACTIONS))
    rng = random.Random(42)
    learning_rate = 0.15
    discount_factor = 0.95

    for episode in range(episodes):
        epsilon = max(0.02, 0.2 * (0.985 ** episode))
        position = 0
        for index in range(LOOKBACK, len(closes) - 1):
            state = _market_state(closes, index, position)
            action = (
                rng.randrange(len(ACTIONS))
                if rng.random() < epsilon
                else _best_action(q_table[state])
            )
            next_position = _target_position(action, position)
            price_return = closes[index + 1] / closes[index] - 1
            reward = price_return * next_position
            if next_position != position:
                reward -= TRANSACTION_COST_RATE
            terminal = index == len(closes) - 2
            if terminal and next_position:
                reward -= TRANSACTION_COST_RATE

            next_state = _market_state(closes, index + 1, next_position)
            future_value = 0 if terminal else max(q_table[next_state])
            old_value = q_table[state][action]
            q_table[state][action] = old_value + learning_rate * (
                reward + discount_factor * future_value - old_value
            )
            position = next_position

    return q_table


def _evaluate(q_table, candles, closes, initial_capital, previous_closes):
    equity = initial_capital
    position = 0
    entry_equity = None
    entry_date = None
    state_closes = previous_closes[-LOOKBACK:] + closes
    curve = [{'date': str(candles[0]['time']), 'equity': round(equity, 2)}]
    actions = []
    closed_trades = []

    for index in range(len(closes) - 1):
        history_index = index + LOOKBACK
        state = _market_state(state_closes, history_index, position)
        action = _best_action(q_table[state])
        next_position = _target_position(action, position)

        if next_position != position:
            previous_equity = equity
            equity *= 1 - TRANSACTION_COST_RATE
            actions.append({
                'date': str(candles[index]['time']),
                'action': ACTIONS[action],
                'price': round(closes[index], 2),
            })
            if next_position:
                entry_equity = previous_equity
                entry_date = str(candles[index]['time'])
            else:
                closed_trades.append({
                    'entry_date': entry_date,
                    'exit_date': str(candles[index]['time']),
                    'return_pct': round((equity / entry_equity - 1) * 100, 2),
                })
                entry_equity = None
                entry_date = None
            position = next_position

        equity *= 1 + (closes[index + 1] / closes[index] - 1) * position
        curve.append({
            'date': str(candles[index + 1]['time']),
            'equity': round(equity, 2),
        })

    if position:
        equity *= 1 - TRANSACTION_COST_RATE
        actions.append({
            'date': str(candles[-1]['time']),
            'action': 'sell',
            'price': round(closes[-1], 2),
        })
        closed_trades.append({
            'entry_date': entry_date,
            'exit_date': str(candles[-1]['time']),
            'return_pct': round((equity / entry_equity - 1) * 100, 2),
        })
        curve[-1]['equity'] = round(equity, 2)

    buy_and_hold_value = (
        initial_capital
        * (1 - TRANSACTION_COST_RATE)
        * (closes[-1] / closes[0])
        * (1 - TRANSACTION_COST_RATE)
    )
    peak = initial_capital
    maximum_drawdown = 0.0
    for point in curve:
        peak = max(peak, point['equity'])
        maximum_drawdown = max(
            maximum_drawdown,
            (peak - point['equity']) / peak * 100,
        )

    return {
        'initial_capital': round(initial_capital, 2),
        'final_value': round(equity, 2),
        'return_pct': round((equity / initial_capital - 1) * 100, 2),
        'buy_and_hold_return_pct': round(
            (buy_and_hold_value / initial_capital - 1) * 100,
            2,
        ),
        'max_drawdown_pct': round(maximum_drawdown, 2),
        'total_trades': len(closed_trades),
        'winning_trades': sum(trade['return_pct'] > 0 for trade in closed_trades),
        'equity_curve': curve,
        'actions': actions,
    }


def run_q_learning_backtest(candles, symbol, initial_capital=100_000):
    if not isinstance(candles, list) or len(candles) < MIN_CANDLES:
        raise ValueError(
            f'At least {MIN_CANDLES} historical candles are required for an RL backtest.'
        )
    if (
        isinstance(initial_capital, bool)
        or not isinstance(initial_capital, (int, float))
        or not math.isfinite(initial_capital)
        or initial_capital <= 0
    ):
        raise ValueError('Initial capital must be a positive finite number.')

    closes = []
    for candle in candles:
        try:
            close = float(candle['close'])
            timestamp = candle['time']
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Historical candles must include a date and closing price.') from error
        if not math.isfinite(close) or close <= 0 or not timestamp:
            raise ValueError('Historical candles contain an invalid date or closing price.')
        closes.append(close)

    split_index = int(len(candles) * TRAIN_RATIO)
    if split_index < MIN_CANDLES // 2 or len(candles) - split_index < 20:
        raise ValueError('Historical data is too short for a separate training and test period.')

    training_candles = candles[:split_index]
    test_candles = candles[split_index:]
    training_closes = closes[:split_index]
    test_closes = closes[split_index:]
    q_table = _train_q_table(training_closes, DEFAULT_EPISODES)
    evaluation = _evaluate(
        q_table,
        test_candles,
        test_closes,
        float(initial_capital),
        training_closes[-LOOKBACK:],
    )

    return {
        'symbol': symbol.strip().upper(),
        'method': 'Tabular Q-learning',
        'data_source': 'Bundled historical CSV; offline simulation',
        'episodes': DEFAULT_EPISODES,
        'transaction_cost_pct_per_side': TRANSACTION_COST_RATE * 100,
        'training_period': {
            'observations': len(training_candles),
            'start_date': str(training_candles[0]['time']),
            'end_date': str(training_candles[-1]['time']),
        },
        'test_period': {
            'observations': len(test_candles),
            'start_date': str(test_candles[0]['time']),
            'end_date': str(test_candles[-1]['time']),
        },
        **evaluation,
    }
