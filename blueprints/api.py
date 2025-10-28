from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from functools import wraps
import secrets
from datetime import datetime

# Імпорти моделей та функцій
from models import Device, City, User, DeviceHistory, db
from utils import generate_inventory_number, record_device_history

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# Простий API key authentication (для production використовувати JWT)
def api_key_required(f):
    """Декоратор для перевірки API ключа"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # Перевіряємо API key в базі (можна зберігати в User моделі)
        # Поки що використовуємо просту перевірку
        user = User.query.filter_by(username=api_key).first()
        
        if not user or not user.is_active:
            return jsonify({'error': 'Invalid API key'}), 401
        
        # Додаємо user до request context
        request.api_user = user
        return f(*args, **kwargs)
    return decorated_function

# GET /api/v1/devices - Список пристроїв
@api_bp.route('/devices', methods=['GET'])
@api_key_required
def api_get_devices():
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
    
    # Базовий запит
    if user.is_admin:
        query = Device.query
    else:
        query = Device.query.filter_by(city_id=user.city_id)
    
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
@api_key_required
def api_get_device(device_id):
    """Отримати інформацію про пристрій"""
    user = request.api_user
    device = Device.query.get_or_404(device_id)
    
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
@api_key_required
def api_create_device():
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
@api_key_required
def api_update_device(device_id):
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
@api_key_required
def api_delete_device(device_id):
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
@api_key_required
def api_get_cities():
    """Отримати список міст"""
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
@api_key_required
def api_get_stats():
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

# Обробка помилок
@api_bp.errorhandler(404)
def api_not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@api_bp.errorhandler(500)
def api_internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

