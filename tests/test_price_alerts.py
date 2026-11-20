import base64
from datetime import datetime, timezone
import secrets
from types import SimpleNamespace

import pytest

import backend.app as app_module
from backend.app import app
from backend.database import db
from backend.models import AlertNotificationSettings, AlertPushSubscription, PriceAlert, User
from backend.services import price_alert_worker


def valid_push_keys():
    return {
        'p256dh': base64.urlsafe_b64encode(b'\x04' + b'\x01' * 64).decode().rstrip('='),
        'auth': base64.urlsafe_b64encode(b'\x02' * 16).decode().rstrip('='),
    }


@pytest.fixture
def authenticated_clients():
    user_ids = []

    def create_client():
        client = app.test_client()
        suffix = secrets.token_hex(8)
        email = f'price-alert-{suffix}@example.test'
        response = client.post('/api/auth/register', json={
            'full_name': 'Price Alert Tester',
            'email': email,
            'username': f'price-alert-{suffix}',
            'password': 'price-alert-test-password',
        })
        assert response.status_code == 201
        with app.app_context():
            user_ids.append(User.query.filter_by(email=email).one().id)
        headers = {'Authorization': f"Bearer {response.get_json()['token']}"}
        return client, headers

    yield create_client

    with app.app_context():
        PriceAlert.query.filter(PriceAlert.user_id.in_(user_ids)).delete(synchronize_session=False)
        AlertPushSubscription.query.filter(
            AlertPushSubscription.user_id.in_(user_ids),
        ).delete(synchronize_session=False)
        AlertNotificationSettings.query.filter(
            AlertNotificationSettings.user_id.in_(user_ids),
        ).delete(synchronize_session=False)
        User.query.filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.session.commit()


def test_price_alert_settings_and_user_scoping(monkeypatch, authenticated_clients):
    client, headers = authenticated_clients()
    other_client, other_headers = authenticated_clients()
    monkeypatch.setattr(app_module, 'find_demo_instrument', lambda symbol, exchange: {
        'symbol': symbol,
        'exchange': exchange,
        'name': 'Alpha Test Company',
    })

    created = client.post('/api/price-alerts', headers=headers, json={
        'symbol': 'ALPHA',
        'exchange': 'NSE',
        'target_price': 125,
        'direction': 'above',
    })
    assert created.status_code == 201
    alert_id = created.get_json()['data']['id']
    paused = client.put(
        f'/api/price-alerts/{alert_id}',
        headers=headers,
        json={'enabled': False},
    )
    assert paused.status_code == 200
    duplicate = client.post('/api/price-alerts', headers=headers, json={
        'symbol': 'ALPHA',
        'exchange': 'NSE',
        'target_price': 125,
        'direction': 'above',
    })
    assert duplicate.status_code == 409
    second_alert = client.post('/api/price-alerts', headers=headers, json={
        'symbol': 'ALPHA',
        'exchange': 'NSE',
        'target_price': 150,
        'direction': 'above',
    })
    update_duplicate = client.put(
        f"/api/price-alerts/{second_alert.get_json()['data']['id']}",
        headers=headers,
        json={'target_price': 125},
    )
    assert update_duplicate.status_code == 409
    own_alerts = client.get('/api/alerts', headers=headers).get_json()['price_alerts']
    assert next(item for item in own_alerts if item['id'] == second_alert.get_json()['data']['id'])['target_price'] == 150
    assert other_client.put(
        f'/api/price-alerts/{alert_id}',
        headers=other_headers,
        json={'enabled': False},
    ).status_code == 404

    invalid_settings = client.put('/api/alerts/settings', headers=headers, json={
        'enabled': True,
        'quiet_hours_enabled': True,
        'quiet_start': '08:00',
        'quiet_end': '08:00',
    })
    assert invalid_settings.status_code == 400
    settings = client.put('/api/alerts/settings', headers=headers, json={
        'enabled': True,
        'quiet_hours_enabled': True,
        'quiet_start': '22:00',
        'quiet_end': '08:00',
    })
    assert settings.status_code == 200
    assert settings.get_json()['data']['enabled'] is True


