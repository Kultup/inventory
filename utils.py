from functools import wraps
from flask import abort, request, current_app
from flask_login import current_user
from datetime import datetime
import os
import re
import shutil
import sqlite3
import json
import time
from PIL import Image

# Дозволені розширення файлів
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Перевіряє, чи дозволене розширення файлу"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def optimize_image(image_path, max_width=1920, max_height=1920, quality=85):
    """
    Оптимізує зображення: зменшує розмір, стискає
    
    Args:
        image_path: Шлях до зображення
        max_width: Максимальна ширина (px)
        max_height: Максимальна висота (px)
        quality: Якість JPEG (1-100)
    
    Returns:
        True якщо успішно, False у випадку помилки
    """
    try:
        with Image.open(image_path) as img:
            # Конвертуємо RGBA в RGB
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Зберігаємо оригінальні пропорції
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # Визначаємо формат збереження
            file_ext = os.path.splitext(image_path)[1].lower()
            if file_ext == '.png':
                # PNG зберігаємо як JPEG для економії місця
                output_path = os.path.splitext(image_path)[0] + '.jpg'
                img.save(output_path, 'JPEG', quality=quality, optimize=True)
                # Видаляємо оригінальний PNG якщо створили JPG
                if output_path != image_path:
                    os.remove(image_path)
                return output_path
            else:
                # JPEG стискаємо
                img.save(image_path, 'JPEG', quality=quality, optimize=True)
                return image_path
        
        return True
    except Exception as e:
        print(f"Помилка оптимізації зображення {image_path}: {e}")
        return False

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

