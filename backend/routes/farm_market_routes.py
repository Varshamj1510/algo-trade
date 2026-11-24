from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from backend.services.farm_market import get_crop_markets, get_farm_resources, recommend_sale


bp = Blueprint('farm_market', __name__, url_prefix='/api/farm-market')


@bp.route('/markets', methods=['GET'])
@jwt_required()
def farm_markets():
    crop = request.args.get('crop', '').strip()
    district = request.args.get('district', '').strip()
    market = request.args.get('market', '').strip()
    state = request.args.get('state', '').strip()
    rows = get_crop_markets(crop=crop, district=district, market=market, state=state)
    return jsonify({
        'success': True,
        'data': rows,
        'source': 'AGMARKNET daily mandi-price CSV',
        'live': True,
    })


@bp.route('/recommend', methods=['POST'])
@jwt_required()
def farm_recommendation():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400
    try:
        result = recommend_sale(
            price=payload.get('price'),
            previous_price=payload.get('previous_price'),
            quantity=payload.get('quantity'),
            transport_cost=payload.get('transport_cost'),
            storage_cost=payload.get('storage_cost'),
            distance_km=payload.get('distance_km'),
            crop=payload.get('crop'),
        )
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    return jsonify({'success': True, 'data': result})


@bp.route('/resources', methods=['GET'])
@jwt_required()
def farm_resources():
    return jsonify({
        'success': True,
        'data': get_farm_resources(
            crop=request.args.get('crop', '').strip(),
            district=request.args.get('district', '').strip(),
        ),
    })
