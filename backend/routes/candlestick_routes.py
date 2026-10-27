from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from backend.services.historical_backtest import (
    detect_candlestick_patterns,
    get_csv_chart_candles,
    get_demo_research_universe,
)


bp = Blueprint('candlestick_chart', __name__)
SUPPORTED_TIMEFRAMES = {'3M', '6M', '1Y', '5Y'}


@bp.route('/api/candlestick-chart/instruments', methods=['GET'])
@jwt_required()
def chart_instruments():
    try:
        return jsonify({
            'success': True,
            'data': get_demo_research_universe(),
            'provider': 'Bundled historical CSV',
        })
    except (OSError, ValueError) as error:
        return jsonify({'success': False, 'message': str(error)}), 503


@bp.route('/api/candlestick-chart', methods=['GET'])
@jwt_required()
def chart_history():
    symbol = request.args.get('symbol', '').strip().upper()
    timeframe = request.args.get('timeframe', '1Y').strip().upper()
    if not symbol or len(symbol) > 30:
        return jsonify({'success': False, 'message': 'Enter a valid CSV instrument symbol.'}), 400
    if timeframe not in SUPPORTED_TIMEFRAMES:
        return jsonify({'success': False, 'message': 'Choose 3M, 6M, 1Y, or 5Y history.'}), 400
    try:
        candles = get_csv_chart_candles(symbol, timeframe)
    except LookupError as error:
        return jsonify({'success': False, 'message': str(error)}), 404
    except (OSError, ValueError) as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    return jsonify({
        'success': True,
        'data': {
            'symbol': symbol,
            'exchange': 'NSE',
            'timeframe': timeframe,
            'candles': candles,
            'patterns': detect_candlestick_patterns(candles),
            'provider': 'Bundled historical CSV',
        },
    })
