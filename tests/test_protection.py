import pytest

from backend.app import app


def authenticated_client():
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    token = response.get_json()['token']
    return client, {'Authorization': f'Bearer {token}'}


def test_protection_calculator_estimates_long_trade():
    client, headers = authenticated_client()

    response = client.post('/api/protection/calculate', headers=headers, json={
        'side': 'BUY',
        'entry_price': 100,
        'stop_loss_price': 95,
        'take_profit_price': 110,
        'quantity': 10,
        'account_balance': 10000,
        'risk_percent': 1,
        'trailing_percent': 2,
    })

    assert response.status_code == 200
    result = response.get_json()['data']
    assert result['risk_amount'] == 100
    assert result['position_size'] == 20
    assert result['maximum_loss'] == 50
    assert result['potential_profit'] == 100
    assert result['risk_reward_ratio'] == 2
    assert result['trailing_stop_price'] == 98


@pytest.mark.parametrize(('side', 'stop', 'target'), [
    ('BUY', 105, 110),
    ('SELL', 95, 90),
])
def test_protection_calculator_rejects_stop_on_wrong_side(side, stop, target):
    client, headers = authenticated_client()

    response = client.post('/api/protection/calculate', headers=headers, json={
        'side': side,
        'entry_price': 100,
        'stop_loss_price': stop,
        'take_profit_price': target,
        'account_balance': 10000,
        'risk_percent': 1,
    })

    assert response.status_code == 400
    assert 'Stop-loss must be' in response.get_json()['message']


def test_protection_calculator_requires_authentication():
    response = app.test_client().post('/api/protection/calculate', json={})

    assert response.status_code == 401
