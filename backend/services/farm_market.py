import csv
import math
from pathlib import Path


MANDI_CSV = Path(__file__).resolve().parent.parent / 'data' / 'mandi_prices.csv'


CROP_MARKETS = {
    'TOMATO': {
        'name': 'Tomato', 'unit': 'quintal',
        'markets': [
            {'district': 'Bengaluru Rural', 'market': 'Doddaballapur', 'price': 2200, 'previous_price': 2050, 'distance_km': 28},
            {'district': 'Bengaluru Rural', 'market': 'Yelahanka', 'price': 2080, 'previous_price': 2100, 'distance_km': 36},
            {'district': 'Kolar', 'market': 'Kolar APMC', 'price': 2350, 'previous_price': 2180, 'distance_km': 62},
        ],
        'season': 'Year-round; strong supply during peak summer and monsoon transitions',
    },
    'ONION': {
        'name': 'Onion', 'unit': 'quintal',
        'markets': [
            {'district': 'Bengaluru Rural', 'market': 'Yeshwanthpur', 'price': 2900, 'previous_price': 2750, 'distance_km': 31},
            {'district': 'Chikkaballapur', 'market': 'Chikkaballapur APMC', 'price': 3050, 'previous_price': 2800, 'distance_km': 58},
            {'district': 'Kolar', 'market': 'Kolar APMC', 'price': 2980, 'previous_price': 2920, 'distance_km': 68},
        ],
        'season': 'High storage suitability; best timing depends on humidity and stock quality',
    },
    'RICE': {
        'name': 'Rice', 'unit': 'quintal',
        'markets': [
            {'district': 'Mandya', 'market': 'Mandya APMC', 'price': 3250, 'previous_price': 3180, 'distance_km': 46},
            {'district': 'Mysuru', 'market': 'Nanjangud', 'price': 3320, 'previous_price': 3210, 'distance_km': 74},
            {'district': 'Hassan', 'market': 'Hassan APMC', 'price': 3180, 'previous_price': 3160, 'distance_km': 97},
        ],
        'season': 'Seasonal harvest cycles; compare minimum support and local demand',
    },
}

BUYERS = [
    {'name': 'Green Valley Farmers Cooperative', 'district': 'Bengaluru Rural', 'crops': ['Tomato', 'Onion'], 'type': 'Cooperative', 'verified': True},
    {'name': 'Karnataka Produce Collective', 'district': 'Kolar', 'crops': ['Tomato', 'Onion', 'Rice'], 'type': 'Farmer producer organization', 'verified': True},
    {'name': 'Mandya Grain Buyers Network', 'district': 'Mandya', 'crops': ['Rice'], 'type': 'Buyer network', 'verified': False},
]

SCHEMES = [
    {'name': 'PM-KISAN', 'summary': 'Income-support benefit for eligible farming families.', 'category': 'Income support'},
    {'name': 'Pradhan Mantri Fasal Bima Yojana', 'summary': 'Crop-insurance coverage against notified local risks.', 'category': 'Insurance'},
    {'name': 'Kisan Credit Card', 'summary': 'Short-term working-capital credit for agricultural needs.', 'category': 'Credit'},
]

WEATHER_ALERTS = [
    {'level': 'Watch', 'title': 'Heavy rain watch', 'detail': 'Protect harvested produce, reduce open storage exposure and check drainage.'},
    {'level': 'Advisory', 'title': 'High humidity', 'detail': 'Short-term storage needs ventilation and regular moisture checks.'},
]


