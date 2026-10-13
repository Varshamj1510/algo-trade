from backend.app import app


def test_login_accepts_email_or_username():
    client = app.test_client()

    for identifier in ('demo@algotrade.com', 'trader'):
        response = client.post('/api/auth/login', json={
            'email': identifier,
            'password': 'demo123',
        })

        assert response.status_code == 200
        assert response.get_json()['user']['email'] == 'demo@algotrade.com'
