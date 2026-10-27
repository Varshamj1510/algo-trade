import json
import logging
import math
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pywebpush import WebPushException, webpush

from backend.database import db
from backend.models import (
    AlertNotificationSettings,
    AlertPushSubscription,
    AlertWorkerHeartbeat,
    PriceAlert,
)
from backend.services.kite_market import KiteAPIError, KiteConfigurationError, get_live_quotes


LOGGER = logging.getLogger(__name__)
WORKER_NAME = 'price-alerts'
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '').strip()
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', 'mailto:admin@alphamind.local').strip()


def _quiet_hours_active(settings, now=None):
    if not settings.quiet_hours_enabled:
        return False
    local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(settings.timezone))
    current_minutes = local_now.hour * 60 + local_now.minute
    start_hour, start_minute = map(int, settings.quiet_start.split(':'))
    end_hour, end_minute = map(int, settings.quiet_end.split(':'))
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    if start < end:
        return start <= current_minutes < end
    return current_minutes >= start or current_minutes < end


def _send_to_subscription(subscription, alert):
    payload = json.dumps({
        'title': 'AlgoMind price alert',
        'body': (
            f'{alert.name} ({alert.symbol}) reached ₹{alert.triggered_price:,.2f}; '
            f'your {alert.direction} ₹{alert.target_price:,.2f} target was met.'
        ),
        'tag': f'price-alert-{alert.id}',
        'url': '/alerts',
    })
    return webpush(
        subscription_info={
            'endpoint': subscription.endpoint,
            'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
        },
        data=payload,
        vapid_private_key=VAPID_PRIVATE_KEY,
        vapid_claims={'sub': VAPID_SUBJECT},
        ttl=86400,
    )


def check_and_deliver_price_alerts():
    if not VAPID_PRIVATE_KEY or not os.getenv('VAPID_PUBLIC_KEY', '').strip():
        LOGGER.error('Price alert worker is running without configured VAPID keys.')
        return

    active_alerts = PriceAlert.query.join(
        AlertNotificationSettings,
        PriceAlert.user_id == AlertNotificationSettings.user_id,
    ).filter(
        PriceAlert.enabled.is_(True),
        AlertNotificationSettings.enabled.is_(True),
    ).all()
    if not active_alerts:
        return

    unique_instruments = list({
        (alert.exchange, alert.symbol): {'symbol': alert.symbol, 'exchange': alert.exchange}
        for alert in active_alerts
    }.values())
    try:
        quotes = get_live_quotes(unique_instruments)
    except (KiteConfigurationError, KiteAPIError) as error:
        LOGGER.warning('Price alerts skipped because live Kite quotes are unavailable: %s', error)
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for alert in active_alerts:
        if alert.triggered_at is not None:
            continue
        quote = quotes.get((alert.exchange, alert.symbol))
        try:
            price = float(quote.get('price')) if quote else 0
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        condition_met = price >= alert.target_price if alert.direction == 'above' else price <= alert.target_price
        if condition_met:
            alert.triggered_at = now
            alert.triggered_price = price
    db.session.commit()

    pending_alerts = PriceAlert.query.join(
        AlertNotificationSettings,
        PriceAlert.user_id == AlertNotificationSettings.user_id,
    ).filter(
        PriceAlert.enabled.is_(True),
        PriceAlert.triggered_at.isnot(None),
        PriceAlert.notification_delivered_at.is_(None),
        AlertNotificationSettings.enabled.is_(True),
    ).all()

    for alert in pending_alerts:
        settings = AlertNotificationSettings.query.filter_by(user_id=alert.user_id).first()
        if settings is None or _quiet_hours_active(settings):
            continue
        subscriptions = AlertPushSubscription.query.filter_by(user_id=alert.user_id).all()
        delivered = False
        for subscription in subscriptions:
            try:
                _send_to_subscription(subscription, alert)
                delivered = True
            except WebPushException as error:
                status_code = getattr(getattr(error, 'response', None), 'status_code', None)
                if status_code in (404, 410):
                    LOGGER.info('Removing expired push subscription for user %s.', alert.user_id)
                    db.session.delete(subscription)
                else:
                    LOGGER.warning(
                        'Push delivery failed for price alert %s (HTTP %s).',
                        alert.id,
                        status_code or 'unknown',
                    )
        if delivered:
            alert.notification_delivered_at = now
        db.session.commit()


def update_worker_heartbeat(now=None):
    heartbeat = AlertWorkerHeartbeat.query.filter_by(name=WORKER_NAME).first()
    if heartbeat is None:
        heartbeat = AlertWorkerHeartbeat(name=WORKER_NAME)
        db.session.add(heartbeat)
    heartbeat.last_seen_at = now or datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
