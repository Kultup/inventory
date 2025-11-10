from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from functools import wraps
import secrets
from datetime import datetime
from sqlalchemy.orm import joinedload, selectinload

# Імпорти моделей та функцій
from models import Device, City, User, DeviceHistory, db, ApiToken
from utils import generate_inventory_number, record_device_history, verify_jwt_token, generate_jwt_token, revoke_jwt_token, refresh_access_token

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# Rate limiting для API отримується через current_app.extensions під час виконання

# JWT автентифікація для API
def jwt_required(f):
    """Декоратор для перевірки JWT токена"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Перевіряємо заголовок Authorization
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'Authorization header required'}), 401
        
        # Перевіряємо формат "Bearer <token>"
        try:
            auth_type, token = auth_header.split(' ', 1)
            if auth_type.lower() != 'bearer':
                return jsonify({'error': 'Invalid authorization type. Use Bearer token'}), 401
        except ValueError:
            return jsonify({'error': 'Invalid authorization header format'}), 401
        
        # Валідуємо токен
        user = verify_jwt_token(token)
        
        if not user:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Додаємо user до request context
        request.api_user = user
        return f(*args, **kwargs)
    return decorated_function

# Залишаємо старий декоратор для зворотної сумісності (deprecated)
def api_key_required(f):
    """Декоратор для перевірки API ключа (deprecated, використовуйте jwt_required)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Спочатку перевіряємо JWT токен
        auth_header = request.headers.get('Authorization')
        if auth_header:
            try:
                auth_type, token = auth_header.split(' ', 1)
                if auth_type.lower() == 'bearer':
                    user = verify_jwt_token(token)
                    if user:
                        request.api_user = user
                        return f(*args, **kwargs)
            except ValueError:
                pass
        
        # Fallback до старого методу (username-based)
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key or JWT token required'}), 401
        
        user = User.query.filter_by(username=api_key).first()
        
        if not user or not user.is_active:
            return jsonify({'error': 'Invalid API key'}), 401
        
        request.api_user = user
        return f(*args, **kwargs)
    return decorated_function

# GET /api/v1/devices - Список пристроїв
@api_bp.route('/devices', methods=['GET'])
@jwt_required
def api_get_devices():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Отримати список пристроїв"""
    user = request.api_user
    
    # Параметри пагінації
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Фільтри
    city_id = request.args.get('city_id', type=int)
    device_type = request.args.get('type', type=str)
    status = request.args.get('status', type=str)
    search = request.args.get('search', type=str)
    
    # Базовий запит з eager loading для city
    if user.is_admin:
        query = Device.query.options(joinedload(Device.city))
    else:
        query = Device.query.options(joinedload(Device.city)).filter_by(city_id=user.city_id)
    
    # Застосовуємо фільтри
    if city_id and user.is_admin:
        query = query.filter_by(city_id=city_id)
    if device_type:
        query = query.filter(Device.type.ilike(f'%{device_type}%'))
    if status:
        query = query.filter(Device.status.ilike(f'%{status}%'))
    if search:
        query = query.filter(
            db.or_(
                Device.name.ilike(f'%{search}%'),
                Device.serial_number.ilike(f'%{search}%'),
                Device.inventory_number.ilike(f'%{search}%')
            )
        )
    
    # Пагінація
    pagination = query.paginate(page=page, per_page=min(per_page, 100), error_out=False)
    
    devices = [{
        'id': d.id,
        'name': d.name,
        'type': d.type,
        'serial_number': d.serial_number,
        'inventory_number': d.inventory_number,
        'location': d.location,
        'status': d.status,
        'notes': d.notes,
        'city_id': d.city_id,
        'city_name': d.city.name if d.city else None,
        'created_at': d.created_at.isoformat() if d.created_at else None,
        'last_maintenance': d.last_maintenance.isoformat() if d.last_maintenance else None,
        'next_maintenance': d.next_maintenance.isoformat() if d.next_maintenance else None
    } for d in pagination.items]
    
    return jsonify({
        'devices': devices,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
        'per_page': per_page
    })

# GET /api/v1/devices/<id> - Один пристрій
@api_bp.route('/devices/<int:device_id>', methods=['GET'])
@jwt_required
def api_get_device(device_id):
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Отримати інформацію про пристрій"""
    user = request.api_user
    device = Device.query.options(joinedload(Device.city)).get_or_404(device_id)
    
    # Перевірка прав доступу
    if not user.is_admin and device.city_id != user.city_id:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'id': device.id,
        'name': device.name,
        'type': device.type,
        'serial_number': device.serial_number,
        'inventory_number': device.inventory_number,
        'location': device.location,
        'status': device.status,
        'notes': device.notes,
        'city_id': device.city_id,
        'city_name': device.city.name if device.city else None,
        'created_at': device.created_at.isoformat() if device.created_at else None,
        'last_maintenance': device.last_maintenance.isoformat() if device.last_maintenance else None,
        'next_maintenance': device.next_maintenance.isoformat() if device.next_maintenance else None,
        'maintenance_interval': device.maintenance_interval
    })

