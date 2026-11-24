import math
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.database import db
from backend.models import (
    PaperAccount,
    PaperFutureTrade,
    PaperTrade,
    PaperTradeJournal,
    PaperVirtualOrder,
    StrategyModel,
)
from backend.services.instrument_catalog import (
    find_demo_instrument,
    find_paper_trading_instrument,
    get_paper_trading_instruments,
)
from backend.services.kite_market import (
    KiteAPIError,
    KiteConfigurationError,
    get_nifty_futures,
    get_live_quotes,
)
from backend.services.paper_strategy import BUILT_IN_STRATEGIES, review_strategy


bp = Blueprint('paper_trading', __name__, url_prefix='/api/paper-trading')
STARTING_CASH = 1500000.0
LEGACY_STARTING_CASH = 100000.0


def _quote_price(quote):
    try:
        raw_price = (quote or {}).get('price')
        if raw_price is None:
            return None
        price = float(raw_price)
    except (TypeError, ValueError, OverflowError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def _account_for_user(user_id):
    account = PaperAccount.query.filter_by(user_id=user_id).with_for_update().first()
    if account is None:
        account = PaperAccount()
        account.user_id = user_id
        account.cash_balance = STARTING_CASH
        db.session.add(account)
        db.session.commit()
    elif account.cash_balance == LEGACY_STARTING_CASH:
        equity_trades = PaperTrade.query.filter_by(user_id=user_id).first()
        future_trades = PaperFutureTrade.query.filter_by(user_id=user_id).first()
        if equity_trades is None and future_trades is None:
            account.cash_balance = STARTING_CASH
            db.session.commit()
    return account


def _positions_and_pnl(trades):
    positions = {}
    realized_pnl = 0.0
    realized_exits = []

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
            exit_pnl = (trade.price - position['average_price']) * trade.quantity
            realized_pnl += exit_pnl
            realized_exits.append((trade.created_at, exit_pnl))
            position['quantity'] -= trade.quantity
            if position['quantity'] == 0:
                position['average_price'] = 0.0

    return positions, realized_pnl, realized_exits


def _future_positions_and_pnl(trades):
    positions = {}
    realized_pnl = 0.0
    realized_exits = []

    for trade in trades:
        key = (trade.symbol, trade.expiry)
        position = positions.setdefault(key, {
            'lots': 0,
            'lot_size': trade.lot_size,
            'average_price': 0.0,
        })
        if trade.lot_size != position['lot_size']:
            raise KiteAPIError(f'Lot size changed for {trade.symbol}; virtual futures account needs review.')
        if trade.side == 'BUY':
            new_lots = position['lots'] + trade.lots
            position['average_price'] = (
                (position['lots'] * position['average_price'] + trade.lots * trade.price)
                / new_lots
            )
            position['lots'] = new_lots
        else:
            exit_pnl = (
                (trade.price - position['average_price'])
                * position['lot_size'] * trade.lots
            )
            realized_pnl += exit_pnl
            realized_exits.append((trade.created_at, exit_pnl))
            position['lots'] -= trade.lots
            if position['lots'] == 0:
                position['average_price'] = 0.0

    return positions, realized_pnl, realized_exits


def _account_snapshot(user_id, market_quotes=None):
    account = _account_for_user(user_id)
    trades = PaperTrade.query.filter_by(user_id=user_id).order_by(
        PaperTrade.created_at.asc(), PaperTrade.id.asc(),
    ).all()
    positions, realized_pnl, equity_exits = _positions_and_pnl(trades)
    future_trades = PaperFutureTrade.query.filter_by(user_id=user_id).order_by(
        PaperFutureTrade.created_at.asc(), PaperFutureTrade.id.asc(),
    ).all()
    journal_notes = {
        (entry.trade_type, entry.trade_id): entry.note
        for entry in PaperTradeJournal.query.filter_by(user_id=user_id).all()
    }
    future_positions, future_realized_pnl, future_exits = _future_positions_and_pnl(future_trades)
    open_positions = {
        key: position for key, position in positions.items()
        if position['quantity'] > 0
    }
    open_future_positions = {
        key: position for key, position in future_positions.items()
        if position['lots'] > 0
    }
    market_quotes = dict(market_quotes or {})
    for exchange, symbol in open_positions:
        instrument = find_paper_trading_instrument(symbol, exchange) or find_demo_instrument(symbol, exchange)
        if instrument is None:
            raise ValueError(f'No seeded virtual quote is available for {exchange}:{symbol}.')
        market_quotes[(exchange, symbol)] = {'price': instrument['price']}

    missing_future_quotes = [
        {'exchange': 'NFO', 'symbol': symbol}
        for symbol, _expiry in open_future_positions
        if _quote_price(market_quotes.get(('NFO', symbol))) is None
    ]
    if missing_future_quotes:
        market_quotes.update(get_live_quotes(missing_future_quotes))

    holdings = []
    for key, position in sorted(open_positions.items()):
        quote = market_quotes.get(key)
        market_price = _quote_price(quote)
        if market_price is None:
            raise ValueError(f'Virtual quote is unavailable for {key[0]}:{key[1]}.')
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
            'instrument_type': 'EQUITY',
        })

    for (symbol, expiry), position in sorted(open_future_positions.items()):
        quote = market_quotes.get(('NFO', symbol))
        market_price = _quote_price(quote)
        if market_price is None:
            raise KiteAPIError(f'Kite quote is unavailable for NFO:{symbol}; account values were not refreshed.')
        quantity = position['lots'] * position['lot_size']
        market_value = market_price * quantity
        invested = position['average_price'] * quantity
        holdings.append({
            'symbol': symbol,
            'exchange': 'NFO',
            'expiry': expiry.isoformat(),
            'quantity': quantity,
            'lots': position['lots'],
            'lot_size': position['lot_size'],
            'average_price': round(position['average_price'], 2),
            'current_price': round(market_price, 2),
            'market_value': round(market_value, 2),
            'unrealized_pnl': round(market_value - invested, 2),
            'instrument_type': 'FUT',
        })

    market_value = sum(item['market_value'] for item in holdings)
    realized_exits = sorted(equity_exits + future_exits, key=lambda item: item[0])
    running_realized_pnl = 0.0
    peak_realized_pnl = 0.0
    realized_drawdown = 0.0
    for _closed_at, exit_pnl in realized_exits:
        running_realized_pnl += exit_pnl
        peak_realized_pnl = max(peak_realized_pnl, running_realized_pnl)
        realized_drawdown = max(realized_drawdown, peak_realized_pnl - running_realized_pnl)
    return {
        'starting_cash': STARTING_CASH,
        'cash_balance': round(account.cash_balance, 2),
        'market_value': round(market_value, 2),
        'total_equity': round(account.cash_balance + market_value, 2),
        'realized_pnl': round(realized_pnl + future_realized_pnl, 2),
        'unrealized_pnl': round(sum(item['unrealized_pnl'] for item in holdings), 2),
        'journal_summary': {
            'closed_exits': len(realized_exits),
            'profitable_exit_rate': round(
                sum(exit_pnl > 0 for _closed_at, exit_pnl in realized_exits)
                / len(realized_exits) * 100,
                2,
            ) if realized_exits else 0,
            'max_realized_pnl_drawdown': round(realized_drawdown, 2),
        },
        'holdings': holdings,
        'trades': [
            *[
                {**trade.to_dict(), 'trade_type': 'EQUITY', 'journal_note': journal_notes.get(('EQUITY', trade.id), '')}
                for trade in reversed(trades)
            ],
            *[
                {**trade.to_dict(), 'trade_type': 'FUTURE', 'journal_note': journal_notes.get(('FUTURE', trade.id), '')}
                for trade in reversed(future_trades)
            ],
        ],
        'instruments': [
            {
                'symbol': item['symbol'],
                'exchange': item['exchange'],
                'name': item['name'],
            }
            for item in get_paper_trading_instruments()
        ],
    }


