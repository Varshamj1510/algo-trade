import math
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, session
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required

from backend.config import Config
from backend.database import db, init_db
from backend.models import Alert, BacktestResult, Holding, Order, Report, Signal, Stock, Transaction, User, WatchlistItem
from backend.routes.protection_routes import bp as protection_bp
from backend.routes.strategy_routes import bp as strategy_bp
from backend.routes.alpha_research_routes import bp as alpha_research_bp
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

CORS(app, supports_credentials=True)
jwt = JWTManager(app)
app.register_blueprint(protection_bp)
app.register_blueprint(strategy_bp)
app.register_blueprint(alpha_research_bp)
init_db(app)

with app.app_context():
    seed_demo_data()


@app.route('/')
def index():
    return redirect('/login')


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


@app.route('/signals')
def signals_page():
    return send_file(str(BASE_DIR / 'frontend' / 'signals.html'))


@app.route('/strategies')
def strategies_page():
    return send_file(str(BASE_DIR / 'frontend' / 'strategies.html'))


@app.route('/alpha-research')
def alpha_research_page():
    return send_file(str(BASE_DIR / 'frontend' / 'alpha-research.html'))


@app.route('/portfolio')
def portfolio_page():
    return send_file(str(BASE_DIR / 'frontend' / 'portfolio.html'))


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
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not full_name or not email or not username or not password:
        return jsonify({"success": False, "message": "All fields are required."}), 400
    if '@' not in email:
        return jsonify({"success": False, "message": "Enter a valid email."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400
    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({"success": False, "message": "Email or username already exists."}), 409

    user = User(full_name=full_name, email=email, username=username, plan='Premium Plan')
    user.set_password(password)
    db.session.add(user)
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
        'quote_source': 'Dashboard demo data (not live)',
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
            'Connect support must resolve the app access. AlgoTrade cannot grant this '
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


@app.route('/api/instruments/<symbol>', methods=['GET'])
@jwt_required()
def instrument_detail(symbol):
    instrument = find_demo_instrument(symbol, request.args.get('exchange', ''))
    if not instrument:
        return jsonify({"success": False, "message": "Instrument not found"}), 404
    return jsonify({'success': True, 'data': {
        **instrument,
        'quote_source': 'Dashboard demo data (not live)',
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
            'quote_source': 'Dashboard demo data (not live)',
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
    alerts = Alert.query.filter_by(user_id=int(get_jwt_identity())).all()
    return jsonify({"success": True, "data": [a.to_dict() for a in alerts]})


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
    user.full_name = data.get('full_name', user.full_name)
    user.email = data.get('email', user.email)
    user.username = data.get('username', user.username)
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
