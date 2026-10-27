import logging
import os
import signal
import threading

from backend.app import app
from backend.services.price_alert_worker import (
    check_and_deliver_price_alerts,
    update_worker_heartbeat,
)


LOGGER = logging.getLogger('alphamind.price_alert_worker')
POLL_INTERVAL_SECONDS = max(10, int(os.getenv('PRICE_ALERT_POLL_SECONDS', '30')))
stop_event = threading.Event()


def _request_stop(signum, frame):
    LOGGER.info('Received shutdown signal %s.', signum)
    stop_event.set()


def run_worker():
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    LOGGER.info('Price alert push worker started; polling every %s seconds.', POLL_INTERVAL_SECONDS)
    while not stop_event.is_set():
        try:
            with app.app_context():
                update_worker_heartbeat()
                check_and_deliver_price_alerts()
        except Exception:
            LOGGER.exception('Price alert worker cycle failed.')
        stop_event.wait(POLL_INTERVAL_SECONDS)
    LOGGER.info('Price alert push worker stopped.')


if __name__ == '__main__':
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    run_worker()
