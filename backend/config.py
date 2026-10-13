import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(BASE_DIR, '.env'))

database_uri = os.getenv(
    'DATABASE_URL',
    'sqlite:///' + os.path.join(BASE_DIR, 'database', 'algotrade.db')
)
if database_uri.startswith('postgres://'):
    database_uri = database_uri.replace('postgres://', 'postgresql://', 1)

secret_key = os.getenv('SECRET_KEY')
jwt_secret_key = os.getenv('JWT_SECRET_KEY')
if os.getenv('RENDER_EXTERNAL_URL') and (not secret_key or not jwt_secret_key):
    raise RuntimeError('Set SECRET_KEY and JWT_SECRET_KEY in the Render service environment.')


class Config:
    SECRET_KEY = secret_key or 'dev-secret-key-change-me'
    JWT_SECRET_KEY = jwt_secret_key or 'jwt-secret-key-change-me'
    SQLALCHEMY_DATABASE_URI = database_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_HEADERS = 'Content-Type'
