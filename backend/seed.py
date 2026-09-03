from backend.database import db
from backend.models import Alert, Holding, Report, Signal, Stock, StrategyModel, User, WatchlistItem


def seed_demo_data():
    user = User.query.filter_by(email='demo@algotrade.com').first()
    if not user:
        user = User(
            full_name='Algo Trader',
            email='demo@algotrade.com',
            username='trader',
            plan='Premium Plan',
        )
        user.set_password('demo123')
        db.session.add(user)
        db.session.flush()
    else:
        user.full_name = 'Algo Trader'
        user.username = 'trader'
        user.plan = 'Premium Plan'

    db.session.commit()

    if Stock.query.count() == 0:
        stocks = [
            ('RELIANCE', 'Reliance Industries', 'Energy', 2856.40, 1.38, 2450000, 2868.50, 2825.00, 2840.10),
            ('TCS', 'Tata Consultancy Services', 'IT', 3620.15, 0.92, 1800000, 3648.20, 3595.00, 3608.55),
            ('INFY', 'Infosys', 'IT', 1512.80, -1.24, 2105000, 1535.40, 1494.50, 1532.70),
            ('HDFCBANK', 'HDFC Bank', 'Banking', 1685.30, 1.55, 1680000, 1704.40, 1662.10, 1660.50),
            ('ICICIBANK', 'ICICI Bank', 'Banking', 1245.60, -0.85, 2050000, 1268.90, 1230.00, 1256.30),
            ('SBIN', 'State Bank of India', 'Banking', 812.40, -1.20, 3100000, 829.00, 800.50, 821.70),
            ('AXISBANK', 'Axis Bank', 'Banking', 1062.30, -0.95, 2240000, 1085.00, 1049.30, 1072.80),
            ('BEL', 'Bharat Electronics', 'Defense', 306.75, 4.35, 4300000, 310.20, 298.20, 293.60),
            ('NTPC', 'NTPC Ltd', 'Power', 335.40, 3.20, 2800000, 339.50, 329.00, 325.10),
            ('M&M', 'Mahindra & Mahindra', 'Auto', 2742.10, 2.87, 1900000, 2770.30, 2695.00, 2666.80),
            ('TATASTEEL', 'Tata Steel', 'Metals', 155.65, 2.45, 5400000, 158.90, 152.40, 151.90),
            ('ADANIENT', 'Adani Enterprises', 'Infrastructure', 2651.30, 2.10, 3300000, 2680.80, 2610.20, 2595.50),
            ('TECHM', 'Tech Mahindra', 'IT', 1236.50, -2.39, 1450000, 1259.00, 1215.20, 1267.80),
            ('WIPRO', 'Wipro', 'IT', 458.20, -1.85, 1875000, 470.50, 450.20, 467.00),
        ]
        for stock in stocks:
            db.session.add(Stock(
                symbol=stock[0],
                name=stock[1],
                sector=stock[2],
                price=stock[3],
                change=stock[4],
                volume=stock[5],
                high=stock[6],
                low=stock[7],
                open_price=stock[8],
                prev_close=stock[8],
            ))

    if Signal.query.count() == 0:
        signals = [
            ('RELIANCE', 'BUY', 2856.40, 2950.00, 2790.00, 92, 'Momentum', '10:29 AM'),
            ('TCS', 'BUY', 3620.15, 3740.00, 3550.00, 90, 'Trend Following', '10:28 AM'),
            ('INFY', 'SELL', 1512.80, 1480.00, 1540.00, 86, 'Breakout', '10:27 AM'),
            ('HDFCBANK', 'BUY', 1685.30, 1740.00, 1650.00, 89, 'Momentum', '10:26 AM'),
            ('ICICIBANK', 'SELL', 1245.60, 1210.00, 1275.00, 85, 'Mean Reversion', '10:25 AM'),
        ]
        for symbol, signal, current, target, stop, conf, strategy, ts in signals:
            db.session.add(Signal(
                symbol=symbol,
                signal=signal,
                current_price=current,
                target_price=target,
                stop_loss=stop,
                confidence=conf,
                strategy=strategy,
                timestamp=None,
            ))

    if StrategyModel.query.count() == 0:
        strategies = [
            ('Moving Average', 'Captures average trend direction and entries around dynamic support.', 'Active', 68.5, 142),
            ('Momentum', 'Identifies strong directional moves with breakout confirmation.', 'Active', 71.2, 126),
            ('RSI', 'Flags overbought and oversold conditions in trending markets.', 'Paused', 64.1, 98),
            ('MACD', 'Tracks momentum shifts using moving average convergence.', 'Active', 69.8, 110),
            ('Bollinger Bands', 'Uses volatility bands to identify squeeze and expansion.', 'Active', 73.4, 118),
        ]
        for name, description, status, win_rate, total_trades in strategies:
            db.session.add(StrategyModel(
                name=name,
                description=description,
                status=status,
                win_rate=win_rate,
                total_trades=total_trades,
                user_id=user.id,
            ))

    if WatchlistItem.query.filter_by(user_id=user.id).count() == 0:
        db.session.add(WatchlistItem(user_id=user.id, symbol='RELIANCE'))
        db.session.add(WatchlistItem(user_id=user.id, symbol='TCS'))
        db.session.add(WatchlistItem(user_id=user.id, symbol='BEL'))

    if Alert.query.filter_by(user_id=user.id).count() == 0:
        db.session.add(Alert(user_id=user.id, title='Price Alert', description='RELIANCE above ₹2,900', type='Price Alert', status='Active'))
        db.session.add(Alert(user_id=user.id, title='Signal Alert', description='Momentum setup on NTPC', type='Signal Alert', status='Triggered'))
        db.session.add(Alert(user_id=user.id, title='Portfolio Alert', description='Allocation target reached', type='Portfolio Alert', status='Disabled'))

    if Report.query.count() == 0:
        db.session.add(Report(name='May Performance Report', total_return=16.2, total_trades=58, win_rate=63.7, profit_factor=1.48, status='Ready'))
        db.session.add(Report(name='June Weekly Snapshot', total_return=8.7, total_trades=21, win_rate=61.0, profit_factor=1.33, status='Ready'))

    if Holding.query.filter_by(user_id=user.id).count() == 0:
        db.session.add(Holding(user_id=user.id, symbol='RELIANCE', quantity=120, average_price=2650.00, current_price=2856.40))
        db.session.add(Holding(user_id=user.id, symbol='TCS', quantity=80, average_price=3420.00, current_price=3620.15))
        db.session.add(Holding(user_id=user.id, symbol='INFY', quantity=150, average_price=1440.00, current_price=1512.80))
        db.session.add(Holding(user_id=user.id, symbol='HDFCBANK', quantity=60, average_price=1700.00, current_price=1685.30))

    db.session.commit()