def get_crop_markets(crop=None, district=None, market=None, state=None):
    crop_filter = (crop or '').strip().lower()
    district_filter = (district or '').strip().lower()
    market_filter = (market or '').strip().lower()
    state_filter = (state or '').strip().lower()
    rows = []

    with MANDI_CSV.open('r', encoding='utf-8-sig', newline='') as csv_file:
        reader = csv.DictReader(csv_file)
        for item in reader:
            commodity = (item.get('Commodity') or '').strip()
            row_district = (item.get('District') or '').strip()
            row_market = (item.get('Market') or '').strip()
            row_state = (item.get('State') or '').strip()
            if crop_filter and crop_filter not in commodity.lower():
                continue
            if district_filter and district_filter not in row_district.lower():
                continue
            if market_filter and market_filter not in row_market.lower():
                continue
            if state_filter and state_filter not in row_state.lower():
                continue
            try:
                modal_price = float(item['Modal_x0020_Price'])
                min_price = float(item['Min_x0020_Price'])
                max_price = float(item['Max_x0020_Price'])
            except (KeyError, TypeError, ValueError):
                continue
            if not all(math.isfinite(value) and value >= 0 for value in (modal_price, min_price, max_price)):
                continue
            rows.append({
                'state': row_state,
                'crop': commodity,
                'unit': 'quintal',
                'district': row_district,
                'market': row_market,
                'variety': (item.get('Variety') or '').strip(),
                'grade': (item.get('Grade') or '').strip(),
                'arrival_date': (item.get('Arrival_Date') or '').strip(),
                'price': round(modal_price, 2),
                'min_price': round(min_price, 2),
                'max_price': round(max_price, 2),
                'previous_price': round(modal_price, 2),
                'change_pct': 0,
                'distance_km': 0,
                'season': 'Use arrival date and local seasonal conditions to judge timing.',
            })

    rows.sort(key=lambda item: (item['arrival_date'], item['crop'].lower(), item['market'].lower()))
    return rows[:500]


def recommend_sale(price, previous_price, quantity, transport_cost, storage_cost, distance_km, crop):
    values = [price, previous_price, quantity, transport_cost, storage_cost, distance_km]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values):
        raise ValueError('Enter valid numeric values.')
    price = float(price); previous_price = float(previous_price); quantity = float(quantity)
    transport_cost = float(transport_cost); storage_cost = float(storage_cost); distance_km = float(distance_km)
    if price <= 0 or previous_price <= 0 or quantity <= 0 or transport_cost < 0 or storage_cost < 0 or distance_km < 0:
        raise ValueError('Prices and quantity must be positive; costs and distance cannot be negative.')

    gross_revenue = price * quantity
    net_revenue = gross_revenue - transport_cost - storage_cost
    yesterday_change_pct = ((price - previous_price) / previous_price) * 100
    transport_per_quintal = transport_cost / quantity

    if yesterday_change_pct <= -2 or distance_km >= 80:
        action = 'WAIT'
        reason = 'Recent price weakness or a long transport distance reduces the immediate net benefit.'
    elif yesterday_change_pct >= 2 and net_revenue > 0:
        action = 'SELL NOW'
        reason = 'The current price is stronger and the market provides a positive net return.'
    elif storage_cost <= transport_cost * 0.5 and yesterday_change_pct >= 0:
        action = 'STORE'
        reason = 'Storage cost is manageable and the price trend supports a short storage review.'
    else:
        action = 'WAIT'
        reason = 'The current margin does not clearly justify immediate sale or storage.'

    return {
        'action': action,
        'reason': reason,
        'crop': crop.strip().upper() if crop else '',
        'gross_revenue': round(gross_revenue, 2),
        'transport_per_quintal': round(transport_per_quintal, 2),
        'net_revenue': round(net_revenue, 2),
        'change_pct': round(yesterday_change_pct, 2),
        'profit_formula': 'Net revenue = (Market price x Quantity) - Transport cost - Storage cost',
    }


def get_farm_resources(crop=None, district=None):
    crop_name = (crop or '').strip()
    district_name = (district or '').strip()
    buyers = [
        buyer for buyer in BUYERS
        if (not crop_name or crop_name.lower() in [value.lower() for value in buyer['crops']])
        and (not district_name or district_name.lower() in buyer['district'].lower())
    ]
    return {
        'buyers': buyers,
        'schemes': SCHEMES,
        'weather_alerts': WEATHER_ALERTS,
        'languages': ['English', 'Kannada', 'Hindi', 'Telugu'],
        'offline': {
            'enabled': True,
            'saved_features': ['Crop search', 'Calculated recommendations', 'Recent mandi prices'],
        },
    }
