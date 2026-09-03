from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from backend.models import Stock

bp = Blueprint('market', __name__, url_prefix='/api')


@bp.route('/market', methods=['GET'])
@jwt_required()
def market():
    stocks = Stock.query.order_by(Stock.symbol.asc()).all()
    return jsonify({'success': True, 'data': [s.to_dict() for s in stocks]})


@bp.route('/market/<symbol>', methods=['GET'])
@jwt_required()
def market_detail(symbol):
    stock = Stock.query.filter_by(symbol=symbol.upper()).first_or_404()
    return jsonify({'success': True, 'data': stock.to_dict()})
