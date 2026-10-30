import base64
import base64
import binascii
import json
import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, redirect, request, send_file, session
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from backend.config import Config
from backend.database import db, init_db
from backend.models import (
    Alert,
    AlertPushSubscription,
    AlertNotificationSettings,
    AlertWorkerHeartbeat,
    BacktestResult,
    Holding,
    Order,
    PasskeyCredential,
    PriceAlert,
    Report,
    Signal,
    Stock,
    Transaction,
    User,
    UserAuthPin,
    WatchlistItem,
    WebAuthnChallenge,
)
from backend.routes.protection_routes import bp as protection_bp
from backend.routes.strategy_routes import bp as strategy_bp
from backend.routes.alpha_research_routes import bp as alpha_research_bp
from backend.routes.paper_trading_routes import bp as paper_trading_bp
from backend.routes.candlestick_routes import bp as candlestick_chart_bp
from backend.routes.sentiment_routes import bp as sentiment_bp
from backend.routes.assistant_routes import bp as assistant_bp
from backend.routes.academy_routes import bp as academy_bp
from backend.seed import seed_demo_data
from backend.services.instrument_catalog import (
    find_demo_instrument,
    find_instrument,
    get_demo_instruments,
    get_demo_market_overview,
)
from backend.services.signal_generator import generate_demo_trade_signals
from backend.services.historical_backtest import (
    STRATEGY_NAME,
    get_historical_universe,
    run_historical_backtest,
)
from backend.services.kite_market import (
    KiteAPIError,
    KiteConfigurationError,
    build_login_url,
    exchange_request_token,
    get_brokerage_estimate,
    get_live_quotes,
    get_market_overview,
    get_stock_details,
    set_access_token,
)

BASE_DIR = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=str(BASE_DIR / 'frontend'), static_url_path='')
app.config.from_object(Config)

CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True)
jwt = JWTManager(app)
app.register_blueprint(protection_bp)
app.register_blueprint(strategy_bp)
app.register_blueprint(alpha_research_bp)
app.register_blueprint(paper_trading_bp)
app.register_blueprint(candlestick_chart_bp)
app.register_blueprint(sentiment_bp)
app.register_blueprint(assistant_bp)
app.register_blueprint(academy_bp)
init_db(app)

with app.app_context():
    seed_demo_data()


@app.route('/')
def index():
    return send_file(str(BASE_DIR / 'frontend' / 'register.html'))


@app.route('/login')
def login_page():
    return send_file(str(BASE_DIR / 'frontend' / 'login.html'))


@app.route('/register')
def register_page():
    return send_file(str(BASE_DIR / 'frontend' / 'register.html'))


@app.route('/dashboard')
def dashboard_page():
    return send_file(str(BASE_DIR / 'frontend' / 'dashboard.html'))


@app.route('/market')
def market_page():
    return send_file(str(BASE_DIR / 'frontend' / 'market.html'))


@app.route('/stocks')
def stock_directory_page():
    return send_file(str(BASE_DIR / 'frontend' / 'stock-directory.html'))


@app.route('/signals')
def signals_page():
    return send_file(str(BASE_DIR / 'frontend' / 'signals.html'))


@app.route('/sentiment')
def sentiment_page():
    return send_file(str(BASE_DIR / 'frontend' / 'sentiment.html'))


@app.route('/strategies')
def strategies_page():
    return send_file(str(BASE_DIR / 'frontend' / 'strategies.html'))


@app.route('/alpha-research')
def alpha_research_page():
    return send_file(str(BASE_DIR / 'frontend' / 'alpha-research.html'))


@app.route('/trading-academy')
def trading_academy_page():
    return send_file(str(BASE_DIR / 'frontend' / 'trading-academy.html'))


@app.route('/candlestick-chart')
def candlestick_chart_page():
    return send_file(str(BASE_DIR / 'frontend' / 'candlestick-chart.html'))


@app.route('/portfolio')
def portfolio_page():
    return send_file(str(BASE_DIR / 'frontend' / 'portfolio.html'))


@app.route('/paper-trading')
def paper_trading_page():
    return send_file(str(BASE_DIR / 'frontend' / 'paper-trading.html'))


@app.route('/backtesting')
def backtesting_page():
    return send_file(str(BASE_DIR / 'frontend' / 'backtesting.html'))


@app.route('/reports')
def reports_page():
    return send_file(str(BASE_DIR / 'frontend' / 'reports.html'))


@app.route('/watchlist')
def watchlist_page():
    return send_file(str(BASE_DIR / 'frontend' / 'watchlist.html'))


@app.route('/alerts')
def alerts_page():
    return send_file(str(BASE_DIR / 'frontend' / 'alerts.html'))


@app.route('/order-protection')
def order_protection_page():
    return send_file(str(BASE_DIR / 'frontend' / 'order-protection.html'))


@app.route('/profile')
def profile_page():
    return send_file(str(BASE_DIR / 'frontend' / 'profile.html'))


@app.route('/api/auth/register', methods=['POST'])
def register_user():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    pin = data.get('pin')

    if not email or not username or not password:
        return jsonify({"success": False, "message": "All fields are required."}), 400
    if '@' not in email:
        return jsonify({"success": False, "message": "Enter a valid email."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400
    if pin is not None and (
        not isinstance(pin, str)
        or len(pin) != 6
        or not pin.isascii()
        or not pin.isdigit()
    ):
        return jsonify({"success": False, "message": "PIN must contain exactly 6 digits."}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({
            "success": False,
            "message": "An account with this email already exists. Sign in instead.",
        }), 409
    if User.query.filter_by(username=username).first():
        return jsonify({
            "success": False,
            "message": "That username is already taken. Choose another.",
        }), 409

    user = User(full_name=username, email=email, username=username, plan='Premium Plan')
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    if pin is not None:
        db.session.add(UserAuthPin(user_id=user.id, pin_hash=generate_password_hash(pin)))
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"success": True, "token": token, "user": user.to_public_dict()}), 201


@app.route('/api/auth/login', methods=['POST'])
def login_user():
    data = request.get_json(silent=True) or {}
    identifier = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not identifier or not password:
        return jsonify({"success": False, "message": "Email or username and password are required."}), 400

    user = User.query.filter(
        db.or_(
            db.func.lower(User.email) == identifier,
            db.func.lower(User.username) == identifier,
        )
    ).first()
    if not user or not user.check_password(password):
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"success": True, "token": token, "user": user.to_public_dict()})


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _base64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _create_auth_challenge(user, ceremony, challenge):
    now = _utc_now()
    WebAuthnChallenge.query.filter(
        WebAuthnChallenge.expires_at <= now
    ).delete()
    challenge_id = secrets.token_urlsafe(32)
    db.session.add(WebAuthnChallenge(
        id=challenge_id,
        challenge=_base64url_encode(challenge),
        ceremony=ceremony,
        user_id=user.id,
        expires_at=now + timedelta(minutes=5),
    ))
    db.session.commit()
    return challenge_id