# POST /api/v1/devices - Створити пристрій
@api_bp.route('/devices', methods=['POST'])
@jwt_required
def api_create_device():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Створити новий пристрій"""
    user = request.api_user
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Валідація обов'язкових полів
    required_fields = ['name', 'type', 'serial_number']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Перевірка унікальності серійного номера
    existing_device = Device.query.filter_by(serial_number=data['serial_number']).first()
    if existing_device:
        return jsonify({'error': 'Device with this serial number already exists'}), 409
    
    # Визначаємо місто
    if user.is_admin and 'city_id' in data:
        city_id = data['city_id']
    else:
        city_id = user.city_id
    
    # Генеруємо інвентарний номер
    inventory_number = generate_inventory_number()
    
    # Створюємо пристрій
    device = Device(
        name=data['name'],
        type=data['type'],
        serial_number=data['serial_number'],
        inventory_number=inventory_number,
        location=data.get('location', ''),
        status=data.get('status', 'В роботі'),
        notes=data.get('notes', ''),
        city_id=city_id,
        maintenance_interval=data.get('maintenance_interval', 365)
    )
    
    db.session.add(device)
    db.session.flush()
    
    # Записуємо історію
    record_device_history(device.id, user.id, 'create')
    
    db.session.commit()
    
    return jsonify({
        'id': device.id,
        'inventory_number': device.inventory_number,
        'message': 'Device created successfully'
    }), 201

# PUT /api/v1/devices/<id> - Оновити пристрій
@api_bp.route('/devices/<int:device_id>', methods=['PUT'])
@jwt_required
def api_update_device(device_id):
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Оновити пристрій"""
    user = request.api_user
    device = Device.query.get_or_404(device_id)
    
    # Перевірка прав доступу
    if not user.is_admin and device.city_id != user.city_id:
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Оновлюємо поля з відстеженням змін
    updateable_fields = ['name', 'type', 'location', 'status', 'notes', 'maintenance_interval']
    
    for field in updateable_fields:
        if field in data:
            old_value = getattr(device, field)
            new_value = data[field]
            if old_value != new_value:
                record_device_history(device.id, user.id, 'update', field, old_value, new_value)
                setattr(device, field, new_value)
    
    # Оновлюємо дату обслуговування, якщо надано
    if 'last_maintenance' in data:
        try:
            device.last_maintenance = datetime.fromisoformat(data['last_maintenance']).date()
            device.update_next_maintenance()
        except:
            pass
    
    db.session.commit()
    
    return jsonify({'message': 'Device updated successfully'})

# DELETE /api/v1/devices/<id> - Видалити пристрій
@api_bp.route('/devices/<int:device_id>', methods=['DELETE'])
@jwt_required
def api_delete_device(device_id):
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Видалити пристрій"""
    user = request.api_user
    device = Device.query.get_or_404(device_id)
    
    # Перевірка прав доступу
    if not user.is_admin and device.city_id != user.city_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Записуємо історію видалення
    record_device_history(device.id, user.id, 'delete', device=device)
    
    db.session.delete(device)
    db.session.commit()
    
    return jsonify({'message': 'Device deleted successfully'})

# GET /api/v1/cities - Список міст
@api_bp.route('/cities', methods=['GET'])
@jwt_required
def api_get_cities():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Отримати список міст"""
    # Кешуємо список міст (TTL 1 година)
    try:
        cache_obj = current_app.extensions.get('cache')
        # Перевіряємо, чи це об'єкт Cache (має метод set)
        if cache_obj and hasattr(cache_obj, 'set'):
            cities = cache_obj.get('api_cities')
            if cities is None:
                cities = City.query.all()
                cache_obj.set('api_cities', cities, timeout=3600)  # 1 година
        else:
            # Кеш не доступний, отримуємо дані без кешування
            cities = City.query.all()
    except (KeyError, AttributeError, TypeError):
        # Якщо кеш не доступний, просто отримуємо дані без кешування
        cities = City.query.all()
    
    return jsonify({
        'cities': [{
            'id': c.id,
            'name': c.name,
            'created_at': c.created_at.isoformat() if c.created_at else None
        } for c in cities]
    })

