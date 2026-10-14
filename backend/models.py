import json
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

from backend.database import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(50), default='Premium Plan')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_public_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'email': self.email,
            'username': self.username,
            'plan': self.plan,
        }


class Stock(db.Model):
    __tablename__ = 'stocks'

    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    sector = db.Column(db.String(80), nullable=True)
    price = db.Column(db.Float, nullable=False)
    change = db.Column(db.Float, nullable=False, default=0.0)
    volume = db.Column(db.Integer, nullable=False, default=0)
    high = db.Column(db.Float, nullable=False, default=0.0)
    low = db.Column(db.Float, nullable=False, default=0.0)
    open_price = db.Column(db.Float, nullable=False, default=0.0)
    prev_close = db.Column(db.Float, nullable=False, default=0.0)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'name': self.name,
            'sector': self.sector,
            'price': round(self.price, 2),
            'change': round(self.change, 2),
            'volume': self.volume,
            'high': round(self.high, 2),
            'low': round(self.low, 2),
            'open': round(self.open_price, 2),
            'previous_close': round(self.prev_close, 2),
        }


class Signal(db.Model):
    __tablename__ = 'signals'

    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    signal = db.Column(db.String(10), nullable=False)
    current_price = db.Column(db.Float, nullable=False)
    target_price = db.Column(db.Float, nullable=False)
    stop_loss = db.Column(db.Float, nullable=False)
    confidence = db.Column(db.Integer, nullable=False, default=80)
    strategy = db.Column(db.String(80), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'signal': self.signal,
            'current_price': round(self.current_price, 2),
            'target_price': round(self.target_price, 2),
            'stop_loss': round(self.stop_loss, 2),
            'confidence': self.confidence,
            'strategy': self.strategy,
            'timestamp': self.timestamp.strftime('%H:%M %p') if self.timestamp else '',
        }


class StrategyModel(db.Model):
    __tablename__ = 'strategies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(250), nullable=True)
    status = db.Column(db.String(20), default='Active')
    win_rate = db.Column(db.Float, default=0.0)
    total_trades = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    buy_logic = db.Column(db.String(3), nullable=True)
    buy_conditions = db.Column(db.Text, nullable=True)
    sell_logic = db.Column(db.String(3), nullable=True)
    sell_conditions = db.Column(db.Text, nullable=True)

    def to_dict(self):
        buy_conditions = json.loads(self.buy_conditions) if self.buy_conditions else []
        sell_conditions = json.loads(self.sell_conditions) if self.sell_conditions else []
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'win_rate': round(self.win_rate, 2),
            'total_trades': self.total_trades,
            'buy_logic': self.buy_logic or 'AND',
            'buy_conditions': buy_conditions,
            'sell_logic': self.sell_logic or 'AND',
            'sell_conditions': sell_conditions,
            'is_custom': bool(buy_conditions or sell_conditions),
        }


class BacktestResult(db.Model):
    __tablename__ = 'backtests'

    id = db.Column(db.Integer, primary_key=True)
    strategy_name = db.Column(db.String(80), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    initial_capital = db.Column(db.Float, nullable=False)
    final_value = db.Column(db.Float, nullable=False)
    total_return = db.Column(db.Float, nullable=False)
    win_rate = db.Column(db.Float, nullable=False)
    total_trades = db.Column(db.Integer, default=0)
    max_drawdown = db.Column(db.Float, nullable=False)
    profit_factor = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'strategy_name': self.strategy_name,
            'symbol': self.symbol,
            'initial_capital': round(self.initial_capital, 2),
            'final_value': round(self.final_value, 2),
            'total_return': round(self.total_return, 2),
            'win_rate': round(self.win_rate, 2),
            'total_trades': self.total_trades,
            'max_drawdown': round(self.max_drawdown, 2),
            'profit_factor': round(self.profit_factor, 2),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Report(db.Model):
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    total_return = db.Column(db.Float, default=0.0)
    total_trades = db.Column(db.Integer, default=0)
    win_rate = db.Column(db.Float, default=0.0)
    profit_factor = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(30), default='Ready')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'total_return': round(self.total_return, 2),
            'total_trades': self.total_trades,
            'win_rate': round(self.win_rate, 2),
            'profit_factor': round(self.profit_factor, 2),
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }


class WatchlistItem(db.Model):
    __tablename__ = 'watchlist'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    symbol = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'symbol', name='uq_watchlist_user_symbol'),)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'symbol': self.symbol,
        }


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(250), nullable=True)
    type = db.Column(db.String(50), default='Price Alert')
    status = db.Column(db.String(20), default='Active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'type': self.type,
            'status': self.status,
            'time': self.created_at.strftime('%H:%M %p') if self.created_at else '',
        }


class Holding(db.Model):
    __tablename__ = 'holdings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    symbol = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0.0)
    average_price = db.Column(db.Float, nullable=False, default=0.0)
    current_price = db.Column(db.Float, nullable=False, default=0.0)

    def to_dict(self):
        pnl = (self.current_price - self.average_price) * self.quantity
        return {
            'symbol': self.symbol,
            'quantity': round(self.quantity, 2),
            'average_price': round(self.average_price, 2),
            'current_price': round(self.current_price, 2),
            'investment': round(self.average_price * self.quantity, 2),
            'current_value': round(self.current_price * self.quantity, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round((pnl / max(self.average_price * self.quantity, 1)) * 100, 2),
        }


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    symbol = db.Column(db.String(20), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'type': self.type,
            'quantity': round(self.quantity, 2),
            'price': round(self.price, 2),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    exchange = db.Column(db.String(20), nullable=False, default='NSE')
    side = db.Column(db.String(10), nullable=False)
    order_type = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False, default=0.0)
    trigger_price = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='OPEN')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'symbol': self.symbol,
            'exchange': self.exchange,
            'side': self.side,
            'order_type': self.order_type,
            'quantity': round(self.quantity, 2),
            'price': round(self.price or 0, 2),
            'trigger_price': round(self.trigger_price, 2) if self.trigger_price is not None else None,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
            'estimated_value': round((self.price or 0) * self.quantity, 2),
        }


class PaperAccount(db.Model):
    __tablename__ = 'paper_accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    cash_balance = db.Column(db.Float, nullable=False, default=1500000.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PaperTrade(db.Model):
    __tablename__ = 'paper_trades'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(20), nullable=False)
    exchange = db.Column(db.String(10), nullable=False, default='NSE')
    side = db.Column(db.String(4), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'exchange': self.exchange,
            'side': self.side,
            'quantity': self.quantity,
            'price': round(self.price, 2),
            'value': round(self.price * self.quantity, 2),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class PaperFutureTrade(db.Model):
    __tablename__ = 'paper_future_trades'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    symbol = db.Column(db.String(30), nullable=False)
    expiry = db.Column(db.Date, nullable=False)
    side = db.Column(db.String(4), nullable=False)
    lots = db.Column(db.Integer, nullable=False)
    lot_size = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        value = self.price * self.lot_size * self.lots
        return {
            'id': self.id,
            'symbol': self.symbol,
            'exchange': 'NFO',
            'expiry': self.expiry.isoformat(),
            'side': self.side,
            'lots': self.lots,
            'lot_size': self.lot_size,
            'quantity': self.lots * self.lot_size,
            'price': round(self.price, 2),
            'value': round(value, 2),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }
