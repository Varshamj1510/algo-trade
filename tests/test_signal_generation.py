from backend.services.signal_generator import generate_demo_trade_signals, generate_trade_decision


def test_generate_trade_decision_buy():
    result = generate_trade_decision('RELIANCE', 2856.4, 68, 120, 2740, 2810)

    assert result['signal'] == 'BUY'
    assert 50 <= result['confidence'] <= 100
    assert 'reason' in result
    assert 'symbol' in result


def test_generate_trade_decision_sell_when_bearish():
    result = generate_trade_decision('INFY', 1482.5, 32, -90, 1520, 1580)

    assert result['signal'] == 'SELL'
    assert 50 <= result['confidence'] <= 100


def test_demo_trade_signals_are_derived_from_demo_price_changes():
    signals = generate_demo_trade_signals([
        {'symbol': 'BUYER', 'price': 100, 'change': 1.5},
        {'symbol': 'SELLER', 'price': 200, 'change': -1.5},
        {'symbol': 'HOLDER', 'price': 300, 'change': 0.2},
    ])

    assert [signal['signal'] for signal in signals] == ['BUY', 'SELL', 'HOLD']
    assert [signal['current_price'] for signal in signals] == [100, 200, 300]
    assert signals[0]['target_price'] == 102
    assert signals[0]['stop_loss'] == 98
    assert signals[1]['target_price'] == 196
    assert signals[1]['stop_loss'] == 204
    assert signals[2]['target_price'] is None
    assert all(signal['timestamp'] == 'Demo sample' for signal in signals)