def test_price_alert_triggers_once_and_requires_live_price_to_reset(monkeypatch, authenticated_clients):
    client, headers = authenticated_clients()
    monkeypatch.setattr(app_module, 'find_demo_instrument', lambda symbol, exchange: {
        'symbol': symbol,
        'exchange': exchange,
        'name': 'Alpha Test Company',
    })
    current_price = {'value': 130}

    def fake_quotes(instruments):
        assert instruments == [{'symbol': 'ALPHA', 'exchange': 'NSE'}]
        return {('NSE', 'ALPHA'): {'price': current_price['value']}}

    monkeypatch.setattr(app_module, 'get_live_quotes', fake_quotes)
    created = client.post('/api/price-alerts', headers=headers, json={
        'symbol': 'ALPHA',
        'exchange': 'NSE',
        'target_price': 125,
        'direction': 'above',
    })
    alert_id = created.get_json()['data']['id']
    client.put('/api/alerts/settings', headers=headers, json={
        'enabled': True,
        'quiet_hours_enabled': False,
        'quiet_start': '22:00',
        'quiet_end': '08:00',
    })

    first_check = client.post('/api/alerts/check', headers=headers, json={})
    first_pending = first_check.get_json()['data']['pending_notifications']
    assert len(first_pending) == 1
    assert first_pending[0]['id'] == alert_id
    assert first_pending[0]['triggered_price'] == 130

    second_check = client.post('/api/alerts/check', headers=headers, json={})
    assert len(second_check.get_json()['data']['pending_notifications']) == 1
    assert client.post('/api/alerts/acknowledge', headers=headers, json={
        'alert_ids': [alert_id],
    }).status_code == 200
    acknowledged_check = client.post('/api/alerts/check', headers=headers, json={})
    assert acknowledged_check.get_json()['data']['pending_notifications'] == []

    still_met = client.post(f'/api/price-alerts/{alert_id}/reset', headers=headers, json={})
    assert still_met.status_code == 409
    current_price['value'] = 120
    reset = client.post(f'/api/price-alerts/{alert_id}/reset', headers=headers, json={})
    assert reset.status_code == 200
    current_price['value'] = 130
    retriggered = client.post('/api/alerts/check', headers=headers, json={})
    assert len(retriggered.get_json()['data']['pending_notifications']) == 1


def test_price_alerts_do_not_trigger_without_live_quotes(monkeypatch, authenticated_clients):
    client, headers = authenticated_clients()
    monkeypatch.setattr(app_module, 'find_demo_instrument', lambda symbol, exchange: {
        'symbol': symbol,
        'exchange': exchange,
        'name': 'Alpha Test Company',
    })

    def unavailable_quotes(instruments):
        raise app_module.KiteConfigurationError('Kite session unavailable.')

    monkeypatch.setattr(app_module, 'get_live_quotes', unavailable_quotes)
    created = client.post('/api/price-alerts', headers=headers, json={
        'symbol': 'ALPHA',
        'exchange': 'NSE',
        'target_price': 125,
        'direction': 'above',
    })
    client.put('/api/alerts/settings', headers=headers, json={
        'enabled': True,
        'quiet_hours_enabled': False,
        'quiet_start': '22:00',
        'quiet_end': '08:00',
    })

    check = client.post('/api/alerts/check', headers=headers, json={})
    assert check.status_code == 503
    assert check.get_json()['market_data_available'] is False
    saved = client.get('/api/alerts', headers=headers).get_json()['price_alerts']
    assert saved[0]['id'] == created.get_json()['data']['id']
    assert saved[0]['triggered'] is False


def test_alerts_page_contains_user_controls():
    response = app.test_client().get('/alerts')
    service_worker = app.test_client().get('/service-worker.js')

    assert response.status_code == 200
    assert b'id="price-alert-form"' in response.data
    assert b'id="notifications-enabled"' in response.data
    assert b'id="quiet-hours-enabled"' in response.data
    assert b'/service-worker.js' in response.data
    assert service_worker.status_code == 200
    assert b"addEventListener('push'" in service_worker.data


