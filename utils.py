from functools import wraps
from flask import abort, request, current_app
from flask_login import current_user
from datetime import datetime
import os
import re
import shutil
import sqlite3
import json

# Дозволені розширення файлів
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Перевіряє, чи дозволене розширення файлу"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    """Декоратор для перевірки прав адміністратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def log_activity(action_description):
    """Декоратор для логування активності користувача"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.is_authenticated:
                log_user_activity(
                    current_user.id, 
                    action_description, 
                    request.remote_addr, 
                    request.url
                )
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_user_activity(user_id, action, ip_address=None, url=None):
    """Записує активність користувача в базу даних"""
    from models import UserActivity, db
    
    activity = UserActivity(
        user_id=user_id,
        action=action,
        ip_address=ip_address,
        user_agent=request.headers.get('User-Agent'),
        url=url
    )
    db.session.add(activity)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Помилка при записі активності користувача: {e}")

def record_device_history(device_id, user_id, action, field=None, old_value=None, new_value=None):
    """Записує історію змін пристрою"""
    from models import DeviceHistory, db
    
    if device_id is None:
        current_app.logger.error(f"Спроба створити запис історії з NULL device_id: action={action}, user_id={user_id}")
        return
    
    history = DeviceHistory(
        device_id=device_id,
        user_id=user_id,
        action=action,
        field=field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None
    )
    db.session.add(history)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Помилка при записі історії пристрою: {e}")

def generate_inventory_number():
    """Генерує унікальний інвентарний номер"""
    from models import Device
    
    current_year = datetime.now().year
    
    # Знаходимо останній номер за поточний рік
    last_device = Device.query.filter(
        Device.inventory_number.like(f'{current_year}-%')
    ).order_by(Device.inventory_number.desc()).first()
    
    if last_device:
        # Витягуємо номер з інвентарного номера
        match = re.search(r'(\d{4})-(\d+)', last_device.inventory_number)
        if match:
            last_number = int(match.group(2))
            new_number = last_number + 1
        else:
            new_number = 1
    else:
        new_number = 1
    
    return f"{current_year}-{new_number:04d}"

def nl2br(value):
    """Конвертує переноси рядків в HTML <br> теги"""
    if value is None:
        return ''
    return value.replace('\n', '<br>\n')