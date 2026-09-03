from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from backend.models import Signal, User

bp = Blueprint('dashboard', __name__, url_prefix='/api')


@bp.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    user = User.query.first()
    return jsonify({
        'success': True,
        'user': user.to_public_dict() if user else {},
        'stats': {
            'total_portfolio_value': 245678.90,
            'today_pnl': 5678.30,
            'total_profit': 25430.50,
            'winning_trades': 68.42,
            'active_signals': 7,
        },
        'signals': [signal.to_dict() for signal in Signal.query.order_by(Signal.id.desc()).limit(5).all()],
    })
