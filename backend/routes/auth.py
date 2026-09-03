from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

from backend.database import db
from backend.models import User

bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not all([full_name, email, username, password]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
    if '@' not in email:
        return jsonify({'success': False, 'message': 'Enter a valid email.'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400
    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({'success': False, 'message': 'Email or username already exists.'}), 409

    user = User(full_name=full_name, email=email, username=username, plan='Premium Plan')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({'success': True, 'token': token, 'user': user.to_public_dict()}), 201


@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({'success': True, 'token': token, 'user': user.to_public_dict()})


@bp.route('/me', methods=['GET'])
def me():
    from flask_jwt_extended import get_jwt_identity, jwt_required

    @jwt_required()
    def _me():
        user = User.query.get(int(get_jwt_identity()))
        return jsonify({'success': True, 'user': user.to_public_dict()})

    return _me()
