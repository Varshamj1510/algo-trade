from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app import app
from backend.routes import academy_routes


@pytest.fixture
def academy_client():
    client = app.test_client()
    identity = uuid4().hex
    registration = client.post('/api/auth/register', json={
        'full_name': 'Academy Learner',
        'email': f'academy-{identity}@example.test',
        'username': f'academy-{identity}',
        'password': 'academy-test-password',
    })
    assert registration.status_code == 201
    return client, {'Authorization': f"Bearer {registration.get_json()['token']}"}


def test_academy_starts_free_and_locks_premium_video_search(academy_client, monkeypatch):
    client, headers = academy_client
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-api-key')
    search_calls = []
    monkeypatch.setattr(academy_routes.requests, 'get', lambda *args, **kwargs: search_calls.append(args))

    access = client.get('/api/academy/access', headers=headers)
    locked_search = client.get(
        '/api/academy/youtube-search?q=chart%20patterns&tier=premium',
        headers=headers,
    )

    assert access.status_code == 200
    assert access.get_json()['data']['tier'] == 'free'
    assert access.get_json()['data']['premium_price_inr'] == 199
    assert locked_search.status_code == 403
    assert search_calls == []


def test_demo_premium_unlock_expires_and_makes_premium_search_available(academy_client, monkeypatch):
    client, headers = academy_client
    monkeypatch.setenv('YOUTUBE_API_KEY', 'server-only-test-key')
    captured = {}

    def fake_get(url, *, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {'items': [{
                'id': {'videoId': 'abcdefghijk'},
                'snippet': {
                    'title': 'Candlestick Basics',
                    'description': 'A beginner lesson.',
                    'channelTitle': 'Learning Channel',
                    'publishedAt': '2026-01-02T03:04:05Z',
                },
            }]},
        )

    monkeypatch.setattr(academy_routes.requests, 'get', fake_get)

    unlock = client.post('/api/academy/premium-demo', headers=headers, json={})
    search = client.get(
        '/api/academy/youtube-search?q=candlesticks&tier=premium',
        headers=headers,
    )

    assert unlock.status_code == 200
    assert unlock.get_json()['data']['tier'] == 'premium'
    assert unlock.get_json()['data']['demo_unlock'] is True
    assert 'No payment was made' in unlock.get_json()['message']
    assert search.status_code == 200
    assert search.get_json()['data'][0]['video_id'] == 'abcdefghijk'
    assert search.get_json()['data'][0]['thumbnail'].endswith('/abcdefghijk/mqdefault.jpg')
    assert captured['params']['key'] == 'server-only-test-key'
    assert captured['params']['videoEmbeddable'] == 'true'
    assert captured['params']['safeSearch'] == 'strict'
    assert captured['timeout'] == 10
    assert 'server-only-test-key' not in str(search.get_json())


def test_youtube_search_reports_missing_api_key_without_exposing_credentials(academy_client, monkeypatch):
    client, headers = academy_client
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)

    response = client.get(
        '/api/academy/youtube-search?q=trading%20basics&tier=free',
        headers=headers,
    )

    assert response.status_code == 503
    assert 'YOUTUBE_API_KEY' in response.get_json()['message']


@pytest.mark.parametrize('query,tier', [('', 'free'), ('x' * 101, 'free'), ('lesson', 'unknown')])
def test_youtube_search_validates_query_and_tier(academy_client, query, tier):
    client, headers = academy_client

    response = client.get(
        f'/api/academy/youtube-search?q={query}&tier={tier}',
        headers=headers,
    )

    assert response.status_code == 400
