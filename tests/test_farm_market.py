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


def test_farm_market_page_starts_without_loading_csv_data():
    client, _headers = authenticated_client()

    response = client.get('/farm-market')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Enter search details and press Search.' in page
    assert 'No data loaded. Search the crop and location first.' in page
    assert "document.getElementById('farm-search').addEventListener('submit'" in page


def test_farm_market_search_filters_crop_and_district():
    client, headers = authenticated_client()

    response = client.get('/api/farm-market/markets?crop=TOMATO&district=Kolar', headers=headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body['live'] is True
    assert 'CSV' in body['source']
    rows = body['data']
    assert rows
    assert all(row['crop'] == 'Tomato' for row in rows)
    assert all(row['district'] == 'Kolar' for row in rows)
    assert all(row['price'] > 0 for row in rows)


def test_farm_market_csv_has_tomato_and_karnataka_records():
    client, headers = authenticated_client()

    response = client.get('/api/farm-market/markets?crop=Tomato&state=Karnataka', headers=headers)

    assert response.status_code == 200
    rows = response.get_json()['data']
    assert rows
    assert all(row['state'] == 'Karnataka' for row in rows)
    assert all(row['crop'] == 'Tomato' for row in rows)


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


def test_tender_coconut_is_available_in_history_csv():
    client, headers = authenticated_client()

    response = client.get('/api/farm-market/history/tender-coconut?district=Chikkamagaluru', headers=headers)

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['observations'] > 0
    assert data['latest']['variety'] == 'Tender Coconut'
    assert data['observations'] == len(data['rows']) or data['observations'] >= len(data['rows'])


def test_tender_coconut_history_returns_real_csv_observations():
    client, headers = authenticated_client()

    response = client.get('/api/farm-market/history/tender-coconut?district=Hassan', headers=headers)

    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['observations'] > 0
    assert data['latest']['district'] == 'Hassan'
    assert data['latest']['modal_price'] > 0


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