# GET /api/v1/stats - Статистика
@api_bp.route('/stats', methods=['GET'])
@jwt_required
def api_get_stats():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Отримати статистику"""
    user = request.api_user
    
    if user.is_admin:
        base_query = Device.query
    else:
        base_query = Device.query.filter_by(city_id=user.city_id)
    
    stats = {
        'total_devices': base_query.count(),
        'active_devices': base_query.filter_by(status='В роботі').count(),
        'repair_devices': base_query.filter_by(status='На ремонті').count(),
        'decommissioned_devices': base_query.filter_by(status='Списано').count()
    }
    
    return jsonify(stats)

# POST /api/v1/auth/login - Генерація JWT токена
@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Генерація JWT токена для API"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    username = data.get('username')
    password = data.get('password')
    token_name = data.get('token_name')
    expires_in_days = data.get('expires_in_days', 30)
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    # Перевіряємо користувача
    from werkzeug.security import check_password_hash
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.is_active or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    try:
        # Генеруємо токен
        access_token, refresh_token, token_id = generate_jwt_token(
            user.id,
            token_name=token_name,
            expires_in_days=expires_in_days
        )
        
        return jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_id': token_id,
            'expires_in_days': expires_in_days,
            'user': {
                'id': user.id,
                'username': user.username,
                'is_admin': user.is_admin
            }
        }), 200
    except Exception as e:
        current_app.logger.error(f"Помилка при генерації токена: {e}")
        return jsonify({'error': 'Failed to generate token'}), 500

# POST /api/v1/auth/refresh - Оновлення access token
@api_bp.route('/auth/refresh', methods=['POST'])
def api_refresh():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Оновлення access token через refresh token"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({'error': 'Refresh token required'}), 400
    
    try:
        new_access_token = refresh_access_token(refresh_token)
        
        if not new_access_token:
            return jsonify({'error': 'Invalid or expired refresh token'}), 401
        
        return jsonify({
            'access_token': new_access_token
        }), 200
    except Exception as e:
        current_app.logger.error(f"Помилка при оновленні токена: {e}")
        return jsonify({'error': 'Failed to refresh token'}), 500

# POST /api/v1/auth/revoke - Відкликання токена
@api_bp.route('/auth/revoke', methods=['POST'])
@jwt_required
def api_revoke():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Відкликання JWT токена"""
    data = request.get_json()
    user = request.api_user
    
    token_id = data.get('token_id')
    
    if not token_id:
        return jsonify({'error': 'Token ID required'}), 400
    
    # Перевіряємо, чи токен належить користувачу
    api_token = ApiToken.query.filter_by(
        token_id=token_id,
        user_id=user.id
    ).first()
    
    if not api_token:
        return jsonify({'error': 'Token not found'}), 404
    
    try:
        if revoke_jwt_token(token_id):
            return jsonify({'message': 'Token revoked successfully'}), 200
        else:
            return jsonify({'error': 'Failed to revoke token'}), 500
    except Exception as e:
        current_app.logger.error(f"Помилка при відкликанні токена: {e}")
        return jsonify({'error': 'Failed to revoke token'}), 500

# GET /api/v1/auth/tokens - Список токенів користувача
@api_bp.route('/auth/tokens', methods=['GET'])
@jwt_required
def api_list_tokens():
    # Rate limiting застосовується через глобальні обмеження в app.py
    """Отримати список токенів користувача"""
    user = request.api_user
    
    tokens = ApiToken.query.filter_by(
        user_id=user.id
    ).order_by(ApiToken.created_at.desc()).all()
    
    return jsonify({
        'tokens': [{
            'id': t.id,
            'token_id': t.token_id,
            'name': t.name,
            'is_active': t.is_active,
            'expires_at': t.expires_at.isoformat() if t.expires_at else None,
            'last_used_at': t.last_used_at.isoformat() if t.last_used_at else None,
            'created_at': t.created_at.isoformat() if t.created_at else None
        } for t in tokens]
    }), 200

# Обробка помилок API
@api_bp.errorhandler(404)
def api_not_found(error):
    """Обробка помилки 404 для API"""
    return jsonify({
        'error': 'Resource not found',
        'message': 'Запитаний ресурс не знайдено',
        'status_code': 404
    }), 404

@api_bp.errorhandler(403)
def api_forbidden(error):
    """Обробка помилки 403 для API"""
    return jsonify({
        'error': 'Forbidden',
        'message': 'У вас немає прав доступу до цього ресурсу',
        'status_code': 403
    }), 403

@api_bp.errorhandler(500)
def api_internal_error(error):
    """Обробка помилки 500 для API"""
    current_app.logger.error(f'API Server Error: {error}', exc_info=True)
    return jsonify({
        'error': 'Internal server error',
        'message': 'Сталася несподівана помилка на сервері',
        'status_code': 500
    }), 500

@api_bp.errorhandler(400)
def api_bad_request(error):
    """Обробка помилки 400 для API"""
    return jsonify({
        'error': 'Bad request',
        'message': 'Невірний формат запиту',
        'status_code': 400
    }), 400

@api_bp.errorhandler(429)
def api_rate_limit_exceeded(error):
    """Обробка помилки 429 для API (rate limit exceeded)"""
    return jsonify({
        'error': 'Too many requests',
        'message': 'Перевищено ліміт запитів. Спробуйте пізніше.',
        'status_code': 429
    }), 429