@bp.route('/account', methods=['GET'])
@jwt_required()
def get_paper_account():
    try:
        snapshot = _account_snapshot(int(get_jwt_identity()))
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 422
    return jsonify({'success': True, 'data': snapshot, 'source': 'Seeded prices; virtual trades only'})


@bp.route('/account/add-virtual-cash', methods=['POST'])
@jwt_required()
def add_virtual_cash():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400
    try:
        raw_amount = payload.get('amount')
        if raw_amount is None or isinstance(raw_amount, bool):
            raise ValueError
        parsed_amount = float(raw_amount)
    except (TypeError, ValueError, OverflowError):
        return jsonify({'success': False, 'message': 'Enter a whole-rupee virtual amount.'}), 400
    if not math.isfinite(parsed_amount) or not parsed_amount.is_integer() or not 1 <= parsed_amount <= 1000000:
        return jsonify({
            'success': False,
            'message': 'Virtual top-ups must be a whole-rupee amount between ₹1 and ₹10,00,000.',
        }), 400

    account = _account_for_user(int(get_jwt_identity()))
    account.cash_balance = round(account.cash_balance + parsed_amount, 2)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'₹{parsed_amount:,.0f} practice funds added to your virtual account. No payment was made.',
        'account': _account_snapshot(int(get_jwt_identity())),
    })


