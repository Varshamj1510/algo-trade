import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.database import db
from backend.models import PaperAccount, PaperTrade
from backend.services.instrument_catalog import find_demo_instrument, get_demo_instruments


bp = Blueprint('paper_trading', __name__, url_prefix='/api/paper-trading')
STARTING_CASH = 100000.0


def _account_for_user(user_id):
    account = PaperAccount.query.filter_by(user_id=user_id).with_for_update().first()
    if account is None:
        account = PaperAccount(user_id=user_id, cash_balance=STARTING_CASH)
        db.session.add(account)
        db.session.commit()
    return account


def _account_snapshot(user_id):
    account = _account_for_user(user_id)
    trades = PaperTrade.query.filter_by(user_id=user_id).order_by(
        PaperTrade.created_at.asc(), PaperTrade.id.asc(),
    ).all()
    positions = {}
    realized_pnl = 0.0

    for trade in trades:
        key = (trade.exchange, trade.symbol)
        position = positions.setdefault(key, {
            'quantity': 0,
            'average_price': 0.0,
        })
        if trade.side == 'BUY':
            new_quantity = position['quantity'] + trade.quantity
            position['average_price'] = (
                (position['quantity'] * position['average_price'] + trade.quantity * trade.price)
                / new_quantity
            )
            position['quantity'] = new_quantity
        else:
            realized_pnl += (trade.price - position['average_price']) * trade.quantity
            position['quantity'] -= trade.quantity
            if position['quantity'] == 0:
                position['average_price'] = 0.0

    instruments = {
        (item['exchange'], item['symbol']): item
        for item in get_demo_instruments()
    }
    holdings = []
    for key, position in sorted(positions.items()):
        if position['quantity'] <= 0:
            continue
        instrument = instruments[key]
        market_price = float(instrument['price'])
        market_value = market_price * position['quantity']
        invested = position['average_price'] * position['quantity']
        holdings.append({
            'symbol': key[1],
            'exchange': key[0],
            'quantity': position['quantity'],
            'average_price': round(position['average_price'], 2),
            'current_price': round(market_price, 2),
            'market_value': round(market_value, 2),
            'unrealized_pnl': round(market_value - invested, 2),
        })

    market_value = sum(item['market_value'] for item in holdings)
    return {
        'starting_cash': STARTING_CASH,
        'cash_balance': round(account.cash_balance, 2),
        'market_value': round(market_value, 2),
        'total_equity': round(account.cash_balance + market_value, 2),
        'realized_pnl': round(realized_pnl, 2),
        'unrealized_pnl': round(sum(item['unrealized_pnl'] for item in holdings), 2),
        'holdings': holdings,
        'trades': [trade.to_dict() for trade in reversed(trades)],
        'instruments': [
            {
                'symbol': item['symbol'],
                'exchange': item['exchange'],
                'name': item['name'],
                'price': item['price'],
            }
            for item in get_demo_instruments()
        ],
    }


@bp.route('/account', methods=['GET'])
@jwt_required()
def get_paper_account():
    snapshot = _account_snapshot(int(get_jwt_identity()))
    return jsonify({'success': True, 'data': snapshot, 'source': 'seeded demo prices; virtual trades only'})


@bp.route('/trades', methods=['POST'])
@jwt_required()
def create_paper_trade():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400

    symbol = payload.get('symbol')
    exchange = payload.get('exchange', 'NSE')
    side = payload.get('side')
    if not isinstance(symbol, str) or not symbol.strip() or len(symbol.strip()) > 20:
        return jsonify({'success': False, 'message': 'Enter a valid demo symbol.'}), 400
    if not isinstance(exchange, str) or exchange.strip().upper() not in {'NSE', 'BSE'}:
        return jsonify({'success': False, 'message': 'Exchange must be NSE or BSE.'}), 400
    if not isinstance(side, str) or side.strip().upper() not in {'BUY', 'SELL'}:
        return jsonify({'success': False, 'message': 'Side must be BUY or SELL.'}), 400
    try:
        raw_quantity = payload.get('quantity')
        if isinstance(raw_quantity, bool):
            raise ValueError
        parsed_quantity = float(raw_quantity)
    except (TypeError, ValueError, OverflowError):
        return jsonify({'success': False, 'message': 'Quantity must be a positive whole number.'}), 400
    if not math.isfinite(parsed_quantity) or not parsed_quantity.is_integer() or parsed_quantity <= 0:
        return jsonify({'success': False, 'message': 'Quantity must be a positive whole number.'}), 400
    quantity = int(parsed_quantity)

    instrument = find_demo_instrument(symbol.strip(), exchange.strip())
    if not instrument or not math.isfinite(float(instrument['price'])) or instrument['price'] <= 0:
        return jsonify({'success': False, 'message': 'Choose a symbol with a valid seeded demo price.'}), 404

    side = side.strip().upper()
    price = float(instrument['price'])
    trade_value = round(price * quantity, 2)
    user_id = int(get_jwt_identity())
    account = _account_for_user(user_id)

    if side == 'BUY' and trade_value > account.cash_balance:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Insufficient virtual cash for this buy.'}), 400
    if side == 'SELL':
        buys = PaperTrade.query.filter_by(
            user_id=user_id, symbol=instrument['symbol'], exchange=instrument['exchange'], side='BUY',
        ).all()
        sells = PaperTrade.query.filter_by(
            user_id=user_id, symbol=instrument['symbol'], exchange=instrument['exchange'], side='SELL',
        ).all()
        available = sum(trade.quantity for trade in buys) - sum(trade.quantity for trade in sells)
        if quantity > available:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Cannot sell {quantity} shares; only {available} are held in this paper account.',
            }), 400
        account.cash_balance += trade_value
    else:
        account.cash_balance -= trade_value

    trade = PaperTrade(
        user_id=user_id,
        symbol=instrument['symbol'],
        exchange=instrument['exchange'],
        side=side,
        quantity=quantity,
        price=price,
    )
    db.session.add(trade)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Virtual {side.lower()} filled at the seeded demo price.',
        'data': trade.to_dict(),
        'account': _account_snapshot(user_id),
    }), 201
