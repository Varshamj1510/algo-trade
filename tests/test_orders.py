from backend.app import app


def authenticated_client():
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    token = response.get_json()['token']
    return client, {'Authorization': f'Bearer {token}'}


def test_stop_loss_market_requires_trigger_price():
    client, headers = authenticated_client()

    response = client.post('/api/orders', headers=headers, json={
        'symbol': 'RELIANCE',
        'exchange': 'NSE',
        'side': 'SELL',
        'order_type': 'STOP_LOSS_MARKET',
        'quantity': 1,
    })

    assert response.status_code == 400
    assert response.get_json()['message'] == 'Stop-loss orders require a trigger price.'


def test_order_rejects_non_numeric_quantity():
    client, headers = authenticated_client()

    response = client.post('/api/orders', headers=headers, json={
        'symbol': 'RELIANCE',
        'exchange': 'NSE',
        'side': 'BUY',
        'order_type': 'MARKET',
        'quantity': 'invalid',
    })

    assert response.status_code == 400
    assert response.get_json()['message'] == 'Quantity and order prices must be valid numbers.'
