from backend.app import app


def authenticated_client():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    assert login.status_code == 200
    token = login.get_json()['token']
    return client, {'Authorization': f'Bearer {token}'}


def test_farm_market_search_filters_crop_and_district():
    client, headers = authenticated_client()

    response = client.get('/api/farm-market/markets?crop=TOMATO&district=Kolar', headers=headers)

    assert response.status_code == 200
    rows = response.get_json()['data']
    assert len(rows) == 1
    assert rows[0]['crop'] == 'Tomato'
    assert rows[0]['district'] == 'Kolar'
    assert rows[0]['market'] == 'Kolar APMC'


def test_farm_recommendation_returns_sell_wait_or_store():
    client, headers = authenticated_client()

    response = client.post('/api/farm-market/recommend', headers=headers, json={
        'crop': 'Tomato',
        'price': 2350,
        'previous_price': 2180,
        'quantity': 20,
        'transport_cost': 3600,
        'storage_cost': 2500,
        'distance_km': 62,
    })

    assert response.status_code == 200
    result = response.get_json()['data']
    assert result['action'] in {'SELL NOW', 'WAIT', 'STORE'}
    assert result['gross_revenue'] == 47000
    assert result['net_revenue'] == 40900


def test_farm_resources_include_buyers_schemes_weather_and_languages():
    client, headers = authenticated_client()

    response = client.get('/api/farm-market/resources?crop=Tomato&district=Kolar', headers=headers)

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['buyers']
    assert data['schemes']
    assert data['weather_alerts']
    assert 'Kannada' in data['languages']
    assert data['offline']['enabled'] is True
