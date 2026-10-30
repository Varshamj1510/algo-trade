from unittest.mock import patch
from types import SimpleNamespace

import backend.app as app_module
from backend.app import app
from backend.database import db
from backend.models import (
    PasskeyCredential,
    User,
    UserAuthPin,
)


def test_registration_page_includes_relevant_terms_before_acceptance():
    response = app.test_client().get('/')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'id="terms-and-conditions"' in page
    assert 'I have read and agree to the Terms &amp; Conditions.' in page
    assert 'No investment advice' in page
    assert 'Simulated trading' in page
    assert 'possible loss of some or all of your invested capital' in page
    assert 'id="terms-agreement" type="checkbox" required' in page
    assert 'verification' not in page.lower()


def test_login_confirmation_explains_available_sign_in_methods():
    response = app.test_client().get('/login?registered=1')

    assert response.status_code == 200
    assert 'Your account is ready. Sign in with your password, PIN, or passkey.' in (
        response.get_data(as_text=True)
    )


def test_profile_page_marks_profile_navigation_anchor():
    response = app.test_client().get('/profile')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert '<li class="nav-item active" data-page="profile">' in page


def test_login_accepts_email_or_username():
    client = app.test_client()

    for identifier in ('demo@algotrade.com', 'trader'):
        response = client.post('/api/auth/login', json={
            'email': identifier,
            'password': 'demo123',
        })

        assert response.status_code == 200
        assert response.get_json()['user']['email'] == 'demo@algotrade.com'


def test_registration_sets_hashed_alpha_pin_for_pin_sign_in():
    client = app.test_client()
    email = f'pin-{app_module.secrets.token_hex(8)}@example.test'
    payload = {
        'full_name': 'PIN Trader',
        'email': email,
        'username': f'pin-{app_module.secrets.token_hex(8)}',
        'password': 'registration-password',
        'pin': '482917',
    }
    registration = client.post('/api/auth/register', json=payload)
    assert registration.status_code == 201
    assert registration.get_json()['user']['email'] == email
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user.check_password('registration-password')
        auth_pin = UserAuthPin.query.filter_by(user_id=user.id).first()
        assert auth_pin is not None
        assert auth_pin.pin_hash != '482917'

    signed_in = client.post('/api/auth/pin/login', json={
        'email': email,
        'pin': '482917',
    })
    assert signed_in.status_code == 200
    assert signed_in.get_json()['user']['email'] == email


def test_registration_uses_username_without_a_full_name_field():
    response = app.test_client().post('/api/auth/register', json={
        'email': f'username-{app_module.secrets.token_hex(8)}@example.test',
        'username': f'username-{app_module.secrets.token_hex(8)}',
        'password': 'registration-password',
    })

    assert response.status_code == 201
    user_data = response.get_json()['user']
    assert 'full_name' not in user_data
    assert user_data['username']


def test_registration_rejects_invalid_alpha_pin():
    response = app.test_client().post('/api/auth/register', json={
        'full_name': 'PIN Trader',
        'email': f'invalid-pin-{app_module.secrets.token_hex(8)}@example.test',
        'username': f'invalid-pin-{app_module.secrets.token_hex(8)}',
        'password': 'registration-password',
        'pin': '12ab56',
    })

    assert response.status_code == 400
    assert response.get_json()['message'] == 'PIN must contain exactly 6 digits.'


def test_registration_with_existing_email_points_to_sign_in():
    client = app.test_client()
    email = f'existing-{app_module.secrets.token_hex(8)}@example.test'
    first = client.post('/api/auth/register', json={
        'full_name': 'Existing Trader',
        'email': email,
        'username': f'existing-{app_module.secrets.token_hex(8)}',
        'password': 'registration-password',
        'pin': '482917',
    })
    assert first.status_code == 201

    duplicate = client.post('/api/auth/register', json={
        'full_name': 'Existing Trader',
        'email': email,
        'username': f'other-{app_module.secrets.token_hex(8)}',
        'password': 'another-password',
        'pin': '123456',
    })

    assert duplicate.status_code == 409
    assert duplicate.get_json()['message'] == (
        'An account with this email already exists. Sign in instead.'
    )


def test_pin_sign_in_without_pin_explains_password_setup():
    client = app.test_client()
    email = f'no-pin-{app_module.secrets.token_hex(8)}@example.test'
    registration = client.post('/api/auth/register', json={
        'full_name': 'No PIN Trader',
        'email': email,
        'username': f'no-pin-{app_module.secrets.token_hex(8)}',
        'password': 'registration-password',
    })
    assert registration.status_code == 201

    response = client.post('/api/auth/pin/login', json={
        'email': email,
        'pin': '482917',
    })

    assert response.status_code == 400
    assert response.get_json()['message'] == (
        'This account does not have a PIN yet. Sign in with your password to set one up.'
    )


def test_local_passkey_origin_uses_current_server_port():
    with app.test_request_context('/', base_url='http://localhost:3000'):
        assert app_module._expected_webauthn_rp_id() == 'localhost'
        assert app_module._expected_webauthn_origin() == 'http://localhost:3000'


def test_default_passkey_rp_id_follows_the_current_public_host():
    with app.test_request_context('/', base_url='https://alphamind.example.test'):
        assert app_module._expected_webauthn_rp_id() == 'alphamind.example.test'
        assert app_module._expected_webauthn_origin() == 'https://alphamind.example.test'