@bp.route('/quote', methods=['GET'])
@jwt_required()
def get_paper_quote():
    symbol = request.args.get('symbol', '').strip().upper()
    exchange = request.args.get('exchange', 'NSE').strip().upper()
    if not symbol or len(symbol) > 30 or exchange not in {'NSE', 'BSE', 'NFO'}:
        return jsonify({'success': False, 'message': 'Provide a valid NSE, BSE, or NFO symbol.'}), 400
    if exchange == 'NFO':
        try:
            valid_contract = any(item['symbol'] == symbol for item in get_nifty_futures())
        except KiteConfigurationError as error:
            return jsonify({'success': False, 'message': str(error)}), 503
        except KiteAPIError as error:
            return jsonify({'success': False, 'message': str(error)}), 502
        if not valid_contract:
            return jsonify({'success': False, 'message': 'Choose an active NIFTY futures contract from the Kite list.'}), 404
    else:
        instrument = find_paper_trading_instrument(symbol, exchange) or find_demo_instrument(symbol, exchange)
        if instrument is None:
            return jsonify({
                'success': False,
                'message': f'No seeded virtual quote is available for {exchange}:{symbol}.',
            }), 404
        return jsonify({
            'success': True,
            'data': {'symbol': symbol, 'exchange': exchange, 'price': round(float(instrument['price']), 2)},
            'source': 'Seeded virtual price',
        })
    try:
        quotes = get_live_quotes([{'symbol': symbol, 'exchange': exchange}])
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    quote = quotes.get((exchange, symbol))
    price = _quote_price(quote)
    if price is None:
        return jsonify({
            'success': False,
            'message': f'No Kite market quote is available for {exchange}:{symbol}.',
        }), 404
    return jsonify({
        'success': True,
        'data': {'symbol': symbol, 'exchange': exchange, 'price': round(price, 2)},
        'source': 'Kite Connect quote; virtual trading only',
    })


@bp.route('/futures', methods=['GET'])
@jwt_required()
def list_nifty_futures():
    try:
        contracts = get_nifty_futures()
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    return jsonify({
        'success': True,
        'data': contracts,
        'source': 'Kite Connect instrument master; NIFTY futures only',
    })


@bp.route('/strategies', methods=['GET'])
@jwt_required()
def list_paper_strategies():
    user_id = int(get_jwt_identity())
    saved = (
        StrategyModel.query
        .filter(StrategyModel.user_id == user_id)
        .filter(StrategyModel.buy_conditions.isnot(None))
        .filter(StrategyModel.sell_conditions.isnot(None))
        .order_by(StrategyModel.name.asc())
        .all()
    )
    strategies = [
        {**strategy.to_dict(), 'id': f"saved:{strategy.id}", 'is_custom': True}
        for strategy in saved
    ]
    return jsonify({
        'success': True,
        'data': [
            *[
                {
                    **strategy,
                    'is_custom': False,
                    'buy_conditions': [],
                    'sell_conditions': [],
                }
                for strategy in BUILT_IN_STRATEGIES
            ],
            *strategies,
        ],
    })