def test_push_subscription_is_user_scoped(monkeypatch, authenticated_clients):
    client, headers = authenticated_clients()
    other_client, other_headers = authenticated_clients()
    monkeypatch.setitem(app.config, 'VAPID_PUBLIC_KEY', 'public-test-key')
    monkeypatch.setitem(app.config, 'VAPID_PRIVATE_KEY', 'private-test-key')
    response = client.get('/api/alerts/push/public-key', headers=headers)
    assert response.status_code == 200
    assert response.get_json()['data']['public_key'] == 'public-test-key'

    subscription = {
        'endpoint': 'https://fcm.googleapis.com/fcm/send/unique-id',
        'keys': valid_push_keys(),
    }
    created = client.post('/api/alerts/push/subscribe', headers=headers, json=subscription)
    assert created.status_code == 200
    rejected = client.post('/api/alerts/push/subscribe', headers=headers, json={
        **subscription,
        'endpoint': 'https://127.0.0.1/not-a-browser-push-endpoint',
    })
    assert rejected.status_code == 400
    malformed_port = client.post('/api/alerts/push/subscribe', headers=headers, json={
        **subscription,
        'endpoint': 'https://fcm.googleapis.com:invalid/fcm/send/unique-id',
    })
    assert malformed_port.status_code == 400
    other_client.delete(
        '/api/alerts/push/subscribe',
        headers=other_headers,
        json={'endpoint': subscription['endpoint']},
    )
    with app.app_context():
        assert AlertPushSubscription.query.filter_by(
            endpoint=subscription['endpoint'],
        ).count() == 1
    removed = client.delete(
        '/api/alerts/push/subscribe',
        headers=headers,
        json={'endpoint': subscription['endpoint']},
    )
    assert removed.status_code == 200


def test_quiet_hours_use_the_users_timezone():
    settings = SimpleNamespace(
        quiet_hours_enabled=True,
        timezone='Asia/Kolkata',
        quiet_start='22:00',
        quiet_end='08:00',
    )
    assert price_alert_worker._quiet_hours_active(
        settings,
        datetime(2026, 10, 27, 17, 30, tzinfo=timezone.utc),
    )
    assert price_alert_worker._quiet_hours_active(
        settings,
        datetime(2026, 10, 27, 2, 0, tzinfo=timezone.utc),
    )
    assert not price_alert_worker._quiet_hours_active(
        settings,
        datetime(2026, 10, 27, 4, 0, tzinfo=timezone.utc),
    )


def test_worker_triggers_and_pushes_once(monkeypatch, authenticated_clients):
    client, headers = authenticated_clients()
    monkeypatch.setattr(app_module, 'find_demo_instrument', lambda symbol, exchange: {
        'symbol': symbol,
        'exchange': exchange,
        'name': 'Alpha Test Company',
    })
    monkeypatch.setattr(price_alert_worker, 'VAPID_PRIVATE_KEY', 'private-test-key')
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'public-test-key')
    deliveries = []
    monkeypatch.setattr(
        price_alert_worker,
        'get_live_quotes',
        lambda instruments: {('NSE', 'ALPHA'): {'price': 130}},
    )
    monkeypatch.setattr(
        price_alert_worker,
        '_send_to_subscription',
        lambda subscription, alert: deliveries.append((subscription.id, alert.id)),
    )
    created = client.post('/api/price-alerts', headers=headers, json={
        'symbol': 'ALPHA',
        'exchange': 'NSE',
        'target_price': 125,
        'direction': 'above',
    })
    client.put('/api/alerts/settings', headers=headers, json={
        'enabled': True,
        'quiet_hours_enabled': False,
        'quiet_start': '22:00',
        'quiet_end': '08:00',
        'timezone': 'Asia/Kolkata',
    })
    client.post('/api/alerts/push/subscribe', headers=headers, json={
        'endpoint': 'https://fcm.googleapis.com/fcm/send/worker',
        'keys': valid_push_keys(),
    })

    with app.app_context():
        price_alert_worker.check_and_deliver_price_alerts()
        price_alert_worker.check_and_deliver_price_alerts()
        alert = PriceAlert.query.get(created.get_json()['data']['id'])
        assert alert.triggered_at is not None
        assert alert.notification_delivered_at is not None
    assert len(deliveries) == 1
