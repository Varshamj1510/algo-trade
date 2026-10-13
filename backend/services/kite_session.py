import getpass
import hashlib
import json
import os
import secrets
import stat
import subprocess
import tempfile
import threading

import requests
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

try:
    from kiteconnect import KiteConnect
    from kiteconnect.exceptions import KiteException, TokenException
except ModuleNotFoundError:  # pragma: no cover - optional SDK in lightweight environments
    class KiteException(Exception):
        pass

    class TokenException(Exception):
        pass

    class KiteConnect:
        def __init__(self, api_key):
            self.api_key = api_key
            self.access_token = None

        def login_url(self):
            return f'https://kite.zerodha.com/connect/login?api_key={self.api_key}'

        def set_access_token(self, token):
            self.access_token = token

        def generate_session(self, request_token, api_secret):
            checksum = hashlib.sha256(
                f'{self.api_key}{request_token}{api_secret}'.encode('utf-8')
            ).hexdigest()
            response = requests.post(
                'https://api.kite.trade/session/token',
                headers={'X-Kite-Version': '3'},
                data={
                    'api_key': self.api_key,
                    'request_token': request_token,
                    'checksum': checksum,
                },
                timeout=15,
            )
            payload = response.json()
            if response.status_code != 200 or payload.get('status') != 'success':
                raise KiteException(payload.get('message') or 'Kite authorization failed.')
            data = payload.get('data') or {}
            access_token = data.get('access_token')
            if not access_token:
                raise KiteException('Kite returned an incomplete authorization response.')
            return {'access_token': access_token, 'user_id': data.get('user_id', 'demo-user')}


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / '.env')
SESSION_FILE = PROJECT_ROOT / 'backend' / 'data' / 'kite_session.json'
LOGIN_STATE_TTL_SECONDS = 600

_lock = threading.RLock()
_pending_states = {}


class KiteSessionError(Exception):
    pass


def _api_key():
    value = os.getenv('KITE_API_KEY', '').strip()
    if not value:
        raise KiteSessionError('Kite API key is not configured on the backend.')
    return value


def _api_secret():
    value = os.getenv('KITE_API_SECRET', '').strip()
    if not value:
        raise KiteSessionError('Kite API secret is not configured on the backend.')
    return value


def _apply_private_permissions(path):
    if os.name == 'nt':
        account = os.environ.get('USERDOMAIN', '') + '\\' + getpass.getuser()
        command = [
            'icacls.exe', str(path), '/inheritance:r', '/grant:r',
            f'{account}:(F)', 'SYSTEM:(F)',
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except OSError as error:
            raise KiteSessionError('Could not protect the local Kite session file.') from error
        if result.returncode:
            raise KiteSessionError('Could not protect the local Kite session file.')
    else:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError as error:
            raise KiteSessionError('Could not protect the local Kite session file.') from error


def load_access_token():
    token = os.getenv('KITE_ACCESS_TOKEN', '').strip()
    if token:
        return token

    if not SESSION_FILE.exists():
        return None

    with _lock:
        try:
            with SESSION_FILE.open('r', encoding='utf-8') as session_file:
                session = json.load(session_file)
        except (OSError, json.JSONDecodeError) as error:
            raise KiteSessionError(
                'The saved Kite session file cannot be read. Reauthorize Kite after resolving the file issue.'
            ) from error

    access_token = session.get('access_token') if isinstance(session, dict) else None
    if not isinstance(access_token, str) or not access_token.strip():
        raise KiteSessionError(
            'The saved Kite session file is invalid. Remove it and authorize Kite again.'
        )
    return access_token.strip()


def save_access_token(access_token):
    if not isinstance(access_token, str) or not access_token.strip():
        raise KiteSessionError('Kite did not provide a valid access token.')

    os.environ['KITE_ACCESS_TOKEN'] = access_token.strip()
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    with _lock:
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=SESSION_FILE.parent,
                prefix='.kite-session-', suffix='.tmp', delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
            _apply_private_permissions(temporary_path)
            with temporary_path.open('w', encoding='utf-8') as temporary_file:
                json.dump({
                    'access_token': access_token.strip(),
                    'saved_at': datetime.now(timezone.utc).isoformat(),
                }, temporary_file)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, SESSION_FILE)
        except KiteSessionError:
            raise
        except OSError as error:
            raise KiteSessionError('Could not save the protected Kite session file.') from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass


def clear_access_token():
    os.environ.pop('KITE_ACCESS_TOKEN', None)
    with _lock:
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except OSError as error:
            raise KiteSessionError('Could not remove the saved Kite session file.') from error


def create_kite_client(access_token=None):
    client = KiteConnect(api_key=_api_key())
    token = access_token or load_access_token()
    if not token:
        raise KiteSessionError('Kite is not connected. Select Connect to Zerodha to authorize.')
    client.set_access_token(token)
    return client


def get_stream_credentials():
    token = load_access_token()
    if not token:
        raise KiteSessionError('Kite is not connected. Select Connect to Zerodha to authorize.')
    return _api_key(), token


def create_login_url(state):
    client = KiteConnect(api_key=_api_key())
    parts = urlsplit(client.login_url())
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query['redirect_params'] = f'state={state}'
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def create_login_state():
    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).timestamp()
    with _lock:
        expired = [
            key for key, created_at in _pending_states.items()
            if now - created_at > LOGIN_STATE_TTL_SECONDS
        ]
        for key in expired:
            _pending_states.pop(key, None)
        _pending_states[state] = now
    return state


def consume_login_state(state):
    now = datetime.now(timezone.utc).timestamp()
    with _lock:
        created_at = _pending_states.pop(state, None)
    return created_at is not None and now - created_at <= LOGIN_STATE_TTL_SECONDS


def exchange_request_token(request_token):
    if not isinstance(request_token, str) or not request_token.strip():
        raise KiteSessionError('Kite did not return a request token.')
    client = KiteConnect(api_key=_api_key())
    try:
        session = client.generate_session(request_token.strip(), api_secret=_api_secret())
    except TokenException as error:
        raise KiteSessionError('Kite rejected the one-time login token. Start authorization again.') from error
    except KiteException as error:
        raise KiteSessionError('Kite could not complete authorization. Check app access and try again.') from error

    access_token = session.get('access_token') if isinstance(session, dict) else None
    user_id = session.get('user_id') if isinstance(session, dict) else None
    if not access_token or not user_id:
        raise KiteSessionError('Kite returned an incomplete authorization response.')
    save_access_token(access_token)
    return access_token


def validate_saved_session():
    token = load_access_token()
    if not token:
        return False
    client = create_kite_client(token)
    try:
        client.profile()
    except TokenException as error:
        clear_access_token()
        raise KiteSessionError('Kite session expired. Reauthorize to continue.') from error
    except KiteException as error:
        raise KiteSessionError('Kite could not validate the saved session. Check Kite access and retry.') from error
    return True
