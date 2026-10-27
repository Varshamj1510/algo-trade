from backend.app import app


def test_sentiment_page_is_available_and_uses_ai_analysis():
    response = app.test_client().get('/sentiment')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Sentiment Analysis' in page
    assert 'Analyze sentiment' in page
    assert 'Hugging Face' in page
    assert '/api/sentiment/analyze' in page
    assert 'positiveWords' not in page
    assert 'Model confidence' in page
    assert 'negative-score-value' in page
    assert 'neutral-score-value' in page
    assert 'positive-score-value' in page
    assert page.count('class="sentiment-example ') == 6
    assert 'Mixed wording' in page
    assert 'Negation' in page