@bp.route('/strategy-review', methods=['POST'])
@jwt_required()
def paper_strategy_review():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400
    symbol = payload.get('symbol')
    strategy_id = payload.get('strategy_id')
    if not isinstance(symbol, str) or not symbol.strip() or len(symbol.strip()) > 30:
        return jsonify({'success': False, 'message': 'Choose a valid NSE instrument.'}), 400
    symbol = symbol.strip().upper()
    if find_paper_trading_instrument(symbol, 'NSE') is None:
        return jsonify({'success': False, 'message': 'Choose an available NSE instrument.'}), 404
    if not isinstance(strategy_id, str) or not strategy_id:
        return jsonify({'success': False, 'message': 'Choose a strategy to review.'}), 400

    is_builtin = strategy_id.startswith('builtin:')
    if is_builtin:
        strategy = next((item for item in BUILT_IN_STRATEGIES if item['id'] == strategy_id), None)
        if strategy is None:
            return jsonify({'success': False, 'message': 'The selected strategy is unavailable.'}), 404
    elif strategy_id.startswith('saved:'):
        try:
            saved_id = int(strategy_id.removeprefix('saved:'))
        except ValueError:
            return jsonify({'success': False, 'message': 'Choose a valid saved strategy.'}), 400
        strategy = StrategyModel.query.filter_by(
            id=saved_id,
            user_id=int(get_jwt_identity()),
        ).first()
        if strategy is None or not strategy.buy_conditions or not strategy.sell_conditions:
            return jsonify({'success': False, 'message': 'Saved strategy was not found or has incomplete rules.'}), 404
        strategy = strategy.to_dict()
    else:
        return jsonify({'success': False, 'message': 'Choose a valid strategy.'}), 400

    try:
        result = review_strategy(symbol, strategy, is_builtin)
    except LookupError as error:
        return jsonify({'success': False, 'message': str(error)}), 404
    except (OSError, ValueError) as error:
        return jsonify({'success': False, 'message': str(error)}), 422
    return jsonify({
        'success': True,
        'data': result,
        'source': 'Bundled historical candles for strategy review; seeded prices for virtual orders',
    })


