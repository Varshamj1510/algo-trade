from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.services.gemini_assistant import consume_chat_request
from backend.services.gemini_assistant import (
    AssistantConfigurationError,
    AssistantProviderError,
    AssistantRateLimitError,
    AssistantUnavailableError,
    chat_with_gemini,
)


bp = Blueprint('ai_assistant', __name__, url_prefix='/api/ai-assistant')
MAX_MESSAGES = 12
MAX_MESSAGE_LENGTH = 2000
MAX_CONVERSATION_LENGTH = 10000


@bp.route('/chat', methods=['POST'])
@jwt_required()
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('messages'), list):
        return jsonify({'success': False, 'message': 'Send a messages array to the AI assistant.'}), 400

    incoming = payload['messages']
    if not incoming or len(incoming) > MAX_MESSAGES:
        return jsonify({
            'success': False,
            'message': f'Include between 1 and {MAX_MESSAGES} recent messages.',
        }), 400

    messages = []
    total_length = 0
    for message in incoming:
        if (
            not isinstance(message, dict)
            or not isinstance(message.get('role'), str)
            or message['role'] not in {'user', 'assistant'}
        ):
            return jsonify({'success': False, 'message': 'Each message must have a user or assistant role.'}), 400
        content = message.get('content')
        if not isinstance(content, str):
            return jsonify({'success': False, 'message': 'Message content must be text.'}), 400
        content = content.strip()
        if not content or len(content) > MAX_MESSAGE_LENGTH:
            return jsonify({
                'success': False,
                'message': f'Messages must contain 1 to {MAX_MESSAGE_LENGTH} characters.',
            }), 400
        total_length += len(content)
        if total_length > MAX_CONVERSATION_LENGTH:
            return jsonify({'success': False, 'message': 'The recent conversation is too long. Start a new chat.'}), 400
        messages.append({'role': message['role'], 'content': content})

    if messages[-1]['role'] != 'user':
        return jsonify({'success': False, 'message': 'The most recent message must be from you.'}), 400
    if not consume_chat_request(int(get_jwt_identity())):
        return jsonify({
            'success': False,
            'message': 'Chat limit reached. Please wait a minute before sending another message.',
        }), 429

    try:
        result = chat_with_gemini(messages)
    except AssistantConfigurationError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except AssistantRateLimitError as error:
        return jsonify({'success': False, 'message': str(error)}), 429
    except AssistantUnavailableError as error:
        return jsonify({'success': False, 'message': str(error)}), 503
    except AssistantProviderError as error:
        return jsonify({'success': False, 'message': str(error)}), 502

    return jsonify({'success': True, 'data': result})
