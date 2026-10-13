import asyncio
import threading

from kiteconnect import KiteTicker

from backend.services.kite_market import get_instrument_token
from backend.services.kite_session import KiteSessionError, clear_access_token, get_stream_credentials


class KiteMarketStream:
    def __init__(self):
        self._lock = threading.RLock()
        self._ticker = None
        self._status = 'disconnected'
        self._subscribers = {}
        self._tokens = set()
        self._instruments = {}
        self._next_subscriber_id = 0

    def status(self):
        with self._lock:
            return {'status': self._status}

    def subscribe(self, loop, queue, symbol='RELIANCE', exchange='NSE'):
        token = int(get_instrument_token(symbol, exchange))
        instrument = {'symbol': symbol.upper(), 'exchange': exchange.upper()}
        with self._lock:
            self._next_subscriber_id += 1
            subscriber_id = self._next_subscriber_id
            self._subscribers[subscriber_id] = (loop, queue)
            first_token = token not in self._tokens
            self._tokens.add(token)
            self._instruments[token] = instrument
            ticker = self._ticker
            should_start = ticker is None
            if should_start:
                try:
                    api_key, access_token = get_stream_credentials()
                except KiteSessionError:
                    self._subscribers.pop(subscriber_id, None)
                    self._tokens.discard(token)
                    self._instruments.pop(token, None)
                    raise
                ticker = KiteTicker(api_key, access_token)
                ticker.on_connect = self._on_connect
                ticker.on_ticks = self._on_ticks
                ticker.on_close = self._on_close
                ticker.on_error = self._on_error
                ticker.on_reconnect = self._on_reconnect
                ticker.on_noreconnect = self._on_no_reconnect
                self._ticker = ticker
                self._status = 'connecting'

        if should_start:
            try:
                ticker.connect(threaded=True)
            except (OSError, RuntimeError) as error:
                with self._lock:
                    if self._ticker is ticker:
                        self._ticker = None
                        self._status = 'error'
                    self._subscribers.pop(subscriber_id, None)
                raise RuntimeError('Could not start the Kite market stream.') from error
        elif first_token and self._is_connected(ticker):
            ticker.subscribe([token])
            ticker.set_mode(ticker.MODE_FULL, [token])

        self._enqueue(loop, queue, {'type': 'status', 'status': self.status()['status']})
        return subscriber_id

    def unsubscribe(self, subscriber_id):
        with self._lock:
            self._subscribers.pop(subscriber_id, None)
            if self._subscribers or self._ticker is None:
                return
            ticker = self._ticker
            self._ticker = None
            self._tokens.clear()
            self._instruments.clear()
            self._status = 'disconnected'
        ticker.close()

    def close(self):
        with self._lock:
            ticker = self._ticker
            self._ticker = None
            self._subscribers.clear()
            self._tokens.clear()
            self._instruments.clear()
            self._status = 'disconnected'
        if ticker is not None:
            ticker.close()

    @staticmethod
    def _is_connected(ticker):
        try:
            return ticker.is_connected()
        except AttributeError:
            return False

    def _on_connect(self, ticker, response):
        with self._lock:
            tokens = list(self._tokens)
            self._status = 'connected'
        if tokens:
            ticker.subscribe(tokens)
            ticker.set_mode(ticker.MODE_FULL, tokens)
        self._broadcast({'type': 'status', 'status': 'connected'})

    def _on_ticks(self, ticker, ticks):
        for tick in ticks:
            token = tick.get('instrument_token')
            with self._lock:
                instrument = self._instruments.get(token)
            if not instrument:
                continue
            ohlc = tick.get('ohlc') or {}
            timestamp = tick.get('exchange_timestamp') or tick.get('last_trade_time')
            if hasattr(timestamp, 'isoformat'):
                timestamp = timestamp.isoformat()
            self._broadcast({
                'type': 'tick',
                'data': {
                    **instrument,
                    'last_traded_price': tick.get('last_price'),
                    'open': ohlc.get('open'),
                    'high': ohlc.get('high'),
                    'low': ohlc.get('low'),
                    'previous_close': ohlc.get('close'),
                    'volume': tick.get('volume_traded', tick.get('volume')),
                    'timestamp': timestamp,
                },
            })

    def _on_close(self, ticker, code, reason):
        with self._lock:
            if self._ticker is ticker:
                self._status = 'disconnected'
        self._broadcast({'type': 'status', 'status': 'disconnected'})

    def _on_error(self, ticker, code, reason):
        error_text = str(reason or '').lower()
        if code in (401, 403) and 'token' in error_text:
            try:
                clear_access_token()
            except KiteSessionError:
                pass
            with self._lock:
                self._status = 'reauthorization_required'
            self._broadcast({
                'type': 'error',
                'message': 'Kite session expired or was rejected. Reauthorize to resume live data.',
            })
            return
        with self._lock:
            self._status = 'error'
        self._broadcast({
            'type': 'error',
            'message': 'Kite market stream reported an error. Check the session and market-data access.',
        })

    def _on_reconnect(self, ticker, attempt_count):
        with self._lock:
            self._status = 'reconnecting'
        self._broadcast({'type': 'status', 'status': 'reconnecting'})

    def _on_no_reconnect(self, ticker):
        with self._lock:
            self._status = 'error'
        self._broadcast({
            'type': 'error',
            'message': 'Kite could not reconnect the market stream. Reauthorize or retry later.',
        })

    def _broadcast(self, message):
        with self._lock:
            subscribers = list(self._subscribers.values())
        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(self._enqueue, loop, queue, message)
            except RuntimeError:
                continue

    @staticmethod
    def _enqueue(loop, queue, message):
        if loop.is_closed():
            return
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            queue.put_nowait(message)


market_stream = KiteMarketStream()