@bp.route('/futures/trades', methods=['POST'])
@jwt_required()
def create_nifty_future_trade():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400
    symbol = payload.get('symbol')
    side = payload.get('side')
    if not isinstance(symbol, str) or not symbol.strip() or len(symbol.strip()) > 30:
        return jsonify({'success': False, 'message': 'Choose a valid Kite NIFTY futures contract.'}), 400
    if not isinstance(side, str) or side.strip().upper() not in {'BUY', 'SELL'}:
        return jsonify({'success': False, 'message': 'Side must be BUY or SELL.'}), 400
    try:
        raw_lots = payload.get('lots')
        if raw_lots is None or isinstance(raw_lots, bool):
            raise ValueError
        parsed_lots = float(raw_lots)
    except (TypeError, ValueError, OverflowError):
        return jsonify({'success': False, 'message': 'Lots must be a positive whole number.'}), 400
    if not math.isfinite(parsed_lots) or not parsed_lots.is_integer() or parsed_lots <= 0:
        return jsonify({'success': False, 'message': 'Lots must be a positive whole number.'}), 400

    try:
        contracts = get_nifty_futures()
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    contract = next((item for item in contracts if item['symbol'] == symbol.strip().upper()), None)
    if contract is None:
        return jsonify({'success': False, 'message': 'Choose an active NIFTY futures contract from the Kite list.'}), 404

    side = side.strip().upper()
    lots = int(parsed_lots)
    user_id = int(get_jwt_identity())
    account = _account_for_user(user_id)
    existing_future_trades = PaperFutureTrade.query.filter_by(user_id=user_id).order_by(
        PaperFutureTrade.created_at.asc(), PaperFutureTrade.id.asc(),
    ).all()
    positions, _, _ = _future_positions_and_pnl(existing_future_trades)
    quote_keys = {
        ('NFO', key[0]) for key, position in positions.items()
        if position['lots'] > 0
    }
    existing_equity_trades = PaperTrade.query.filter_by(user_id=user_id).order_by(
        PaperTrade.created_at.asc(), PaperTrade.id.asc(),
    ).all()
    equity_positions, _, _ = _positions_and_pnl(existing_equity_trades)
    quote_keys.update(
        key for key, position in equity_positions.items()
        if position['quantity'] > 0
    )
    quote_keys.add(('NFO', contract['symbol']))
    try:
        quotes = get_live_quotes([
            {'symbol': quote_symbol, 'exchange': quote_exchange}
            for quote_exchange, quote_symbol in sorted(quote_keys)
        ])
    except KiteConfigurationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteAPIError as error:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(error)}), 502

    price = _quote_price(quotes.get(('NFO', contract['symbol'])))
    if price is None:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f"No Kite quote is available for NFO:{contract['symbol']}.",
        }), 404
    for quote_exchange, quote_symbol in quote_keys:
        if _quote_price(quotes.get((quote_exchange, quote_symbol))) is None:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Kite quote is unavailable for {quote_exchange}:{quote_symbol}; no virtual trade was placed.',
            }), 502

    position = positions.get((contract['symbol'], datetime.fromisoformat(contract['expiry']).date()), {
        'lots': 0,
        'lot_size': contract['lot_size'],
    })
    if position['lot_size'] != contract['lot_size']:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'The Kite lot size changed; no virtual trade was placed.'}), 409
    notional = round(price * contract['lot_size'] * lots, 2)
    if side == 'BUY':
        if notional > account.cash_balance:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'Insufficient virtual cash for the full NIFTY futures contract value.',
            }), 400
        account.cash_balance -= notional
    else:
        if lots > position['lots']:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f"Cannot sell {lots} lots; only {position['lots']} are held for this expiry.",
            }), 400
        account.cash_balance += notional

    trade = PaperFutureTrade()
    trade.user_id = user_id
    trade.symbol = contract['symbol']
    trade.expiry = datetime.fromisoformat(contract['expiry']).date()
    trade.side = side
    trade.lots = lots
    trade.lot_size = contract['lot_size']
    trade.price = price
    db.session.add(trade)
    db.session.commit()
    snapshot = _account_snapshot(user_id, market_quotes=quotes)
    return jsonify({
        'success': True,
        'message': f'Virtual NIFTY futures {side.lower()} filled at the Kite quote. No broker order was sent.',
        'data': trade.to_dict(),
        'account': snapshot,
    }), 201


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
        return jsonify({'success': False, 'message': 'Enter a valid Kite-listed symbol.'}), 400
    if not isinstance(exchange, str) or exchange.strip().upper() not in {'NSE', 'BSE'}:
        return jsonify({'success': False, 'message': 'Exchange must be NSE or BSE.'}), 400
    if not isinstance(side, str) or side.strip().upper() not in {'BUY', 'SELL'}:
        return jsonify({'success': False, 'message': 'Side must be BUY or SELL.'}), 400
    try:
        raw_quantity = payload.get('quantity')
        if raw_quantity is None or isinstance(raw_quantity, bool):
            raise ValueError
        parsed_quantity = float(raw_quantity)
    except (TypeError, ValueError, OverflowError):
        return jsonify({'success': False, 'message': 'Quantity must be a positive whole number.'}), 400
    if not math.isfinite(parsed_quantity) or not parsed_quantity.is_integer() or parsed_quantity <= 0:
        return jsonify({'success': False, 'message': 'Quantity must be a positive whole number.'}), 400
    quantity = int(parsed_quantity)

    side = side.strip().upper()
    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    instrument = find_paper_trading_instrument(symbol, exchange) or find_demo_instrument(symbol, exchange)
    if instrument is None:
        return jsonify({
            'success': False,
            'message': f'No seeded virtual quote is available for {exchange}:{symbol}.',
        }), 404
    user_id = int(get_jwt_identity())
    account = _account_for_user(user_id)
    existing_trades = PaperTrade.query.filter_by(user_id=user_id).order_by(
        PaperTrade.created_at.asc(), PaperTrade.id.asc(),
    ).all()
    price = _quote_price({'price': instrument['price']})
    if price is None:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'The seeded virtual price is invalid; no trade was placed.'}), 422

    trade_value = round(price * quantity, 2)

    if side == 'BUY' and trade_value > account.cash_balance:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Insufficient virtual cash for this buy.'}), 400
    if side == 'SELL':
        buys = PaperTrade.query.filter_by(
            user_id=user_id, symbol=symbol, exchange=exchange, side='BUY',
        ).all()
        sells = PaperTrade.query.filter_by(
            user_id=user_id, symbol=symbol, exchange=exchange, side='SELL',
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

    trade = PaperTrade()
    trade.user_id = user_id
    trade.symbol = symbol
    trade.exchange = exchange
    trade.side = side
    trade.quantity = quantity
    trade.price = price
    db.session.add(trade)
    db.session.commit()
    snapshot = _account_snapshot(user_id)
    return jsonify({
        'success': True,
        'message': f'Virtual {side.lower()} filled at the seeded price. No broker order was sent.',
        'data': trade.to_dict(),
        'account': snapshot,
    }), 201


@bp.route('/orders', methods=['GET'])
@jwt_required()
def list_paper_orders():
    user_id = int(get_jwt_identity())
    status_filter = request.args.get('status', '').strip().upper()
    query = PaperVirtualOrder.query.filter_by(user_id=user_id)
    if status_filter:
        status_filter = status_filter.replace('-', '_')
        if status_filter not in {'OPEN', 'FILLED', 'CANCELLED'}:
            return jsonify({'success': False, 'message': 'Invalid virtual order status.'}), 400
        query = query.filter_by(status=status_filter)
    orders = query.order_by(PaperVirtualOrder.created_at.desc(), PaperVirtualOrder.id.desc()).all()
    return jsonify({'success': True, 'data': [order.to_dict() for order in orders]})


@bp.route('/orders', methods=['POST'])
@jwt_required()
def create_paper_order():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400

    symbol = payload.get('symbol')
    exchange = payload.get('exchange', 'NSE')
    side = payload.get('side')
    order_type = payload.get('order_type', 'MARKET')

    if not isinstance(symbol, str) or not symbol.strip() or len(symbol.strip()) > 20:
        return jsonify({'success': False, 'message': 'Enter a valid symbol.'}), 400
    if not isinstance(exchange, str) or exchange.strip().upper() not in {'NSE', 'BSE'}:
        return jsonify({'success': False, 'message': 'Exchange must be NSE or BSE.'}), 400
    if not isinstance(side, str) or side.strip().upper() not in {'BUY', 'SELL'}:
        return jsonify({'success': False, 'message': 'Side must be BUY or SELL.'}), 400
    if not isinstance(order_type, str) or order_type.strip().upper() not in {'MARKET', 'LIMIT'}:
        return jsonify({'success': False, 'message': 'Order type must be MARKET or LIMIT.'}), 400

    try:
        raw_quantity = payload.get('quantity')
        if raw_quantity is None or isinstance(raw_quantity, bool):
            raise ValueError
        quantity = float(raw_quantity)
    except (TypeError, ValueError, OverflowError):
        return jsonify({'success': False, 'message': 'Quantity must be a positive whole number.'}), 400
    if not math.isfinite(quantity) or not quantity.is_integer() or quantity <= 0:
        return jsonify({'success': False, 'message': 'Quantity must be a positive whole number.'}), 400

    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    side = side.strip().upper()
    order_type = order_type.strip().upper()
    instrument = find_paper_trading_instrument(symbol, exchange) or find_demo_instrument(symbol, exchange)
    if instrument is None:
        return jsonify({'success': False, 'message': f'No seeded virtual quote is available for {exchange}:{symbol}.'}), 404

    market_price = _quote_price({'price': instrument['price']})
    if market_price is None:
        return jsonify({'success': False, 'message': 'The seeded virtual price is invalid.'}), 422

    limit_price = None
    if order_type == 'LIMIT':
        try:
            raw_limit = payload.get('limit_price')
            if raw_limit is None or isinstance(raw_limit, bool):
                raise ValueError
            limit_price = float(raw_limit)
        except (TypeError, ValueError, OverflowError):
            return jsonify({'success': False, 'message': 'Limit price must be greater than zero.'}), 400
        if not math.isfinite(limit_price) or limit_price <= 0:
            return jsonify({'success': False, 'message': 'Limit price must be greater than zero.'}), 400

    user_id = int(get_jwt_identity())
    account = _account_for_user(user_id)
    quantity = int(quantity)

    if order_type == 'MARKET':
        filled_price = market_price
    else:
        if limit_price is None:
            return jsonify({'success': False, 'message': 'Limit price must be greater than zero.'}), 400
        can_fill = limit_price >= market_price if side == 'BUY' else limit_price <= market_price
        filled_price = market_price if can_fill else None

    if filled_price is not None:
        trade_value = round(filled_price * quantity, 2)
        existing_trades = PaperTrade.query.filter_by(user_id=user_id).order_by(
            PaperTrade.created_at.asc(), PaperTrade.id.asc(),
        ).all()
        positions, _, _ = _positions_and_pnl(existing_trades)
        held_quantity = positions.get((exchange, symbol), {'quantity': 0})['quantity']

        if side == 'BUY' and trade_value > account.cash_balance:
            return jsonify({'success': False, 'message': 'Insufficient virtual cash for this order.'}), 400
        if side == 'SELL' and quantity > held_quantity:
            return jsonify({'success': False, 'message': f'Cannot sell {quantity} shares; only {held_quantity} are held.'}), 400

        account.cash_balance += trade_value if side == 'SELL' else -trade_value
        trade = PaperTrade()
        trade.user_id = user_id
        trade.symbol = symbol
        trade.exchange = exchange
        trade.side = side
        trade.quantity = quantity
        trade.price = filled_price
        db.session.add(trade)

    order = PaperVirtualOrder()
    order.user_id = user_id
    order.symbol = symbol
    order.exchange = exchange
    order.side = side
    order.order_type = order_type
    order.quantity = quantity
    order.limit_price = limit_price
    order.status = 'FILLED' if filled_price is not None else 'OPEN'
    order.filled_price = filled_price
    db.session.add(order)
    db.session.commit()

    snapshot = _account_snapshot(user_id)
    return jsonify({
        'success': True,
        'message': 'Virtual order filled.' if filled_price is not None else 'Limit order placed and awaiting a qualifying virtual price.',
        'data': order.to_dict(),
        'account': snapshot,
    }), 201


@bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_paper_order(order_id):
    user_id = int(get_jwt_identity())
    order = PaperVirtualOrder.query.filter_by(id=order_id, user_id=user_id).first()
    if order is None:
        return jsonify({'success': False, 'message': 'Virtual order not found.'}), 404
    if order.status != 'OPEN':
        return jsonify({'success': False, 'message': 'Only open virtual orders can be cancelled.'}), 400
    order.status = 'CANCELLED'
    db.session.add(order)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Virtual order cancelled.', 'data': order.to_dict()})


@bp.route('/trades/<string:trade_type>/<int:trade_id>/journal', methods=['PUT'])
@jwt_required()
def update_paper_trade_journal(trade_type, trade_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400
    note = payload.get('note')
    if not isinstance(note, str) or len(note) > 500:
        return jsonify({'success': False, 'message': 'Journal notes must be 500 characters or fewer.'}), 400
    trade_type = trade_type.upper()
    trade_model = PaperTrade if trade_type == 'EQUITY' else PaperFutureTrade if trade_type == 'FUTURE' else None
    if trade_model is None:
        return jsonify({'success': False, 'message': 'Trade type must be EQUITY or FUTURE.'}), 400
    user_id = int(get_jwt_identity())
    trade = trade_model.query.filter_by(id=trade_id, user_id=user_id).first()
    if trade is None:
        return jsonify({'success': False, 'message': 'Trade not found.'}), 404
    entry = PaperTradeJournal.query.filter_by(
        user_id=user_id,
        trade_type=trade_type,
        trade_id=trade_id,
    ).first()
    note = note.strip()
    if not note:
        if entry is not None:
            db.session.delete(entry)
            db.session.commit()
        return jsonify({'success': True, 'note': ''})
    if entry is None:
        entry = PaperTradeJournal()
        entry.user_id = user_id
        entry.trade_type = trade_type
        entry.trade_id = trade_id
        db.session.add(entry)
    entry.note = note
    db.session.commit()
    return jsonify({'success': True, 'note': entry.note})
