from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from backend.services.historical_backtest import (
    get_csv_chart_candles,
    get_demo_research_universe,
)
from backend.services.reinforcement_learning import (
    MIN_CANDLES,
    run_q_learning_backtest,
)


bp = Blueprint('reinforcement_learning', __name__)
BASE_DIR = Path(__file__).resolve().parents[2]


@bp.route('/reinforcement-learning', methods=['GET'])
def page():
    return send_file(str(BASE_DIR / 'frontend' / 'reinforcement-learning.html'))


@bp.route('/api/reinforcement-learning/instruments', methods=['GET'])
@jwt_required()
def instruments():
    try:
        available = [
            item for item in get_demo_research_universe()
            if item['observations'] >= MIN_CANDLES
        ]
    except (OSError, ValueError) as error:
        current_app.logger.exception('Could not load historical instruments for RL.')
        return jsonify({
            'success': False,
            'message': f'Historical instrument data is unavailable: {error}',
        }), 503

    return jsonify({
        'success': True,
        'data_source': 'Bundled historical CSV',
        'data': available,
    })


@bp.route('/api/reinforcement-learning/backtest', methods=['POST'])
@jwt_required()
def backtest():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'A JSON object is required.'}), 400

    symbol = data.get('symbol')
    if not isinstance(symbol, str) or not symbol.strip():
        return jsonify({'success': False, 'message': 'Choose a historical instrument.'}), 400

    initial_capital = data.get('initial_capital', 100_000)
    if (
        isinstance(initial_capital, bool)
        or not isinstance(initial_capital, (int, float))
        or not 1_000 <= initial_capital <= 10_000_000
    ):
        return jsonify({
            'success': False,
            'message': 'Initial capital must be between ₹1,000 and ₹10,000,000.',
        }), 400

    try:
        candles = get_csv_chart_candles(symbol.strip().upper(), '5Y')
        result = run_q_learning_backtest(
            candles,
            symbol,
            initial_capital=initial_capital,
        )
    except LookupError as error:
        return jsonify({'success': False, 'message': str(error)}), 404
    except ValueError as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    except OSError as error:
        current_app.logger.exception('Could not run RL backtest from historical data.')
        return jsonify({
            'success': False,
            'message': f'Historical data is unavailable: {error}',
        }), 503

    return jsonify({'success': True, 'data': result})
