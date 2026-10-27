import os
from datetime import datetime, timedelta

import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.database import db
from backend.models import AcademyAccess


bp = Blueprint('trading_academy', __name__, url_prefix='/api/academy')
YOUTUBE_SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'
PREMIUM_PRICE_INR = 199
DEMO_PREMIUM_DAYS = 30
TRADING_KEYWORDS = {
    'stock', 'stocks', 'share', 'shares', 'trading', 'trade', 'investing',
    'investment', 'market', 'markets', 'equity', 'equities', 'candlestick',
    'technical analysis', 'fundamental analysis', 'portfolio', 'nifty',
    'sensex', 'forex', 'futures', 'options', 'option', 'risk management',
    'support', 'resistance', 'rsi', 'macd', 'moving average', 'broker',
}


def _access_for_user(user_id):
    access = db.session.get(AcademyAccess, user_id)
    if access is None:
        access = AcademyAccess(user_id=user_id, access_type='free')
        db.session.add(access)
        db.session.commit()
    active = (
        access.access_type == 'demo-premium'
        and access.expires_at is not None
        and access.expires_at > datetime.utcnow()
    )
    if access.access_type == 'demo-premium' and not active:
        access.access_type = 'free'
        access.expires_at = None
        db.session.commit()
    return access, active


@bp.route('/access', methods=['GET'])
@jwt_required()
def get_academy_access():
    access, active = _access_for_user(int(get_jwt_identity()))
    return jsonify({
        'success': True,
        'data': {
            'tier': 'premium' if active else 'free',
            'premium_price_inr': PREMIUM_PRICE_INR,
            'demo_unlock': active,
            'expires_at': access.expires_at.isoformat() + 'Z' if active else None,
        },
    })


@bp.route('/premium-demo', methods=['POST'])
@jwt_required()
def unlock_demo_premium():
    user_id = int(get_jwt_identity())
    access, active = _access_for_user(user_id)
    if not active:
        access.access_type = 'demo-premium'
        access.expires_at = datetime.utcnow() + timedelta(days=DEMO_PREMIUM_DAYS)
        db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Premium demo access is active for {DEMO_PREMIUM_DAYS} days. No payment was made.',
        'data': {
            'tier': 'premium',
            'premium_price_inr': PREMIUM_PRICE_INR,
            'demo_unlock': True,
            'expires_at': access.expires_at.isoformat() + 'Z',
        },
    })


@bp.route('/youtube-search', methods=['GET'])
@jwt_required()
def search_youtube_lessons():
    query = request.args.get('q', '').strip()
    tier = request.args.get('tier', 'free').strip().lower()
    if not query or len(query) > 100:
        return jsonify({'success': False, 'message': 'Enter a lesson search up to 100 characters.'}), 400
    if tier not in {'free', 'premium'}:
        return jsonify({'success': False, 'message': 'Choose the free or premium lesson catalog.'}), 400
    if tier == 'premium':
        _access, active = _access_for_user(int(get_jwt_identity()))
        if not active:
            return jsonify({'success': False, 'message': 'Unlock the Premium demo to search Premium lessons.'}), 403

    api_key = os.getenv('YOUTUBE_API_KEY', '').strip()
    if not api_key:
        return jsonify({
            'success': False,
            'message': 'YouTube search is not configured. Add YOUTUBE_API_KEY to the server environment and restart AlgoMind.',
        }), 503

    try:
        response = requests.get(
            YOUTUBE_SEARCH_URL,
            params={
                'key': api_key,
                'part': 'snippet',
                'q': (
                    f'{query} stock market trading investing education'
                    if tier == 'premium'
                    else f'{query} stock market trading education beginner'
                ),
                'type': 'video',
                'videoCategoryId': '27',
                'videoEmbeddable': 'true',
                'safeSearch': 'strict',
                'maxResults': 12,
                'relevanceLanguage': 'en',
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout:
        return jsonify({'success': False, 'message': 'YouTube search timed out. Please try again.'}), 504
    except requests.RequestException:
        return jsonify({'success': False, 'message': 'YouTube search is temporarily unavailable. Please try again.'}), 502
    except ValueError:
        return jsonify({'success': False, 'message': 'YouTube returned an unreadable search response.'}), 502

    items = payload.get('items')
    if not isinstance(items, list):
        return jsonify({'success': False, 'message': 'YouTube returned an invalid search response.'}), 502
    videos = []
    for item in items:
        snippet = item.get('snippet') or {}
        video_id = (item.get('id') or {}).get('videoId')
        if not isinstance(video_id, str) or not video_id or len(video_id) > 30:
            continue
        title = str(snippet.get('title') or 'Untitled lesson')[:200]
        description = str(snippet.get('description') or '')[:500]
        searchable_text = f'{title} {description}'.lower()
        if not any(keyword in searchable_text for keyword in TRADING_KEYWORDS):
            continue
        videos.append({
            'video_id': video_id,
            'title': title,
            'description': description,
            'channel': str(snippet.get('channelTitle') or 'YouTube creator')[:120],
            'published_at': str(snippet.get('publishedAt') or '')[:30],
            'thumbnail': f'https://i.ytimg.com/vi/{video_id}/mqdefault.jpg',
        })
    return jsonify({'success': True, 'data': videos, 'source': 'YouTube Data API v3'})
