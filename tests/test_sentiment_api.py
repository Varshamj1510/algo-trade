import json
from unittest.mock import Mock

import pytest

from backend.app import app
from backend.services import huggingface_sentiment


def authenticated_client():
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'email': 'demo@algotrade.com',
        'password': 'demo123',
    })
    assert response.status_code == 200
    token = response.get_json()['token']
    return client, {'Authorization': f'Bearer {token}'}


def test_sentiment_endpoint_returns_model_result(monkeypatch):
    result = {
        'label': 'positive',
        'confidence': 91.2,
        'scores': {'negative': 1.3, 'neutral': 7.5, 'positive': 91.2},
        'model': huggingface_sentiment.MODEL_ID,
        'provider': 'Hugging Face Inference Providers',
    }
    monkeypatch.setattr(
        'backend.routes.sentiment_routes.analyze_financial_sentiment',
        lambda text: result,
    )
    client, headers = authenticated_client()

    response = client.post(
        '/api/sentiment/analyze',
        json={'text': 'Company reports strong quarterly results.'},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.get_json()['data'] == result


@pytest.mark.parametrize(('payload', 'message'), [
    (None, 'Request body must be a JSON object.'),
    ({'text': 123}, 'Enter text to analyze.'),
    ({'text': 'short'}, 'Enter at least 10 characters to analyze.'),
    ({'text': 'x' * 5001}, 'Text must be 5000 characters or fewer.'),
])
def test_sentiment_endpoint_validates_input(payload, message):
    client, headers = authenticated_client()

    response = client.post(
        '/api/sentiment/analyze',
        json=payload,
        headers=headers,
    )

    assert response.status_code == 400
    assert response.get_json()['message'] == message


def test_sentiment_endpoint_requires_authentication():
    response = app.test_client().post(
        '/api/sentiment/analyze',
        json={'text': 'Company reports strong quarterly results.'},
    )

    assert response.status_code == 401


def test_sentiment_endpoint_returns_configuration_error(monkeypatch):
    from backend.routes.sentiment_routes import SentimentConfigurationError

    def missing_token(_text):
        raise SentimentConfigurationError('Hugging Face token is not configured.')

    monkeypatch.setattr(
        'backend.routes.sentiment_routes.analyze_financial_sentiment',
        missing_token,
    )
    client, headers = authenticated_client()

    response = client.post(
        '/api/sentiment/analyze',
        json={'text': 'Company reports strong quarterly results.'},
        headers=headers,
    )

    assert response.status_code == 503
    assert response.get_json()['message'] == 'Hugging Face token is not configured.'


def test_model_response_maps_three_financial_classes(monkeypatch):
    response = Mock(status_code=200, ok=True)
    response.json.return_value = [[
        {'label': 'LABEL_2', 'score': 0.91},
        {'label': 'LABEL_0', 'score': 0.02},
        {'label': 'LABEL_1', 'score': 0.07},
    ]]
    provider_request = Mock(return_value=response)
    monkeypatch.setenv('HUGGINGFACE_API_TOKEN', 'test-token')
    monkeypatch.setattr(huggingface_sentiment.requests, 'post', provider_request)

    result = huggingface_sentiment.analyze_financial_sentiment('Revenue increased this quarter.')

    assert result['label'] == 'positive'
    assert result['confidence'] == 91.0
    assert result['scores'] == {'negative': 2.0, 'neutral': 7.0, 'positive': 91.0}
    assert result['model'] == huggingface_sentiment.MODEL_ID
    provider_request.assert_called_once_with(
        huggingface_sentiment.INFERENCE_URL,
        headers={'Authorization': 'Bearer test-token'},
        json={
            'inputs': 'Revenue increased this quarter.',
            'parameters': {'top_k': None},
        },
        timeout=(5, 30),
    )


def test_model_requires_server_side_token(monkeypatch):
    monkeypatch.delenv('HUGGINGFACE_API_TOKEN', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)

    with pytest.raises(huggingface_sentiment.SentimentConfigurationError):
        huggingface_sentiment.analyze_financial_sentiment('Revenue increased this quarter.')


def gemini_response():
    response = Mock(status_code=200, ok=True)
    response.json.return_value = {
        'candidates': [{
            'content': {
                'parts': [{
                    'text': json.dumps({
                        'label': 'positive',
                        'scores': {'negative': 0.02, 'neutral': 0.08, 'positive': 0.9},
                    }),
                }],
            },
        }],
    }
    return response


def test_gemini_provider_analyzes_text_without_huggingface(monkeypatch):
    monkeypatch.delenv('HUGGINGFACE_API_TOKEN', raising=False)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-key')
    provider_request = Mock(return_value=gemini_response())
    monkeypatch.setattr(huggingface_sentiment.requests, 'post', provider_request)

    result = huggingface_sentiment.analyze_financial_sentiment('Revenue increased this quarter.')

    assert result == {
        'label': 'positive',
        'confidence': 90.0,
        'scores': {'negative': 2.0, 'neutral': 8.0, 'positive': 90.0},
        'model': huggingface_sentiment.GEMINI_MODEL_ID,
        'provider': 'Google Gemini',
    }
    args, kwargs = provider_request.call_args
    assert args == (huggingface_sentiment.GEMINI_INFERENCE_URL,)
    assert kwargs['headers'] == {'x-goog-api-key': 'test-gemini-key'}
    assert kwargs['json']['generationConfig']['responseMimeType'] == 'application/json'


def test_huggingface_payment_error_falls_back_to_gemini(monkeypatch):
    monkeypatch.setenv('HUGGINGFACE_API_TOKEN', 'test-hf-token')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-key')
    hf_payment_error = Mock(status_code=402, ok=False)
    provider_request = Mock(side_effect=[hf_payment_error, gemini_response()])
    monkeypatch.setattr(huggingface_sentiment.requests, 'post', provider_request)

    result = huggingface_sentiment.analyze_financial_sentiment('Revenue increased this quarter.')

    assert result['provider'] == 'Google Gemini'
    assert result['label'] == 'positive'
    assert provider_request.call_count == 2


def test_huggingface_payment_error_explains_missing_gemini_key(monkeypatch):
    monkeypatch.setenv('HUGGINGFACE_API_TOKEN', 'test-hf-token')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    provider_request = Mock(return_value=Mock(status_code=402, ok=False))
    monkeypatch.setattr(huggingface_sentiment.requests, 'post', provider_request)

    with pytest.raises(
        huggingface_sentiment.SentimentConfigurationError,
        match='GEMINI_API_KEY',
    ):
        huggingface_sentiment.analyze_financial_sentiment('Revenue increased this quarter.')

    provider_request.assert_called_once()


def test_model_response_rejects_missing_class_scores(monkeypatch):
    response = Mock(status_code=200, ok=True)
    response.json.return_value = [
        {'label': 'positive', 'score': 0.91},
        {'label': 'negative', 'score': 0.09},
    ]
    monkeypatch.setenv('HUGGINGFACE_API_TOKEN', 'test-token')
    monkeypatch.setattr(huggingface_sentiment.requests, 'post', Mock(return_value=response))

    with pytest.raises(huggingface_sentiment.SentimentProviderError):
        huggingface_sentiment.analyze_financial_sentiment('Revenue increased this quarter.')