def record_device_history(device_id, user_id, action, field=None, old_value=None, new_value=None, device=None):
    """Записує історію змін пристрою"""
    from models import DeviceHistory, Device, db
    
    if device_id is None:
        current_app.logger.error(f"Спроба створити запис історії з NULL device_id: action={action}, user_id={user_id}")
        return
    
    # Отримуємо інформацію про пристрій, якщо вона не передана
    if device is None:
        device = Device.query.get(device_id)
    
    history = DeviceHistory(
        device_id=device_id,
        user_id=user_id,
        action=action,
        field=field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        device_name=device.name if device else None,
        device_inventory_number=device.inventory_number if device else None,
        device_type=device.type if device else None,
        device_serial_number=device.serial_number if device else None
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

def backup_database(backup_folder='backups'):
    """Створює резервну копію бази даних"""
    try:
        from models import db
        import time
        
        # Отримуємо шлях до бази даних
        db_path = db.engine.url.database
        if db_path.startswith('sqlite:///'):
            db_path = db_path.replace('sqlite:///', '')
        
        if not os.path.exists(db_path):
            current_app.logger.error(f"База даних не знайдена: {db_path}")
            return None
        
        # Створюємо директорію для backup, якщо її немає
        os.makedirs(backup_folder, exist_ok=True)
        
        # Генеруємо ім'я файлу з timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'inventory_backup_{timestamp}.db'
        backup_path = os.path.join(backup_folder, backup_filename)
        
        # Копіюємо базу даних
        shutil.copy2(db_path, backup_path)
        
        # Створюємо також SQL дамп
        dump_filename = f'inventory_dump_{timestamp}.sql'
        dump_path = os.path.join(backup_folder, dump_filename)
        
        conn = sqlite3.connect(db_path)
        with open(dump_path, 'w', encoding='utf-8') as f:
            for line in conn.iterdump():
                f.write('%s\n' % line)
        conn.close()
        
        current_app.logger.info(f"Резервна копія створена: {backup_path}")
        return {
            'backup_path': backup_path,
            'dump_path': dump_path,
            'filename': backup_filename,
            'size': os.path.getsize(backup_path),
            'timestamp': datetime.now()
        }
    except Exception as e:
        current_app.logger.error(f"Помилка при створенні резервної копії: {e}")
        return None

def cleanup_old_backups(backup_folder='backups', keep_days=30):
    """Видаляє старі резервні копії"""
    try:
        if not os.path.exists(backup_folder):
            return
        
        cutoff_time = time.time() - (keep_days * 24 * 60 * 60)
        
        for filename in os.listdir(backup_folder):
            file_path = os.path.join(backup_folder, filename)
            if os.path.isfile(file_path):
                # Перевіряємо час модифікації файлу
                if os.path.getmtime(file_path) < cutoff_time:
                    os.remove(file_path)
                    current_app.logger.info(f"Видалено старий backup: {file_path}")
    except Exception as e:
        current_app.logger.error(f"Помилка при очищенні старих backup: {e}")

def get_backup_list(backup_folder='backups'):
    """Повертає список резервних копій"""
    try:
        if not os.path.exists(backup_folder):
            return []
        
        backups = []
        for filename in os.listdir(backup_folder):
            if filename.startswith('inventory_backup_') and filename.endswith('.db'):
                file_path = os.path.join(backup_folder, filename)
                backups.append({
                    'filename': filename,
                    'path': file_path,
                    'size': os.path.getsize(file_path),
                    'timestamp': datetime.fromtimestamp(os.path.getmtime(file_path))
                })
        
        # Сортуємо за датою (нові спочатку)
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
    except Exception as e:
        current_app.logger.error(f"Помилка при отриманні списку backup: {e}")
        return []

def check_maintenance_reminders(days_before=30):
    """Перевіряє пристрої, яким потрібне обслуговування"""
    from models import Device, Notification, User, db
    from datetime import date, timedelta
    
    try:
        # Пристрої, яким обслуговування прострочене
        today = date.today()
        overdue_devices = Device.query.filter(
            Device.next_maintenance.isnot(None),
            Device.next_maintenance < today,
            Device.status != 'Списано'
        ).all()
        
        # Пристрої, яким обслуговування наближається
        soon_date = today + timedelta(days=days_before)
        soon_devices = Device.query.filter(
            Device.next_maintenance.isnot(None),
            Device.next_maintenance >= today,
            Device.next_maintenance <= soon_date,
            Device.status != 'Списано'
        ).all()
        
        # Створюємо нагадування для користувачів
        for device in overdue_devices:
            # Отримуємо всіх користувачів міста
            users = User.query.filter_by(city_id=device.city_id, is_active=True).all()
            for user in users:
                # Перевіряємо, чи немає вже такого нагадування
                existing_notification = Notification.query.filter_by(
                    user_id=user.id,
                    title=f"Обслуговування прострочене: {device.name}",
                    is_read=False
                ).first()
                
                if not existing_notification:
                    notification = Notification(
                        user_id=user.id,
                        title=f"Обслуговування прострочене: {device.name}",
                        message=f"Пристрій {device.inventory_number} потребує обслуговування. Наступна дата: {device.next_maintenance.strftime('%d.%m.%Y') if device.next_maintenance else 'Не вказано'}",
                        type='danger'
                    )
                    db.session.add(notification)
        
        # Створюємо попередження для пристроїв, яким скоро обслуговування
        for device in soon_devices:
            users = User.query.filter_by(city_id=device.city_id, is_active=True).all()
            for user in users:
                existing_notification = Notification.query.filter_by(
                    user_id=user.id,
                    title=f"Незабаром обслуговування: {device.name}",
                    is_read=False
                ).first()
                
                if not existing_notification:
                    notification = Notification(
                        user_id=user.id,
                        title=f"Незабаром обслуговування: {device.name}",
                        message=f"Пристрій {device.inventory_number} потребує обслуговування {device.next_maintenance.strftime('%d.%m.%Y') if device.next_maintenance else ''}",
                        type='warning'
                    )
                    db.session.add(notification)
        
        db.session.commit()
        return {'overdue': len(overdue_devices), 'soon': len(soon_devices)}
    except Exception as e:
        current_app.logger.error(f"Помилка при перевірці обслуговування: {e}")
        db.session.rollback()
        return {'overdue': 0, 'soon': 0}