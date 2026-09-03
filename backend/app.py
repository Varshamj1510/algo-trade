import os
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required

from backend.config import Config
from backend.database import db, init_db
from backend.models import Alert, BacktestResult, Holding, Report, Signal, Stock, StrategyModel, User, WatchlistItem
from backend.seed import seed_demo_data
from backend.services.signal_generator import generate_trade_decision

BASE_DIR = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=str(BASE_DIR / 'frontend'), static_url_path='')
app.config.from_object(Config)

CORS(app, supports_credentials=True)
jwt = JWTManager(app)
init_db(app)

with app.app_context():
    seed_demo_data()


@app.route('/')
def index():
    return send_file(str(BASE_DIR / 'frontend' / 'index.html'))


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
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
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
    symbol = (data.get('symbol') or 'RELIANCE').upper()
    current_price = float(data.get('price', 0) or 0)
    rsi_value = float(data.get('rsi', 50) or 50)
    macd_value = float(data.get('macd', 0) or 0)
    support_level = float(data.get('support', current_price) or current_price)
    resistance_level = float(data.get('resistance', current_price) or current_price)

    result = generate_trade_decision(symbol, current_price, rsi_value, macd_value, support_level, resistance_level)
    return jsonify({"success": True, "data": result})


@app.route('/api/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    user = User.query.get(int(get_jwt_identity()))
    signals = Signal.query.order_by(Signal.id.desc()).limit(5).all()
    verdict_signal = signals[0].signal if signals else 'HOLD'
    verdict_reason = (
        'BUY signal from moving average crossover, MACD confirmation, and strong relative momentum across the market session.'
        if verdict_signal == 'BUY'
        else 'SELL signal from weak momentum, price falling below VWAP, and bearish trend confirmation across indicators.'
        if verdict_signal == 'SELL'
        else 'HOLD signal because the indicator mix is mixed; trend strength is weak and the market is in a neutral range.'
    )
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
        'signals': [signal.to_dict() for signal in signals],
        'ai_verdict': {
            'signal': verdict_signal,
            'symbol': signals[0].symbol if signals else 'RELIANCE',
            'confidence': signals[0].confidence if signals else 84,
            'reason': verdict_reason,
        },
    })


@app.route('/api/market', methods=['GET'])
@jwt_required()
def market():
    stocks = Stock.query.order_by(Stock.symbol.asc()).all()
    return jsonify({"success": True, "data": [stock.to_dict() for stock in stocks]})


@app.route('/api/signals', methods=['GET'])
@jwt_required()
def get_signals():
    return jsonify({"success": True, "data": [signal.to_dict() for signal in Signal.query.order_by(Signal.id.desc()).all()]})


@app.route('/api/portfolio', methods=['GET'])
@jwt_required()
def portfolio():
    holdings = Holding.query.all()
    investment = sum(h.average_price * h.quantity for h in holdings)
    current_value = sum(h.current_price * h.quantity for h in holdings)
    pnl = current_value - investment
    return jsonify({
        "success": True,
        "total_value": round(current_value, 2),
        "today_pnl": 5678.30,
        "total_profit": round(pnl, 2),
        "overall_return": round((pnl / investment) * 100, 2) if investment else 0,
        "holdings": [h.to_dict() for h in holdings],
    })


@app.route('/api/strategies', methods=['GET'])
@jwt_required()
def get_strategies():
    return jsonify({"success": True, "data": [s.to_dict() for s in StrategyModel.query.order_by(StrategyModel.id.asc()).all()]})


@app.route('/api/strategies', methods=['POST'])
@jwt_required()
def create_strategy():
    data = request.get_json(silent=True) or {}
    strategy = StrategyModel(
        name=data.get('name', 'New Strategy'),
        description=data.get('description', 'Strategy description'),
        status='Active',
        win_rate=float(data.get('win_rate', 0.0)),
        total_trades=int(data.get('total_trades', 0)),
        user_id=int(get_jwt_identity()),
    )
    db.session.add(strategy)
    db.session.commit()
    return jsonify({"success": True, "data": strategy.to_dict()}), 201


@app.route('/api/backtest', methods=['POST'])
@jwt_required()
def run_backtest():
    data = request.get_json(silent=True) or {}
    strategy = data.get('strategy', 'Momentum')
    symbol = (data.get('symbol') or 'RELIANCE').upper()
    initial_capital = float(data.get('initial_capital', 100000))
    stock = Stock.query.filter_by(symbol=symbol).first_or_404()

    total_return = ((stock.price - (initial_capital * 0.04)) / initial_capital) * 100
    final_value = initial_capital * (1 + (total_return / 100))
    result = BacktestResult(
        strategy_name=strategy,
        symbol=symbol,
        initial_capital=initial_capital,
        final_value=final_value,
        total_return=total_return,
        win_rate=63.4,
        total_trades=25,
        max_drawdown=12.7,
        profit_factor=1.64,
    )
    db.session.add(result)
    db.session.commit()
    return jsonify({"success": True, "data": result.to_dict()})


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
    return jsonify({"success": True, "data": [item.to_dict() for item in items]})


@app.route('/api/watchlist', methods=['POST'])
@jwt_required()
def add_watchlist():
    data = request.get_json(silent=True) or {}
    symbol = (data.get('symbol') or '').upper()
    if not symbol:
        return jsonify({"success": False, "message": "Symbol required"}), 400
    user_id = int(get_jwt_identity())
    if WatchlistItem.query.filter_by(user_id=user_id, symbol=symbol).first():
        return jsonify({"success": False, "message": "Already in watchlist"}), 409
    item = WatchlistItem(user_id=user_id, symbol=symbol)
    db.session.add(item)
    db.session.commit()
    return jsonify({"success": True, "data": item.to_dict()}), 201


@app.route('/api/watchlist/<symbol>', methods=['DELETE'])
@jwt_required()
def delete_watchlist(symbol):
    item = WatchlistItem.query.filter_by(user_id=int(get_jwt_identity()), symbol=symbol.upper()).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify({"success": True, "message": "Removed from watchlist"})


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
