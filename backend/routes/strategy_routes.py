from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.database import db
from backend.models import StrategyModel
from backend.services.strategy_engine import (
    encode_conditions,
    preview_strategy,
    validate_strategy_rules,
)

bp = Blueprint('strategies', __name__, url_prefix='/api/strategies')


@bp.route('', methods=['GET'])
@jwt_required()
def get_strategies():
    user_id = int(get_jwt_identity())
    strategies = (
        StrategyModel.query
        .filter(db.or_(StrategyModel.user_id == user_id, StrategyModel.user_id.is_(None)))
        .order_by(StrategyModel.id.asc())
        .all()
    )
    return jsonify({'success': True, 'data': [strategy.to_dict() for strategy in strategies]})


@bp.route('', methods=['POST'])
@jwt_required()
def create_strategy():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required.'}), 400

    name = data.get('name')
    description = data.get('description', '')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        return jsonify({'success': False, 'message': 'Name is required and must be 80 characters or fewer.'}), 400
    if not isinstance(description, str) or len(description.strip()) > 250:
        return jsonify({'success': False, 'message': 'Description must be 250 characters or fewer.'}), 400
    try:
        rules = validate_strategy_rules(data)
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400

    strategy = StrategyModel(
        name=name.strip(),
        description=description.strip(),
        status='Active',
        win_rate=0,
        total_trades=0,
        user_id=int(get_jwt_identity()),
        buy_logic=rules['buy_logic'],
        buy_conditions=encode_conditions(rules['buy_conditions']),
        sell_logic=rules['sell_logic'],
        sell_conditions=encode_conditions(rules['sell_conditions']),
    )
    db.session.add(strategy)
    db.session.commit()
    return jsonify({'success': True, 'data': strategy.to_dict()}), 201


@bp.route('/preview', methods=['POST'])
@jwt_required()
def preview():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required.'}), 400
    try:
        rules = validate_strategy_rules(data)
        result = preview_strategy(rules, data.get('indicator_values'))
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    return jsonify({'success': True, 'data': result})
