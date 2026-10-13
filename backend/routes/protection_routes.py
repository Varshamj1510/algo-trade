from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from backend.services.risk_calculator import calculate_protection

bp = Blueprint('protection', __name__, url_prefix='/api/protection')


@bp.route('/calculate', methods=['POST'])
@jwt_required()
def calculate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required.'}), 400
    try:
        result = calculate_protection(data)
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    return jsonify({'success': True, 'data': result})