def _take_auth_challenge(challenge_id, ceremony, user_id):
    if not isinstance(challenge_id, str) or not challenge_id:
        return None
    challenge = WebAuthnChallenge.query.filter_by(
        id=challenge_id,
        ceremony=ceremony,
        user_id=user_id,
    ).first()
    if not challenge:
        return None
    db.session.delete(challenge)
    db.session.commit()
    if challenge.expires_at <= _utc_now():
        return None
    try:
        return base64url_to_bytes(challenge.challenge)
    except (ValueError, WebAuthnException):
        return None


def _auth_success(user):
    return jsonify({
        'success': True,
        'token': create_access_token(identity=str(user.id)),
        'user': user.to_public_dict(),
    })


def _expected_webauthn_rp_id():
    configured_rp_id = app.config['WEBAUTHN_RP_ID']
    request_hostname = urlsplit(request.host_url).hostname
    if configured_rp_id == 'localhost' and request_hostname and request_hostname != 'localhost':
        return request_hostname
    return configured_rp_id


def _expected_webauthn_origin():
    if app.config['WEBAUTHN_RP_ID'] == 'localhost':
        return request.host_url.rstrip('/')
    return app.config['WEBAUTHN_ORIGIN']


@app.route('/api/auth/pin/login', methods=['POST'])
def login_with_pin():
    data = request.get_json(silent=True) or {}
    raw_email = data.get('email')
    pin = data.get('pin')
    if not isinstance(raw_email, str) or not isinstance(pin, str):
        return jsonify({'success': False, 'message': 'Enter your email and 6-digit PIN.'}), 400
    email = raw_email.strip().lower()
    pin = pin.strip()
    if not email or '@' not in email or len(pin) != 6 or not pin.isascii() or not pin.isdigit():
        return jsonify({'success': False, 'message': 'Enter your email and 6-digit PIN.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'message': 'Email or PIN is incorrect.'}), 401

    auth_pin = UserAuthPin.query.filter_by(user_id=user.id).first()
    if not auth_pin:
        return jsonify({
            'success': False,
            'message': 'This account does not have a PIN yet. Sign in with your password to set one up.',
        }), 400

    now = _utc_now()
    if auth_pin.locked_until and auth_pin.locked_until > now:
        return jsonify({
            'success': False,
            'message': 'PIN sign-in is temporarily locked. Try again in 15 minutes or use another sign-in method.',
        }), 429
    if auth_pin.locked_until:
        auth_pin.locked_until = None
        auth_pin.failed_attempts = 0

    if not check_password_hash(auth_pin.pin_hash, pin):
        auth_pin.failed_attempts += 1
        if auth_pin.failed_attempts >= 5:
            auth_pin.locked_until = now + timedelta(minutes=15)
            db.session.commit()
            return jsonify({
                'success': False,
                'message': 'Too many incorrect PIN attempts. Try again in 15 minutes or use another sign-in method.',
            }), 429
        db.session.commit()
        return jsonify({'success': False, 'message': 'Email or PIN is incorrect.'}), 401

    auth_pin.failed_attempts = 0
    auth_pin.locked_until = None
    db.session.commit()
    return _auth_success(user)


@app.route('/api/auth/pin', methods=['PUT'])
@jwt_required()
def set_login_pin():
    user = db.get_or_404(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password')
    pin_value = data.get('pin')
    pin = pin_value.strip() if isinstance(pin_value, str) else ''
    if not isinstance(current_password, str) or not user.check_password(current_password):
        return jsonify({'success': False, 'message': 'Current password is incorrect.'}), 400
    if len(pin) != 6 or not pin.isascii() or not pin.isdigit():
        return jsonify({'success': False, 'message': 'PIN must contain exactly 6 digits.'}), 400

    auth_pin = UserAuthPin.query.filter_by(user_id=user.id).first()
    if auth_pin:
        auth_pin.pin_hash = generate_password_hash(pin)
        auth_pin.failed_attempts = 0
        auth_pin.locked_until = None
    else:
        db.session.add(UserAuthPin(user_id=user.id, pin_hash=generate_password_hash(pin)))
    db.session.commit()
    return jsonify({'success': True, 'message': 'Your sign-in PIN is set.'})


@app.route('/api/auth/methods', methods=['GET'])
@jwt_required()
def get_auth_methods():
    user_id = int(get_jwt_identity())
    return jsonify({
        'success': True,
        'pin_enabled': UserAuthPin.query.filter_by(user_id=user_id).first() is not None,
        'passkey_count': PasskeyCredential.query.filter_by(user_id=user_id).count(),
    })


@app.route('/api/auth/passkey/login/options', methods=['POST'])
def passkey_login_options():
    data = request.get_json(silent=True) or {}
    email_value = data.get('email')
    email = email_value.strip().lower() if isinstance(email_value, str) else ''
    if not email or '@' not in email:
        return jsonify({'success': False, 'message': 'Enter your account email first.'}), 400
    user = User.query.filter_by(email=email).first()
    credentials = (
        PasskeyCredential.query.filter_by(user_id=user.id).all()
        if user else []
    )
    if not credentials:
        return jsonify({
            'success': False,
            'message': 'No passkey is registered for that account. Use another sign-in method or set one up in Profile Settings.',
        }), 400

    options = generate_authentication_options(
        rp_id=_expected_webauthn_rp_id(),
        allow_credentials=[
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(credential.credential_id),
                transports=[
                    AuthenticatorTransport(transport)
                    for transport in json.loads(credential.transports)
                ],
            )
            for credential in credentials
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge_id = _create_auth_challenge(user, 'authentication', options.challenge)
    return jsonify({
        'success': True,
        'challenge_id': challenge_id,
        'public_key': json.loads(options_to_json(options)),
    })


@app.route('/api/auth/passkey/login/verify', methods=['POST'])
def passkey_login_verify():
    data = request.get_json(silent=True) or {}
    challenge_id = data.get('challenge_id')
    credential_data = data.get('credential')
    challenge_row = WebAuthnChallenge.query.filter_by(
        id=challenge_id,
        ceremony='authentication',
    ).first() if isinstance(challenge_id, str) else None
    challenge = _take_auth_challenge(
        challenge_id,
        'authentication',
        challenge_row.user_id if challenge_row else -1,
    )
    if not challenge or not isinstance(credential_data, dict):
        return jsonify({'success': False, 'message': 'Passkey sign-in expired. Please try again.'}), 401

    credential_id = credential_data.get('id')
    if not isinstance(credential_id, str):
        return jsonify({'success': False, 'message': 'Passkey could not be verified.'}), 401
    passkey = PasskeyCredential.query.filter_by(credential_id=credential_id).first()
    if not passkey or passkey.user_id != challenge_row.user_id:
        return jsonify({'success': False, 'message': 'Passkey could not be verified.'}), 401

    try:
        verification = verify_authentication_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=_expected_webauthn_rp_id(),
            expected_origin=_expected_webauthn_origin(),
            credential_public_key=base64url_to_bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError):
        return jsonify({'success': False, 'message': 'Passkey could not be verified. Please try again.'}), 401

    passkey.sign_count = verification.new_sign_count
    db.session.commit()
    user = db.get_or_404(User, passkey.user_id)
    return _auth_success(user)


@app.route('/api/auth/passkey/register/options', methods=['POST'])
@jwt_required()
def passkey_registration_options():
    user = db.get_or_404(User, int(get_jwt_identity()))
    existing = PasskeyCredential.query.filter_by(user_id=user.id).all()
    options = generate_registration_options(
        rp_id=_expected_webauthn_rp_id(),
        rp_name=app.config['WEBAUTHN_RP_NAME'],
        user_id=str(user.id).encode('utf-8'),
        user_name=user.email,
        user_display_name=user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(credential.credential_id),
                transports=[
                    AuthenticatorTransport(transport)
                    for transport in json.loads(credential.transports)
                ],
            )
            for credential in existing
        ],
    )
    challenge_id = _create_auth_challenge(user, 'registration', options.challenge)
    return jsonify({
        'success': True,
        'challenge_id': challenge_id,
        'public_key': json.loads(options_to_json(options)),
    })


@app.route('/api/auth/passkey/register/verify', methods=['POST'])
@jwt_required()
def passkey_registration_verify():
    user = db.get_or_404(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    challenge = _take_auth_challenge(data.get('challenge_id'), 'registration', user.id)
    credential_data = data.get('credential')
    if not challenge or not isinstance(credential_data, dict):
        return jsonify({'success': False, 'message': 'Passkey setup expired. Please try again.'}), 400

    try:
        verification = verify_registration_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=_expected_webauthn_rp_id(),
            expected_origin=_expected_webauthn_origin(),
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError):
        return jsonify({'success': False, 'message': 'The device passkey could not be verified.'}), 400

    credential_id = _base64url_encode(verification.credential_id)
    if PasskeyCredential.query.filter_by(credential_id=credential_id).first():
        return jsonify({'success': False, 'message': 'This passkey is already registered.'}), 409
    response_data = credential_data.get('response', {})
    if not isinstance(response_data, dict):
        response_data = {}
    transports = response_data.get('transports', [])
    if not isinstance(transports, list):
        transports = []
    allowed_transports = {transport.value for transport in AuthenticatorTransport}
    safe_transports = [
        transport for transport in transports
        if isinstance(transport, str) and transport in allowed_transports
    ]
    db.session.add(PasskeyCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=_base64url_encode(verification.credential_public_key),
        sign_count=verification.sign_count,
        transports=json.dumps(safe_transports),
    ))
    db.session.commit()
    return jsonify({'success': True, 'message': 'Device passkey added to your account.'})


