from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from backend.services.huggingface_sentiment import (
    SentimentConfigurationError,
    SentimentModelUnavailableError,
    SentimentProviderError,
    SentimentRateLimitError,
    analyze_financial_sentiment,
)


bp = Blueprint('sentiment', __name__, url_prefix='/api/sentiment')
MAX_TEXT_LENGTH = 5000
MIN_TEXT_LENGTH = 10


@bp.route('/analyze', methods=['POST'])
@jwt_required()
def analyze_sentiment():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'message': 'Request body must be a JSON object.'}), 400

    text = payload.get('text')
    if not isinstance(text, str):
        return jsonify({'success': False, 'message': 'Enter text to analyze.'}), 400
    text = text.strip()
    if len(text) < MIN_TEXT_LENGTH:
        return jsonify({'success': False, 'message': f'Enter at least {MIN_TEXT_LENGTH} characters to analyze.'}), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({'success': False, 'message': f'Text must be {MAX_TEXT_LENGTH} characters or fewer.'}), 400

    try:
        result = analyze_financial_sentiment(text)
    except SentimentConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except SentimentRateLimitError as error:
        return jsonify({'success': False, 'message': str(error)}), 429
    except SentimentModelUnavailableError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except SentimentProviderError as error:
        return jsonify({'success': False, 'message': str(error)}), 502

    return jsonify({
        'success': True,
        'data': result,
        'source': result['provider'],
    })
