import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(BASE_DIR, '.env'))

database_uri = os.getenv(
    'DATABASE_URL',
    'sqlite:///' + os.path.join(BASE_DIR, 'database', 'algotrade.db')
)
if database_uri.startswith('postgres://'):
    database_uri = database_uri.replace('postgres://', 'postgresql://', 1)
if database_uri.startswith('sqlite:'):
    database_url = make_url(database_uri)
    database_name = database_url.database
    if database_name and database_name != ':memory:' and not database_name.startswith('file:'):
        if os.name != 'nt' and re.match(r'^[A-Za-z]:[\\/]', database_name):
            raise RuntimeError(
                'DATABASE_URL points to a Windows SQLite path. Remove it from Render '
                'or configure a Render Postgres database.'
            )
        database_path = Path(database_name)
        if not database_path.is_absolute():
            database_path = Path(BASE_DIR) / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        database_uri = database_url.set(database=str(database_path)).render_as_string(
            hide_password=False
        )

secret_key = os.getenv('SECRET_KEY')
jwt_secret_key = os.getenv('JWT_SECRET_KEY')
if os.getenv('RENDER_EXTERNAL_URL') and (not secret_key or not jwt_secret_key):
    raise RuntimeError('Set SECRET_KEY and JWT_SECRET_KEY in the Render service environment.')

mail_port = int(os.getenv('MAIL_PORT') or os.getenv('SMTP_PORT') or '587')
mail_use_ssl_value = os.getenv('MAIL_USE_SSL') or os.getenv('SMTP_USE_SSL')
mail_use_ssl = (
    mail_use_ssl_value.lower() in {'1', 'true', 'yes'}
    if mail_use_ssl_value
    else mail_port == 465
)
mail_use_tls_value = os.getenv('MAIL_USE_TLS') or os.getenv('SMTP_USE_TLS')
mail_use_tls = (
    mail_use_tls_value.lower() in {'1', 'true', 'yes'}
    if mail_use_tls_value
    else not mail_use_ssl
)


class Config:
    SECRET_KEY = secret_key or 'dev-secret-key-change-me'
    JWT_SECRET_KEY = jwt_secret_key or 'jwt-secret-key-change-me'
    SQLALCHEMY_DATABASE_URI = database_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_HEADERS = 'Content-Type'
    MAIL_SERVER = os.getenv('MAIL_SERVER') or os.getenv('SMTP_HOST')
    MAIL_PORT = mail_port
    MAIL_USE_TLS = mail_use_tls
    MAIL_USE_SSL = mail_use_ssl
    MAIL_USERNAME = os.getenv('MAIL_USERNAME') or os.getenv('SMTP_USER')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD') or os.getenv('SMTP_PASS')
    MAIL_DEFAULT_SENDER = (
        os.getenv('MAIL_DEFAULT_SENDER')
        or os.getenv('SMTP_FROM')
        or MAIL_USERNAME
    )
    WEBAUTHN_RP_ID = os.getenv('WEBAUTHN_RP_ID') or os.getenv('RP_ID', 'localhost')
    WEBAUTHN_RP_NAME = os.getenv('WEBAUTHN_RP_NAME') or os.getenv('RP_NAME', 'AlgoMind')
    WEBAUTHN_ORIGIN = (
        os.getenv('WEBAUTHN_ORIGIN')
        or os.getenv('APP_ORIGIN')
        or f"http://localhost:{os.getenv('PORT', '5000')}"
    )
    VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '').strip()
    VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '').strip()
    VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', 'mailto:admin@alphamind.local').strip()