@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def current_user():
    user = User.query.get(int(get_jwt_identity()))
    return jsonify({"success": True, "user": user.to_public_dict()})


@app.route('/api/ai-signal', methods=['POST'])
@jwt_required()
def ai_signal():
    data = request.get_json(silent=True) or {}
    symbol = (data.get('symbol') or '').strip().upper()
    exchange = (data.get('exchange') or 'NSE').strip().upper()
    timeframe = (data.get('timeframe') or '1Y').strip().upper()
    if not symbol:
        return jsonify({'success': False, 'message': 'A Kite-listed symbol is required.'}), 400
    instrument = find_instrument(symbol, exchange)
    if not instrument:
        return jsonify({'success': False, 'message': 'Instrument not found.'}), 404
    try:
        details = get_stock_details(instrument, timeframe)
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    return jsonify({'success': True, 'data': details})


@app.route('/api/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    user = User.query.get(int(get_jwt_identity()))
    return jsonify({
        'success': True,
        'user': user.to_public_dict(),
        'stats': {
            'total_portfolio_value': 245678.90,
            'today_pnl': 5678.30,
            'total_profit': 25430.50,
            'winning_trades': 68.42,
            'active_signals': 7,
        },
        'signals': generate_demo_trade_signals(get_demo_instruments()),
        'signals_source': 'dashboard-demo',
    })


@app.route('/api/market', methods=['GET'])
@jwt_required()
def market():
    available_instruments = get_demo_instruments(
        request.args.get('q', ''),
        request.args.get('exchange', ''),
    )
    instruments = available_instruments[:200]
    data = [{
        **instrument,
        'quote_source': 'Illustrative market data',
    } for instrument in instruments]
    return jsonify({
        'success': True,
        'data': data,
        'coverage': {
            'demo_instruments': len(data),
            'listed_instruments': len(instruments),
            'available_instruments': len(available_instruments),
        },
    })


@app.route('/api/market/overview', methods=['GET'])
@jwt_required()
def market_overview():
    instruments = get_demo_instruments()
    return jsonify({
        'success': True,
        'data': get_demo_market_overview(instruments),
    })


@app.route('/api/market/<section>', methods=['GET'])
@jwt_required()
def market_overview_section(section):
    sections = {'indices', 'gainers', 'losers', 'active', 'sectors'}
    if section not in sections:
        return jsonify({'success': False, 'message': 'Market overview section not found.'}), 404
    overview = get_demo_market_overview(get_demo_instruments())
    section_key = 'most_active' if section == 'active' else section
    return jsonify({'success': True, 'data': overview[section_key]})


@app.route('/kite/connect')
def kite_connect():
    state = secrets.token_urlsafe(32)
    session['kite_oauth_state'] = state
    try:
        return redirect(build_login_url(state))
    except KiteConfigurationError as error:
        return str(error), 503


@app.route('/kite/callback')
def kite_callback():
    expected_state = session.pop('kite_oauth_state', '')
    received_state = request.args.get('state', '')
    if not expected_state or not secrets.compare_digest(expected_state, received_state):
        return 'Kite authorization state did not match. Start the connection again.', 400

    if request.args.get('status', '').lower() == 'error':
        return (
            'Kite did not authorize this account for the configured Kite Connect app. '
            'If Kite reports that the user is not enabled for the app, the app owner must '
            'enable this Zerodha account in the Kite Connect developer console, or Kite '
            'Connect support must resolve the app access. AlgoMind cannot grant this '
            'permission. After access is enabled, start the connection again from Market Data.',
            403,
        )
    if request.args.get('status') == 'cancelled':
        return 'Kite login was cancelled. Start the connection again.', 400
    request_token = request.args.get('request_token', '').strip()
    if not request_token:
        return 'Kite did not return a request token. Start the connection again.', 400

    try:
        set_access_token(exchange_request_token(request_token))
    except KiteConfigurationError as error:
        return str(error), 503
    except KiteAPIError as error:
        return str(error), 502
    return redirect('/market?kite=connected')


@app.route('/api/instruments/search', methods=['GET'])
@jwt_required()
def search_instruments():
    query = request.args.get('q', '').strip()
    exchange = request.args.get('exchange', '')
    instruments = get_demo_instruments(query, exchange)
    if query:
        instruments = instruments[:10]
    return jsonify({"success": True, "data": instruments})


@app.route('/api/instruments/initial/<letter>', methods=['GET'])
@jwt_required()
def instruments_by_initial(letter):
    initial = letter.strip().upper()
    if len(initial) != 1 or not initial.isalpha() or not initial.isascii():
        return jsonify({'success': False, 'message': 'Choose a single letter from A to Z.'}), 400
    try:
        page = int(request.args.get('page', '1'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Page must be a positive whole number.'}), 400
    if page < 1:
        return jsonify({'success': False, 'message': 'Page must be a positive whole number.'}), 400

    matches = [
        instrument for instrument in get_demo_instruments()
        if str(instrument.get('name', '')).strip().upper().startswith(initial)
    ]
    matches.sort(key=lambda instrument: (
        str(instrument.get('name', '')).casefold(),
        str(instrument.get('symbol', '')).casefold(),
    ))
    page_size = 100
    page = min(page, max(1, (len(matches) + page_size - 1) // page_size))
    start = (page - 1) * page_size
    return jsonify({
        'success': True,
        'data': {
            'letter': initial,
            'page': page,
            'page_size': page_size,
            'total': len(matches),
            'instruments': matches[start:start + page_size],
        },
    })


@app.route('/api/instruments/<symbol>', methods=['GET'])
@jwt_required()
def instrument_detail(symbol):
    instrument = find_demo_instrument(symbol, request.args.get('exchange', ''))
    if not instrument:
        return jsonify({"success": False, "message": "Instrument not found"}), 404
    return jsonify({'success': True, 'data': {
        **instrument,
        'quote_source': 'Illustrative market data',
    }})


@app.route('/api/instruments/<symbol>/details', methods=['GET'])
@jwt_required()
def instrument_market_details(symbol):
    instrument = find_instrument(symbol, request.args.get('exchange', ''))
    if not instrument:
        return jsonify({'success': False, 'message': 'Instrument not found'}), 404
    try:
        data = get_stock_details(instrument, request.args.get('timeframe', '1D'))
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    return jsonify({'success': True, 'data': data})


@app.route('/api/instruments/<symbol>/brokerage', methods=['GET'])
@jwt_required()
def instrument_brokerage(symbol):
    instrument = find_instrument(symbol, request.args.get('exchange', ''))
    if not instrument:
        return jsonify({'success': False, 'message': 'Instrument not found'}), 404
    try:
        quantity = int(request.args.get('quantity', ''))
        price = float(request.args.get('price', ''))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Quantity and price must be valid numbers.'}), 400

    product = request.args.get('product', 'D').upper()
    transaction_type = request.args.get('transaction_type', 'BUY').upper()
    if quantity <= 0 or price <= 0:
        return jsonify({'success': False, 'message': 'Quantity and price must be greater than zero.'}), 400
    if product not in ('CNC', 'MIS', 'NRML'):
        return jsonify({'success': False, 'message': 'Product must be CNC (delivery), MIS (intraday), or NRML.'}), 400
    if transaction_type not in ('BUY', 'SELL'):
        return jsonify({'success': False, 'message': 'Transaction type must be BUY or SELL.'}), 400

    try:
        data = get_brokerage_estimate(instrument, quantity, product, transaction_type, price)
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    return jsonify({'success': True, 'data': data})


@app.route('/api/signals', methods=['GET'])
@jwt_required()
def get_signals():
    return jsonify({
        'success': True,
        'source': 'dashboard-demo',
        'data': generate_demo_trade_signals(get_demo_instruments()),
    })


@app.route('/api/portfolio', methods=['GET'])
@jwt_required()
def portfolio():
    user_id = int(get_jwt_identity())
    holdings = Holding.query.filter_by(user_id=user_id).all()
    holdings_source = 'account'
    if not holdings:
        demo_user = User.query.filter_by(email='demo@algotrade.com').first()
        if demo_user and demo_user.id != user_id:
            holdings = Holding.query.filter_by(user_id=demo_user.id).all()
            if holdings:
                holdings_source = 'seeded-demo'

    demo_stocks = {stock.symbol: stock for stock in Stock.query.all()}
    for holding in holdings:
        stock = demo_stocks.get(holding.symbol)
        if stock:
            holding.current_price = stock.price
    investment = sum(h.average_price * h.quantity for h in holdings)
    current_value = sum(h.current_price * h.quantity for h in holdings)
    pnl = current_value - investment
    return jsonify({
        "success": True,
        "total_value": round(current_value, 2),
        "today_pnl": round(sum(
            demo_stocks[h.symbol].price * h.quantity
            * demo_stocks[h.symbol].change / (100 + demo_stocks[h.symbol].change)
            for h in holdings if h.symbol in demo_stocks
        ), 2),
        "total_profit": round(pnl, 2),
        "overall_return": round((pnl / investment) * 100, 2) if investment else 0,
        "holdings_source": holdings_source,
        "holdings": [h.to_dict() for h in holdings],
    })


@app.route('/api/backtest/instruments', methods=['GET'])
@jwt_required()
def backtest_instruments():
    try:
        instruments = get_historical_universe()
    except OSError as error:
        return jsonify({'success': False, 'message': f'Historical CSV is unavailable: {error}'}), 503
    return jsonify({
        'success': True,
        'data_source': 'Historical CSV',
        'strategy': STRATEGY_NAME,
        'data': instruments,
    })


@app.route('/api/backtest', methods=['POST'])
@jwt_required()
def run_backtest():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400
    symbol = data.get('symbol', '')
    if not isinstance(symbol, str) or not symbol.strip():
        return jsonify({'success': False, 'message': 'Select a historical symbol.'}), 400
    try:
        initial_capital = float(data.get('initial_capital', 100000))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Initial capital must be a valid number.'}), 400
    if not math.isfinite(initial_capital) or initial_capital <= 0:
        return jsonify({'success': False, 'message': 'Initial capital must be greater than zero.'}), 400
    try:
        result_data = run_historical_backtest(symbol, initial_capital)
    except LookupError as error:
        return jsonify({'success': False, 'message': str(error)}), 404
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 422
    except OSError as error:
        return jsonify({'success': False, 'message': f'Historical CSV is unavailable: {error}'}), 503

    result = BacktestResult(
        strategy_name=result_data['strategy_name'],
        symbol=result_data['symbol'],
        initial_capital=result_data['initial_capital'],
        final_value=result_data['final_value'],
        total_return=result_data['total_return'],
        win_rate=result_data['win_rate'],
        total_trades=result_data['total_trades'],
        max_drawdown=result_data['max_drawdown'],
        profit_factor=result_data['profit_factor'],
    )
    db.session.add(result)
    db.session.commit()
    return jsonify({
        'success': True,
        'data': {**result.to_dict(), **{
            key: result_data[key]
            for key in ('start_date', 'end_date', 'observations', 'data_source')
        }},
    })


@app.route('/api/backtest/history', methods=['GET'])
@jwt_required()
def backtest_history():
    results = BacktestResult.query.order_by(BacktestResult.id.desc()).all()
    return jsonify({"success": True, "data": [r.to_dict() for r in results]})


@app.route('/api/reports', methods=['GET'])
@jwt_required()
def reports():
    reports_list = Report.query.order_by(Report.id.desc()).all()
    return jsonify({"success": True, "data": [r.to_dict() for r in reports_list]})


@app.route('/api/watchlist', methods=['GET'])
@jwt_required()
def get_watchlist():
    items = WatchlistItem.query.filter_by(user_id=int(get_jwt_identity())).all()
    data = []
    for item in items:
        exchange, separator, symbol = item.symbol.partition(':')
        if not separator:
            symbol, exchange = exchange, ''
        instrument = find_demo_instrument(symbol, exchange)
        if not instrument:
            continue
        data.append({
            **instrument,
            'watchlist_id': item.symbol,
            'quote_source': 'Illustrative market data',
        })
    return jsonify({"success": True, "data": data})


@app.route('/api/watchlist', methods=['POST'])
@jwt_required()
def add_watchlist():
    data = request.get_json(silent=True) or {}
    symbol = (data.get('symbol') or '').strip().upper()
    exchange = (data.get('exchange') or '').strip().upper()
    if ':' in symbol and not exchange:
        exchange, symbol = symbol.split(':', 1)
    if not symbol:
        return jsonify({"success": False, "message": "Symbol required"}), 400
    instrument = find_demo_instrument(symbol, exchange)
    if not instrument:
        return jsonify({"success": False, "message": "Instrument not found"}), 404
    exchange = instrument['exchange']
    watchlist_key = f'{exchange}:{symbol}'
    user_id = int(get_jwt_identity())
    existing = WatchlistItem.query.filter_by(user_id=user_id).all()
    if any(item.symbol == watchlist_key or item.symbol == symbol and exchange == 'NSE' for item in existing):
        return jsonify({"success": False, "message": "Already in watchlist"}), 409
    item = WatchlistItem(user_id=user_id, symbol=watchlist_key)
    db.session.add(item)
    db.session.commit()
    return jsonify({"success": True, "data": {**instrument, 'watchlist_id': watchlist_key}}), 201


@app.route('/api/watchlist/<symbol>', methods=['DELETE'])
@jwt_required()
def delete_watchlist(symbol):
    exchange = request.args.get('exchange', '').strip().upper()
    symbol = symbol.strip().upper()
    if ':' in symbol and not exchange:
        exchange, symbol = symbol.split(':', 1)
    key = f'{exchange}:{symbol}' if exchange else symbol
    items = WatchlistItem.query.filter_by(user_id=int(get_jwt_identity())).all()
    item = next((entry for entry in items if entry.symbol == key
                 or entry.symbol == symbol and exchange in ('', 'NSE')), None)
    if not item:
        return jsonify({"success": False, "message": "Watchlist item not found"}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"success": True, "message": "Removed from watchlist"})


@app.route('/api/orders', methods=['GET'])
@jwt_required()
def get_orders():
    user_id = int(get_jwt_identity())
    status_filter = request.args.get('status', '').strip().upper()
    query = Order.query.filter_by(user_id=user_id)
    if status_filter:
        normalized = status_filter.replace('-', '_')
        query = query.filter_by(status=normalized)
    orders = query.order_by(Order.created_at.desc()).all()
    return jsonify({"success": True, "data": [order.to_dict() for order in orders]})


@app.route('/api/orders', methods=['POST'])
@jwt_required()
def create_order():
    data = request.get_json(silent=True) or {}
    side = (data.get('side') or '').strip().upper()
    order_type = (data.get('order_type') or '').strip().upper()
    symbol = (data.get('symbol') or '').strip().upper()
    exchange = (data.get('exchange') or 'NSE').strip().upper()
    trigger_price = data.get('trigger_price')
    try:
        quantity = float(data.get('quantity', 0) or 0)
        price = float(data.get('price', 0) or 0)
        trigger_price = float(trigger_price) if trigger_price not in (None, '') else None
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Quantity and order prices must be valid numbers."}), 400

    if side not in {'BUY', 'SELL'}:
        return jsonify({"success": False, "message": "Order side must be BUY or SELL."}), 400
    if order_type not in {'MARKET', 'LIMIT', 'STOP_LOSS', 'STOP_LOSS_MARKET'}:
        return jsonify({"success": False, "message": "Unsupported order type."}), 400
    if not symbol:
        return jsonify({"success": False, "message": "Symbol is required."}), 400
    if not math.isfinite(quantity) or quantity <= 0:
        return jsonify({"success": False, "message": "Quantity must be greater than zero."}), 400
    if not math.isfinite(price) or price < 0:
        return jsonify({"success": False, "message": "Price must be a valid non-negative number."}), 400
    if trigger_price is not None and (not math.isfinite(trigger_price) or trigger_price <= 0):
        return jsonify({"success": False, "message": "Trigger price must be greater than zero."}), 400
    if order_type in {'LIMIT', 'STOP_LOSS'} and price <= 0:
        return jsonify({"success": False, "message": "Limit and stop-loss orders require a valid price."}), 400
    if order_type in {'STOP_LOSS', 'STOP_LOSS_MARKET'} and trigger_price is None:
        return jsonify({"success": False, "message": "Stop-loss orders require a trigger price."}), 400

    order = Order(
        user_id=int(get_jwt_identity()),
        symbol=symbol,
        exchange=exchange,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        trigger_price=trigger_price,
        status='OPEN',
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({"success": True, "message": "Order placed successfully.", "data": order.to_dict()}), 201


@app.route('/api/orders/<int:order_id>/complete', methods=['POST'])
@jwt_required()
def complete_order(order_id):
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({"success": False, "message": "Order not found."}), 404
    if order.status in {'COMPLETED', 'CANCELLED'}:
        return jsonify({"success": False, "message": "Order is already processed."}), 400

    order.status = 'COMPLETED'
    order.updated_at = datetime.utcnow()
    db.session.add(Transaction(
        user_id=order.user_id,
        symbol=order.symbol,
        type=order.side,
        quantity=order.quantity,
        price=order.price or order.trigger_price or 0.0,
    ))
    db.session.commit()
    return jsonify({"success": True, "message": "Order completed.", "data": order.to_dict()})


@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
@jwt_required()
def cancel_order(order_id):
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({"success": False, "message": "Order not found."}), 404
    if order.status == 'CANCELLED':
        return jsonify({"success": False, "message": "Order is already cancelled."}), 400
    order.status = 'CANCELLED'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "message": "Order cancelled.", "data": order.to_dict()})


@app.route('/api/alerts', methods=['GET'])
@jwt_required()
def get_alerts():
    user_id = int(get_jwt_identity())
    alerts = Alert.query.filter_by(user_id=user_id).order_by(Alert.created_at.desc()).all()
    price_alerts = PriceAlert.query.filter_by(user_id=user_id).order_by(PriceAlert.created_at.desc()).all()
    settings = AlertNotificationSettings.query.filter_by(user_id=user_id).first()
    return jsonify({
        "success": True,
        "data": [alert.to_dict() for alert in alerts],
        "price_alerts": [alert.to_dict() for alert in price_alerts],
        "settings": settings.to_dict() if settings else {
            'enabled': False,
            'quiet_hours_enabled': False,
            'quiet_start': '22:00',
            'quiet_end': '08:00',
            'timezone': 'UTC',
        },
        "delivery": {
            'method': 'browser_notification',
            'requires_alerts_page_open': False,
            'push_configured': bool(app.config['VAPID_PUBLIC_KEY'] and app.config['VAPID_PRIVATE_KEY']),
            'background_worker_online': _price_alert_worker_online(),
            'market_data': 'Kite Connect quotes only',
        },
    })


def _price_alert_worker_online():
    heartbeat = AlertWorkerHeartbeat.query.filter_by(name='price-alerts').first()
    if not heartbeat or not heartbeat.last_seen_at:
        return False
    age_seconds = (
        datetime.now(timezone.utc).replace(tzinfo=None) - heartbeat.last_seen_at
    ).total_seconds()
    return 0 <= age_seconds < 90


def _is_supported_push_endpoint(endpoint):
    try:
        parsed_endpoint = urlsplit(endpoint)
        port = parsed_endpoint.port
    except ValueError:
        return False
    if (
        parsed_endpoint.scheme != 'https'
        or not parsed_endpoint.hostname
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or port not in (None, 443)
    ):
        return False
    host = parsed_endpoint.hostname.lower().rstrip('.')
    return host in {
        'fcm.googleapis.com',
        'updates.push.services.mozilla.com',
        'push.services.mozilla.com',
        'web.push.apple.com',
    } or host.endswith('.notify.windows.com')


def _decode_push_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        return None
    try:
        return base64.b64decode(
            value + ('=' * (-len(value) % 4)),
            altchars=b'-_',
            validate=True,
        )
    except (binascii.Error, ValueError):
        return None


@app.route('/api/alerts', methods=['POST'])
@jwt_required()
def create_alert():
    data = request.get_json(silent=True) or {}
    alert = Alert(
        user_id=int(get_jwt_identity()),
        title=data.get('title', 'New Alert'),
        description=data.get('description', ''),
        type=data.get('type', 'Price Alert'),
        status=data.get('status', 'Active'),
    )
    db.session.add(alert)
    db.session.commit()
    return jsonify({"success": True, "data": alert.to_dict()}), 201


@app.route('/api/price-alerts', methods=['POST'])
@jwt_required()
def create_price_alert():
    data = request.get_json(silent=True) or {}
    symbol = data.get('symbol')
    exchange = data.get('exchange', 'NSE')
    direction = data.get('direction')
    target_value = data.get('target_price')
    if not all(isinstance(value, str) for value in (symbol, exchange, direction)):
        return jsonify({'success': False, 'message': 'Choose a stock, direction, and target price.'}), 400
    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    direction = direction.strip().lower()
    try:
        target_price = float(target_value)
    except (TypeError, ValueError):
        target_price = 0
    if not math.isfinite(target_price) or target_price <= 0:
        return jsonify({'success': False, 'message': 'Enter a target price greater than zero.'}), 400
    if direction not in {'above', 'below'}:
        return jsonify({'success': False, 'message': 'Choose whether to alert above or below the target.'}), 400
    instrument = find_demo_instrument(symbol, exchange)
    if not instrument:
        return jsonify({'success': False, 'message': 'That stock is not available in the instrument list.'}), 404

    user_id = int(get_jwt_identity())
    existing = PriceAlert.query.filter_by(
        user_id=user_id,
        symbol=symbol,
        exchange=exchange,
        direction=direction,
        target_price=target_price,
    ).first()
    if existing:
        return jsonify({
            'success': False,
            'message': 'An alert for this stock and price condition already exists. Edit or reset the saved alert instead.',
        }), 409

    alert = PriceAlert(
        user_id=user_id,
        symbol=symbol,
        exchange=exchange,
        name=instrument['name'],
        target_price=target_price,
        direction=direction,
    )
    db.session.add(alert)
    db.session.commit()
    return jsonify({'success': True, 'data': alert.to_dict()}), 201


@app.route('/api/price-alerts/<int:alert_id>', methods=['PUT'])
@jwt_required()
def update_price_alert(alert_id):
    user_id = int(get_jwt_identity())
    alert = PriceAlert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return jsonify({'success': False, 'message': 'Price alert not found.'}), 404
    data = request.get_json(silent=True) or {}
    changed_condition = False
    if 'target_price' in data:
        try:
            target_price = float(data['target_price'])
        except (TypeError, ValueError):
            target_price = 0
        if not math.isfinite(target_price) or target_price <= 0:
            return jsonify({'success': False, 'message': 'Enter a target price greater than zero.'}), 400
        changed_condition = changed_condition or target_price != alert.target_price
        alert.target_price = target_price
    if 'direction' in data:
        direction = data['direction']
        if direction not in {'above', 'below'}:
            return jsonify({'success': False, 'message': 'Choose whether to alert above or below the target.'}), 400
        changed_condition = changed_condition or direction != alert.direction
        alert.direction = direction
    if 'enabled' in data:
        if not isinstance(data['enabled'], bool):
            return jsonify({'success': False, 'message': 'Alert enabled must be true or false.'}), 400
        alert.enabled = data['enabled']
    if changed_condition:
        duplicate = PriceAlert.query.filter(
            PriceAlert.user_id == user_id,
            PriceAlert.symbol == alert.symbol,
            PriceAlert.exchange == alert.exchange,
            PriceAlert.direction == alert.direction,
            PriceAlert.target_price == alert.target_price,
            PriceAlert.id != alert.id,
        ).first()
        if duplicate:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'An alert for this stock and price condition already exists. Edit or reset the saved alert instead.',
            }), 409
        alert.triggered_at = None
        alert.triggered_price = None
        alert.notification_delivered_at = None
        alert.enabled = True
    db.session.commit()
    return jsonify({'success': True, 'data': alert.to_dict()})


@app.route('/api/price-alerts/<int:alert_id>', methods=['DELETE'])
@jwt_required()
def delete_price_alert(alert_id):
    alert = PriceAlert.query.filter_by(
        id=alert_id,
        user_id=int(get_jwt_identity()),
    ).first()
    if not alert:
        return jsonify({'success': False, 'message': 'Price alert not found.'}), 404
    db.session.delete(alert)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Price alert deleted.'})


@app.route('/api/price-alerts/<int:alert_id>/reset', methods=['POST'])
@jwt_required()
def reset_price_alert(alert_id):
    alert = PriceAlert.query.filter_by(
        id=alert_id,
        user_id=int(get_jwt_identity()),
    ).first()
    if not alert:
        return jsonify({'success': False, 'message': 'Price alert not found.'}), 404
    if not alert.triggered_at:
        return jsonify({'success': False, 'message': 'This alert has not triggered.'}), 400
    try:
        quotes = get_live_quotes([{'symbol': alert.symbol, 'exchange': alert.exchange}])
    except (KiteConfigurationError, KiteAPIError) as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    quote = quotes.get((alert.exchange, alert.symbol))
    try:
        price = float(quote.get('price')) if quote else 0
    except (TypeError, ValueError):
        price = 0
    if not math.isfinite(price) or price <= 0:
        return jsonify({'success': False, 'message': 'A current quote is not available; the alert cannot be reset yet.'}), 503
    condition_met = price >= alert.target_price if alert.direction == 'above' else price <= alert.target_price
    if condition_met:
        return jsonify({
            'success': False,
            'message': 'The current price still meets this alert condition. Reset it after the price moves back across the target.',
        }), 409
    alert.triggered_at = None
    alert.triggered_price = None
    alert.notification_delivered_at = None
    alert.enabled = True
    db.session.commit()
    return jsonify({'success': True, 'data': alert.to_dict()})


@app.route('/api/alerts/settings', methods=['GET'])
@jwt_required()
def get_alert_settings():
    settings = AlertNotificationSettings.query.filter_by(
        user_id=int(get_jwt_identity()),
    ).first()
    return jsonify({'success': True, 'data': settings.to_dict() if settings else {
        'enabled': False,
        'quiet_hours_enabled': False,
        'quiet_start': '22:00',
        'quiet_end': '08:00',
        'timezone': 'UTC',
    }})


@app.route('/api/alerts/settings', methods=['PUT'])
@jwt_required()
def update_alert_settings():
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled', False)
    quiet_hours_enabled = data.get('quiet_hours_enabled', False)
    quiet_start = data.get('quiet_start', '22:00')
    quiet_end = data.get('quiet_end', '08:00')
    timezone_name = data.get('timezone', 'UTC')
    if not isinstance(enabled, bool) or not isinstance(quiet_hours_enabled, bool):
        return jsonify({'success': False, 'message': 'Notification settings must be enabled or disabled.'}), 400
    time_pattern = re.compile(r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    if not isinstance(quiet_start, str) or not time_pattern.fullmatch(quiet_start):
        return jsonify({'success': False, 'message': 'Enter a valid quiet-hours start time.'}), 400
    if not isinstance(quiet_end, str) or not time_pattern.fullmatch(quiet_end):
        return jsonify({'success': False, 'message': 'Enter a valid quiet-hours end time.'}), 400
    if quiet_hours_enabled and quiet_start == quiet_end:
        return jsonify({'success': False, 'message': 'Quiet-hours start and end times must be different.'}), 400
    if not isinstance(timezone_name, str) or not timezone_name or len(timezone_name) > 64:
        return jsonify({'success': False, 'message': 'Choose a valid timezone for quiet hours.'}), 400
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return jsonify({'success': False, 'message': 'Choose a valid timezone for quiet hours.'}), 400
    user_id = int(get_jwt_identity())
    settings = AlertNotificationSettings.query.filter_by(user_id=user_id).first()
    if not settings:
        settings = AlertNotificationSettings(user_id=user_id)
        db.session.add(settings)
    settings.enabled = enabled
    settings.quiet_hours_enabled = quiet_hours_enabled
    settings.quiet_start = quiet_start
    settings.quiet_end = quiet_end
    settings.timezone = timezone_name
    db.session.commit()
    return jsonify({'success': True, 'data': settings.to_dict()})


@app.route('/api/alerts/push/public-key', methods=['GET'])
@jwt_required()
def get_alert_push_public_key():
    public_key = app.config['VAPID_PUBLIC_KEY']
    if not public_key:
        return jsonify({
            'success': False,
            'message': 'Background browser notifications are not configured on this server.',
        }), 503
    return jsonify({'success': True, 'data': {'public_key': public_key}})


@app.route('/api/alerts/push/subscribe', methods=['POST'])
@jwt_required()
def subscribe_alert_push():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys')
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 1024:
        return jsonify({'success': False, 'message': 'A valid browser push endpoint is required.'}), 400
    if not _is_supported_push_endpoint(endpoint):
        return jsonify({'success': False, 'message': 'The browser push service endpoint is not supported.'}), 400
    if not isinstance(keys, dict):
        return jsonify({'success': False, 'message': 'Browser push encryption keys are required.'}), 400
    p256dh = keys.get('p256dh')
    auth_key = keys.get('auth')
    decoded_p256dh = _decode_push_key(p256dh)
    decoded_auth_key = _decode_push_key(auth_key)
    if (
        decoded_p256dh is None or len(decoded_p256dh) != 65 or decoded_p256dh[0] != 4
        or decoded_auth_key is None or len(decoded_auth_key) != 16
    ):
        return jsonify({'success': False, 'message': 'Browser push encryption keys are invalid.'}), 400
    user_id = int(get_jwt_identity())
    subscription = AlertPushSubscription.query.filter_by(
        user_id=user_id,
        endpoint=endpoint,
    ).first()
    if subscription is None:
        subscription = AlertPushSubscription(user_id=user_id, endpoint=endpoint)
        db.session.add(subscription)
    subscription.p256dh = p256dh
    subscription.auth = auth_key
    db.session.commit()
    return jsonify({'success': True, 'message': 'This browser is ready for background price alerts.'})


@app.route('/api/alerts/push/subscribe', methods=['DELETE'])
@jwt_required()
def unsubscribe_alert_push():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if not isinstance(endpoint, str) or not endpoint:
        return jsonify({'success': False, 'message': 'The browser push endpoint is required.'}), 400
    subscription = AlertPushSubscription.query.filter_by(
        user_id=int(get_jwt_identity()),
        endpoint=endpoint,
    ).first()
    if subscription:
        db.session.delete(subscription)
        db.session.commit()
    return jsonify({'success': True, 'message': 'Browser push subscription removed.'})


@app.route('/api/alerts/check', methods=['POST'])
@jwt_required()
def check_price_alerts():
    user_id = int(get_jwt_identity())
    settings = AlertNotificationSettings.query.filter_by(user_id=user_id).first()
    enabled = bool(settings and settings.enabled)
    alerts = PriceAlert.query.filter_by(user_id=user_id, enabled=True).all()
    if not enabled:
        return jsonify({
            'success': True,
            'data': {
                'monitoring': False,
                'quote_source': None,
                'quotes': {},
                'pending_notifications': [],
                'push_configured': bool(app.config['VAPID_PUBLIC_KEY'] and app.config['VAPID_PRIVATE_KEY']),
                'background_worker_online': _price_alert_worker_online(),
            },
        })
    if not alerts:
        return jsonify({
            'success': True,
            'data': {
                'monitoring': True,
                'quote_source': 'Kite Connect quotes',
                'quotes': {},
                'pending_notifications': [],
                'push_configured': bool(app.config['VAPID_PUBLIC_KEY'] and app.config['VAPID_PRIVATE_KEY']),
                'background_worker_online': _price_alert_worker_online(),
            },
        })
    instruments = [{'symbol': alert.symbol, 'exchange': alert.exchange} for alert in alerts]
    try:
        quotes = get_live_quotes(instruments)
    except (KiteConfigurationError, KiteAPIError) as error:
        return jsonify({'success': False, 'message': str(error), 'market_data_available': False}), 503

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    current_prices = {}
    for alert in alerts:
        quote = quotes.get((alert.exchange, alert.symbol))
        try:
            price = float(quote.get('price')) if quote else 0
        except (TypeError, ValueError):
            price = 0
        if not math.isfinite(price) or price <= 0:
            continue
        current_prices[f'{alert.exchange}:{alert.symbol}'] = price
        condition_met = price >= alert.target_price if alert.direction == 'above' else price <= alert.target_price
        if condition_met and alert.triggered_at is None:
            alert.triggered_at = now
            alert.triggered_price = price
    db.session.commit()

    pending = PriceAlert.query.filter(
        PriceAlert.user_id == user_id,
        PriceAlert.enabled.is_(True),
        PriceAlert.triggered_at.isnot(None),
        PriceAlert.notification_delivered_at.is_(None),
    ).all()
    return jsonify({
        'success': True,
        'data': {
            'monitoring': True,
            'quote_source': 'Kite Connect quotes',
            'quotes': current_prices,
            'push_configured': bool(app.config['VAPID_PUBLIC_KEY'] and app.config['VAPID_PRIVATE_KEY']),
            'background_worker_online': _price_alert_worker_online(),
            'pending_notifications': [{
                **alert.to_dict(),
                'notification_text': (
                    f"{alert.name} ({alert.symbol}) reached ₹{alert.triggered_price:,.2f}; "
                    f"your {alert.direction} ₹{alert.target_price:,.2f} price alert was met."
                ),
            } for alert in pending],
        },
    })


@app.route('/api/alerts/acknowledge', methods=['POST'])
@jwt_required()
def acknowledge_price_alert_notifications():
    data = request.get_json(silent=True) or {}
    alert_ids = data.get('alert_ids')
    if not isinstance(alert_ids, list) or any(
        not isinstance(alert_id, int) or isinstance(alert_id, bool) for alert_id in alert_ids
    ):
        return jsonify({'success': False, 'message': 'Alert IDs must be a list of whole numbers.'}), 400
    alerts = PriceAlert.query.filter(
        PriceAlert.user_id == int(get_jwt_identity()),
        PriceAlert.id.in_(alert_ids),
        PriceAlert.triggered_at.isnot(None),
        PriceAlert.notification_delivered_at.is_(None),
    ).all()
    delivered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for alert in alerts:
        alert.notification_delivered_at = delivered_at
    db.session.commit()
    return jsonify({'success': True, 'data': {'acknowledged': len(alerts)}})


@app.route('/api/profile', methods=['GET'])
@jwt_required()
def profile():
    user = User.query.get_or_404(int(get_jwt_identity()))
    return jsonify({"success": True, "data": user.to_public_dict()})


@app.route('/api/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    user = User.query.get_or_404(int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    user.email = data.get('email', user.email)
    user.username = data.get('username', user.username)
    user.full_name = user.username
    db.session.commit()
    return jsonify({"success": True, "user": user.to_public_dict()})


@app.route('/api/profile/change-password', methods=['POST'])
@jwt_required()
def change_password():
    user = User.query.get_or_404(int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    current = data.get('current_password')
    new_password = data.get('new_password')
    if not user.check_password(current or ''):
        return jsonify({"success": False, "message": "Current password is incorrect."}), 400
    if len(new_password or '') < 6:
        return jsonify({"success": False, "message": "New password must be at least 6 characters."}), 400
    user.set_password(new_password)
    db.session.commit()
    return jsonify({"success": True, "message": "Password updated"})


@app.errorhandler(404)
def e404(_):
    return jsonify({"success": False, "message": "Not found"}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
