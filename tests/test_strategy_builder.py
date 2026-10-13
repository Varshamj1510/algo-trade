import pytest

from backend.app import app
from backend.database import db
from backend.models import StrategyModel
from backend.services.strategy_engine import preview_strategy, validate_strategy_rules


def sample_rules():
    return {
        'buy_logic': 'AND',
        'buy_conditions': [{'indicator': 'rsi', 'operator': 'lt', 'value': 30}],
        'sell_logic': 'OR',
        'sell_conditions': [{'indicator': 'rsi', 'operator': 'gt', 'value': 70}],
    }


def authenticated_client():
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    token = response.get_json()['token']
    return client, {'Authorization': f'Bearer {token}'}


def test_strategy_preview_returns_buy_when_only_buy_rules_match():
    rules = validate_strategy_rules(sample_rules())

    result = preview_strategy(rules, {'rsi': 25})

    assert result['signal'] == 'BUY'
    assert result['buy_matches'] is True
    assert result['sell_matches'] is False


def test_strategy_preview_returns_hold_when_buy_and_sell_match():
    data = {
        'buy_logic': 'OR',
        'buy_conditions': [
            {'indicator': 'rsi', 'operator': 'lt', 'value': 30},
            {'indicator': 'macd', 'operator': 'gt', 'value': 1},
        ],
        'sell_logic': 'AND',
        'sell_conditions': [{'indicator': 'rsi', 'operator': 'lt', 'value': 30}],
    }
    rules = validate_strategy_rules(data)

    result = preview_strategy(rules, {'rsi': 20, 'macd': 2})

    assert result['signal'] == 'HOLD'
    assert result['conflict'] is True


@pytest.mark.parametrize('condition', [
    {'indicator': 'unsupported', 'operator': 'gt', 'value': 1},
    {'indicator': [], 'operator': 'gt', 'value': 1},
    {'indicator': 'rsi', 'operator': {}, 'value': 1},
    {'indicator': 'rsi', 'operator': 'exec', 'value': 1},
    {'indicator': 'rsi', 'operator': 'gt', 'value': 101},
    {'indicator': 'price', 'operator': 'gt', 'value': float('inf')},
])
def test_strategy_rules_reject_invalid_conditions(condition):
    data = sample_rules()
    data['buy_conditions'] = [condition]

    with pytest.raises(ValueError):
        validate_strategy_rules(data)


def test_strategy_preview_requires_values_for_rule_indicators():
    rules = validate_strategy_rules(sample_rules())

    with pytest.raises(ValueError, match='RSI value is required'):
        preview_strategy(rules, {})


@pytest.mark.parametrize('indicator', [
    'rsi', 'macd', 'ema', 'sma', 'bollinger_upper', 'bollinger_middle',
    'bollinger_lower', 'vwap', 'atr', 'obv',
])
def test_strategy_rules_accepts_requested_technical_indicators(indicator):
    data = sample_rules()
    data['buy_conditions'] = [{'indicator': indicator, 'operator': 'gt', 'value': 1}]
    data['sell_conditions'] = [{'indicator': indicator, 'operator': 'lt', 'value': 10}]

    rules = validate_strategy_rules(data)
    result = preview_strategy(rules, {indicator: 5})

    assert result['buy_matches'] is True
    assert result['sell_matches'] is True
    assert result['signal'] == 'HOLD'


def test_strategy_rules_accepts_signed_macd_and_obv_values():
    for indicator in ('macd', 'obv'):
        data = sample_rules()
        data['buy_conditions'] = [{'indicator': indicator, 'operator': 'lt', 'value': -1}]
        data['sell_conditions'] = [{'indicator': indicator, 'operator': 'gt', 'value': 1}]

        rules = validate_strategy_rules(data)
        result = preview_strategy(rules, {indicator: -2})

        assert result['signal'] == 'BUY'


def test_strategy_create_persists_conditions_for_current_user():
    client, headers = authenticated_client()
    response = client.post('/api/strategies', headers=headers, json={
        'name': 'Saved RSI Rule Test',
        'description': 'Temporary integration test strategy.',
        **sample_rules(),
    })
    strategy_id = None
    try:
        assert response.status_code == 201
        strategy_id = response.get_json()['data']['id']
        assert response.get_json()['data']['is_custom'] is True
        assert response.get_json()['data']['buy_conditions'] == sample_rules()['buy_conditions']

        listed = client.get('/api/strategies', headers=headers)
        saved = next(item for item in listed.get_json()['data'] if item['id'] == strategy_id)
        assert saved['sell_logic'] == 'OR'
        assert saved['sell_conditions'] == sample_rules()['sell_conditions']
    finally:
        if strategy_id is not None:
            with app.app_context():
                strategy = db.session.get(StrategyModel, strategy_id)
                if strategy:
                    db.session.delete(strategy)
                    db.session.commit()


def test_strategy_preview_api_evaluates_manual_snapshot():
    client, headers = authenticated_client()

    response = client.post('/api/strategies/preview', headers=headers, json={
        **sample_rules(),
        'indicator_values': {'rsi': 25},
    })

    assert response.status_code == 200
    assert response.get_json()['data']['signal'] == 'BUY'


def test_strategy_builder_api_requires_authentication():
    response = app.test_client().get('/api/strategies')

    assert response.status_code == 401
