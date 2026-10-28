import re
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from types import TracebackType
from unittest.mock import patch
from types import SimpleNamespace

import backend.app as app_module
from backend.app import app
from backend.database import db
from backend.models import EmailLoginCode, PasskeyCredential, User, UserAuthPin
from sqlalchemy import delete


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
    registration = client.post('/api/auth/register', json={
        'full_name': 'PIN Trader',
        'email': email,
        'username': f'pin-{app_module.secrets.token_hex(8)}',
        'password': 'registration-password',
        'pin': '482917',
    })

    assert registration.status_code == 201
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        auth_pin = UserAuthPin.query.filter_by(user_id=user.id).first()
        assert auth_pin is not None
        assert auth_pin.pin_hash != '482917'

    signed_in = client.post('/api/auth/pin/login', json={
        'email': email,
        'pin': '482917',
    })
    assert signed_in.status_code == 200
    assert signed_in.get_json()['user']['email'] == email


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


def test_email_code_sign_in():
    sent_messages: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> bool:
            return False

        def starttls(self) -> None:
            pass

        def login(self, username: str, password: str) -> None:
            pass

        def send_message(self, message: EmailMessage) -> None:
            sent_messages.append(message)

    mail_config: dict[str, str | int | bool] = {
        'MAIL_SERVER': 'smtp.example.com',
        'MAIL_PORT': 587,
        'MAIL_DEFAULT_SENDER': 'no-reply@example.com',
        'MAIL_USE_TLS': True,
        'MAIL_USE_SSL': False,
        'MAIL_USERNAME': 'smtp-user',
        'MAIL_PASSWORD': 'smtp-password',
    }
    with patch.object(app_module.smtplib, 'SMTP', FakeSMTP), patch.dict(app.config, mail_config):
        with app.app_context():
            db.session.execute(delete(EmailLoginCode).where(
                EmailLoginCode.email == 'demo@algotrade.com'
            ))
            db.session.commit()

        client = app.test_client()
        response = client.post('/api/auth/request-otp', json={
            'email': 'demo@algotrade.com',
        })

        assert response.status_code == 200
        assert len(sent_messages) == 1
        match = re.search(r'\b(\d{6})\b', sent_messages[0].get_content())
        assert match is not None
        code = match.group(1)
        assert code is not None
        verified = client.post('/api/auth/verify-otp', json={
            'email': 'demo@algotrade.com',
            'code': code,
        })

        assert verified.status_code == 200
        assert verified.get_json()['user']['email'] == 'demo@algotrade.com'
        assert verified.get_json()['token']


def test_email_code_request_explains_resend_cooldown_without_sending_again():
    email = 'demo@algotrade.com'
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app.app_context():
        existing = EmailLoginCode.query.filter_by(email=email).first()
        if existing:
            db.session.delete(existing)
        db.session.add(EmailLoginCode(
            email=email,
            code_hash=app_module.generate_password_hash('123456'),
            created_at=now,
            expires_at=now + timedelta(minutes=10),
            attempts=0,
        ))
        db.session.commit()

    try:
        with patch.dict(app.config, {
            'MAIL_SERVER': 'smtp.example.com',
            'MAIL_PORT': 587,
            'MAIL_DEFAULT_SENDER': 'no-reply@example.com',
        }):
            response = app.test_client().post('/api/auth/request-otp', json={'email': email})

        assert response.status_code == 200
        assert 'Wait 60 seconds' in response.get_json()['message']
    finally:
        with app.app_context():
            EmailLoginCode.query.filter_by(email=email).delete()
            db.session.commit()


def test_email_code_sign_in_requires_smtp_configuration():
    with patch.dict(app.config, {'MAIL_SERVER': None}):
        response = app.test_client().post('/api/auth/request-otp', json={
            'email': 'demo@algotrade.com',
        })

    assert response.status_code == 503
    assert 'SMTP' in response.get_json()['message']


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
