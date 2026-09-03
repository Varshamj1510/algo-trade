from backend.services.signal_generator import generate_trade_decision


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
