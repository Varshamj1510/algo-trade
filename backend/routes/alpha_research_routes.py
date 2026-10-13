from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from backend.services.alpha_research import AlphaResearchError, analyze_alpha
from backend.services.historical_backtest import (
    get_demo_research_candles,
    get_demo_research_universe,
)
from backend.services.instrument_catalog import find_instrument
from backend.services.kite_market import (
    KiteAPIError,
    KiteConfigurationError,
    get_historical_candles,
)


bp = Blueprint('alpha_research', __name__)
SUPPORTED_TIMEFRAMES = {'1Y', '5Y'}
SUPPORTED_SOURCES = {'demo', 'kite'}


@bp.route('/api/alpha-research/instruments', methods=['GET'])
@jwt_required()
def research_instruments():
    try:
        return jsonify({
            'success': True,
            'data': get_demo_research_universe(),
            'provider': 'Bundled historical CSV demo data',
        })
    except (OSError, ValueError) as error:
        return jsonify({'success': False, 'message': str(error)}), 503


@bp.route('/api/alpha-research', methods=['POST'])
@jwt_required()
def research_alpha():
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400

    symbol = payload.get('symbol')
    exchange = payload.get('exchange', 'NSE')
    timeframe = payload.get('timeframe', '1Y')
    source = payload.get('source', 'kite')
    if not isinstance(symbol, str) or not symbol.strip() or len(symbol.strip()) > 30:
        return jsonify({'success': False, 'message': 'Enter a valid instrument symbol.'}), 400
    if not isinstance(exchange, str) or exchange.strip().upper() not in {'NSE', 'BSE'}:
        return jsonify({'success': False, 'message': 'Exchange must be NSE or BSE.'}), 400
    if not isinstance(timeframe, str) or timeframe.strip().upper() not in SUPPORTED_TIMEFRAMES:
        return jsonify({'success': False, 'message': 'Choose a supported historical period.'}), 400
    if not isinstance(source, str) or source.strip().lower() not in SUPPORTED_SOURCES:
        return jsonify({'success': False, 'message': 'Choose Kite Connect or bundled demo data.'}), 400

    symbol = symbol.strip().upper()
    exchange = exchange.strip().upper()
    timeframe = timeframe.strip().upper()
    source = source.strip().lower()

    try:
        if source == 'demo':
            candles = get_demo_research_candles(symbol, exchange, timeframe)
        else:
            instrument = find_instrument(symbol, exchange)
            if not instrument:
                return jsonify({'success': False, 'message': f'{symbol} is not in the {exchange} instrument catalog.'}), 404
            candles = get_historical_candles(instrument, timeframe)
        result = analyze_alpha(candles, symbol, exchange, timeframe)
        if source == 'demo':
            result['provider'] = 'Bundled historical CSV demo data (not Kite Connect)'
    except LookupError as error:
        return jsonify({'success': False, 'message': str(error)}), 404
    except AlphaResearchError as error:
        return jsonify({'success': False, 'message': str(error)}), 422
    except (OSError, ValueError) as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except KiteAPIError as error:
        return jsonify({'success': False, 'message': str(error)}), 502
    return jsonify({'success': True, 'data': result})
