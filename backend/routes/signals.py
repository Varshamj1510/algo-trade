from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from backend.models import Signal

bp = Blueprint('signals', __name__, url_prefix='/api')


@bp.route('/signals', methods=['GET'])
@jwt_required()
def signals():
    return jsonify({'success': True, 'data': [s.to_dict() for s in Signal.query.order_by(Signal.id.desc()).all()]})