def test_otp_auth_routes_are_removed():
    client = app.test_client()

    for path in (
        '/api/auth/request-otp',
        '/api/auth/verify-otp',
        '/api/auth/verify-registration-otp',
    ):
        response = client.post(path, json={})
        assert response.status_code in {404, 405}

    login_page = client.get('/login').get_data(as_text=True).lower()
    registration_page = client.get('/').get_data(as_text=True).lower()
    assert 'otp' not in login_page
    assert 'otp' not in registration_page


def test_login_page_has_no_passkey_or_fingerprint_sign_in():
    page = app.test_client().get('/login').get_data(as_text=True).lower()

    assert 'fingerprint' not in page
    assert 'passkey-login-btn' not in page
    assert '/api/auth/passkey/login' not in page


def test_profile_page_uses_username_without_full_name_editor():
    page = app.test_client().get('/profile').get_data(as_text=True).lower()

    assert 'profile-name' not in page
    assert 'full name' not in page


def test_pin_setup_requires_password_and_allows_pin_sign_in():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    token = login.get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}

    with app.app_context():
        user = User.query.filter_by(email='demo@algotrade.com').first()
        UserAuthPin.query.filter_by(user_id=user.id).delete()
        db.session.commit()

    rejected = client.put('/api/auth/pin', headers=headers, json={
        'current_password': 'wrong-password',
        'pin': '123456',
    })
    assert rejected.status_code == 400

    configured = client.put('/api/auth/pin', headers=headers, json={
        'current_password': 'demo123',
        'pin': '482917',
    })
    assert configured.status_code == 200

    signed_in = client.post('/api/auth/pin/login', json={
        'email': 'demo@algotrade.com',
        'pin': '482917',
    })
    assert signed_in.status_code == 200
    assert signed_in.get_json()['user']['email'] == 'demo@algotrade.com'

    with app.app_context():
        user = User.query.filter_by(email='demo@algotrade.com').first()
        UserAuthPin.query.filter_by(user_id=user.id).delete()
        db.session.commit()


def test_pin_sign_in_locks_after_five_incorrect_attempts():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    headers = {'Authorization': f'Bearer {login.get_json()["token"]}'}
    with app.app_context():
        user = User.query.filter_by(email='demo@algotrade.com').first()
        UserAuthPin.query.filter_by(user_id=user.id).delete()
        db.session.commit()

    configured = client.put('/api/auth/pin', headers=headers, json={
        'current_password': 'demo123',
        'pin': '482917',
    })
    assert configured.status_code == 200

    for attempt in range(4):
        response = client.post('/api/auth/pin/login', json={
            'email': 'demo@algotrade.com',
            'pin': f'{attempt:06d}',
        })
        assert response.status_code == 401

    locked = client.post('/api/auth/pin/login', json={
        'email': 'demo@algotrade.com',
        'pin': '000004',
    })
    assert locked.status_code == 429
    assert client.post('/api/auth/pin/login', json={
        'email': 'demo@algotrade.com',
        'pin': '482917',
    }).status_code == 429

    with app.app_context():
        user = User.query.filter_by(email='demo@algotrade.com').first()
        UserAuthPin.query.filter_by(user_id=user.id).delete()
        db.session.commit()


def test_passkey_registration_and_login_challenges():
    client = app.test_client()
    login = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    token = login.get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}

    with app.app_context():
        user = User.query.filter_by(email='demo@algotrade.com').first()
        PasskeyCredential.query.filter_by(user_id=user.id).delete()
        db.session.commit()

    registered_credential = SimpleNamespace(
        credential_id=b'test-passkey',
        credential_public_key=b'test-public-key',
        sign_count=0,
    )
    credential_payload = {
        'id': 'dGVzdC1wYXNza2V5',
        'rawId': 'dGVzdC1wYXNza2V5',
        'type': 'public-key',
        'response': {
            'clientDataJSON': 'dGVzdA',
            'attestationObject': 'dGVzdA',
            'transports': ['internal'],
        },
    }
    with patch.object(
        app_module,
        'verify_registration_response',
        return_value=registered_credential,
    ) as verify_registration:
        registration_options = client.post(
            '/api/auth/passkey/register/options',
            headers=headers,
            json={},
        )
        assert registration_options.status_code == 200
        registration_result = client.post(
            '/api/auth/passkey/register/verify',
            headers=headers,
            json={
                'challenge_id': registration_options.get_json()['challenge_id'],
                'credential': credential_payload,
            },
        )
        assert registration_result.status_code == 200
        verify_registration.assert_called_once()
        assert verify_registration.call_args.kwargs['expected_origin'] == 'http://localhost'

    with patch.object(
        app_module,
        'verify_authentication_response',
        return_value=SimpleNamespace(new_sign_count=1),
    ) as verify_authentication:
        authentication_options = client.post(
            '/api/auth/passkey/login/options',
            json={'email': 'demo@algotrade.com'},
        )
        assert authentication_options.status_code == 200
        authentication_result = client.post(
            '/api/auth/passkey/login/verify',
            json={
                'challenge_id': authentication_options.get_json()['challenge_id'],
                'credential': credential_payload,
            },
        )
        assert authentication_result.status_code == 200
        assert authentication_result.get_json()['user']['email'] == 'demo@algotrade.com'
        verify_authentication.assert_called_once()
        assert verify_authentication.call_args.kwargs['expected_origin'] == 'http://localhost'
        replay = client.post(
            '/api/auth/passkey/login/verify',
            json={
                'challenge_id': authentication_options.get_json()['challenge_id'],
                'credential': credential_payload,
            },
        )
        assert replay.status_code == 401

    with app.app_context():
        user = User.query.filter_by(email='demo@algotrade.com').first()
        PasskeyCredential.query.filter_by(user_id=user.id).delete()
        db.session.commit()
