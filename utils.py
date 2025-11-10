from functools import wraps
from flask import abort, request, current_app
from flask_login import current_user
from datetime import datetime, timedelta
import os
import re
import shutil
import sqlite3
import json
import time
import requests
import secrets
import jwt
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

def get_telegram_settings():
    """
    Отримує налаштування Telegram з бази даних або конфігурації
    
    Returns:
        dict: Словник з налаштуваннями (bot_token, chat_id, enabled)
    """
    from models import SystemSettings, db
    
    try:
        # Спочатку пробуємо отримати з бази даних
        bot_token_setting = SystemSettings.query.filter_by(key='telegram_bot_token').first()
        chat_id_setting = SystemSettings.query.filter_by(key='telegram_chat_id').first()
        enabled_setting = SystemSettings.query.filter_by(key='telegram_enabled').first()
        
        bot_token = bot_token_setting.value if bot_token_setting else None
        chat_id = chat_id_setting.value if chat_id_setting else None
        enabled = enabled_setting.value.lower() == 'true' if enabled_setting else False
        
        # Якщо в базі даних немає, використовуємо конфігурацію
        if not bot_token:
            bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN', '')
        if not chat_id:
            chat_id = current_app.config.get('TELEGRAM_CHAT_ID', '')
        if not enabled_setting:
            enabled = current_app.config.get('TELEGRAM_ENABLED', False)
        
        return {
            'bot_token': bot_token,
            'chat_id': chat_id,
            'enabled': enabled
        }
    except Exception as e:
        current_app.logger.error(f"Помилка при отриманні Telegram налаштувань: {e}")
        # Fallback до конфігурації
        return {
            'bot_token': current_app.config.get('TELEGRAM_BOT_TOKEN', ''),
            'chat_id': current_app.config.get('TELEGRAM_CHAT_ID', ''),
            'enabled': current_app.config.get('TELEGRAM_ENABLED', False)
        }

def save_telegram_settings(bot_token, chat_id, enabled):
    """
    Зберігає налаштування Telegram в базу даних
    
    Args:
        bot_token: Токен бота
        chat_id: ID чату
        enabled: Увімкнено/вимкнено
    
    Returns:
        bool: True якщо успішно збережено
    """
    from models import SystemSettings, db
    
    try:
        # Зберігаємо токен бота
        token_setting = SystemSettings.query.filter_by(key='telegram_bot_token').first()
        if token_setting:
            token_setting.value = bot_token
            token_setting.updated_at = datetime.utcnow()
        else:
            token_setting = SystemSettings(
                key='telegram_bot_token',
                value=bot_token,
                description='Telegram Bot Token для нагадувань'
            )
            db.session.add(token_setting)
        
        # Зберігаємо chat ID
        chat_setting = SystemSettings.query.filter_by(key='telegram_chat_id').first()
        if chat_setting:
            chat_setting.value = chat_id
            chat_setting.updated_at = datetime.utcnow()
        else:
            chat_setting = SystemSettings(
                key='telegram_chat_id',
                value=chat_id,
                description='Telegram Chat ID для нагадувань'
            )
            db.session.add(chat_setting)
        
        # Зберігаємо статус увімкнення
        enabled_setting = SystemSettings.query.filter_by(key='telegram_enabled').first()
        if enabled_setting:
            enabled_setting.value = 'true' if enabled else 'false'
            enabled_setting.updated_at = datetime.utcnow()
        else:
            enabled_setting = SystemSettings(
                key='telegram_enabled',
                value='true' if enabled else 'false',
                description='Увімкнено Telegram нагадування'
            )
            db.session.add(enabled_setting)
        
        db.session.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Помилка при збереженні Telegram налаштувань: {e}")
        db.session.rollback()
        return False

def test_telegram_connection(bot_token=None, chat_id=None):
    """
    Тестує з'єднання з Telegram ботом
    
    Args:
        bot_token: Токен бота (якщо не вказано, використовується з налаштувань)
        chat_id: ID чату (якщо не вказано, використовується з налаштувань)
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        settings = get_telegram_settings()
        
        test_token = bot_token or settings['bot_token']
        test_chat_id = chat_id or settings['chat_id']
        
        if not test_token:
            return {'success': False, 'message': 'Токен бота не вказано'}
        
        if not test_chat_id:
            return {'success': False, 'message': 'Chat ID не вказано'}
        
        # Тестове повідомлення
        test_message = "🧪 <b>Тестове повідомлення</b>\n\nЦе тестове повідомлення для перевірки налаштувань Telegram бота."
        
        # URL для відправки повідомлення
        url = f"https://api.telegram.org/bot{test_token}/sendMessage"
        
        # Параметри запиту
        payload = {
            'chat_id': test_chat_id,
            'text': test_message,
            'parse_mode': 'HTML'
        }
        
        # Відправляємо запит
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get('ok'):
            return {'success': True, 'message': 'Тестове повідомлення успішно відправлено!'}
        else:
            error_desc = result.get('description', 'Невідома помилка')
            return {'success': False, 'message': f'Помилка: {error_desc}'}
            
    except requests.exceptions.RequestException as e:
        return {'success': False, 'message': f'Помилка з\'єднання: {str(e)}'}
    except Exception as e:
        current_app.logger.error(f"Помилка при тестуванні Telegram з'єднання: {e}")
        return {'success': False, 'message': f'Несподівана помилка: {str(e)}'}

def send_telegram_notification(message, chat_id=None):
    """
    Відправляє повідомлення в Telegram через бота
    
    Args:
        message: Текст повідомлення
        chat_id: ID чату (якщо не вказано, використовується з налаштувань)
    
    Returns:
        bool: True якщо повідомлення відправлено, False якщо помилка
    """
    try:
        settings = get_telegram_settings()
        
        if not settings['enabled'] or not settings['bot_token']:
            current_app.logger.debug("Telegram нагадування вимкнено або токен не налаштовано")
            return False
        
        # Використовуємо chat_id з параметра або з налаштувань
        target_chat_id = chat_id or settings['chat_id']
        if not target_chat_id:
            current_app.logger.warning("Telegram chat_id не вказано")
            return False
        
        # URL для відправки повідомлення
        url = f"https://api.telegram.org/bot{settings['bot_token']}/sendMessage"
        
        # Параметри запиту
        payload = {
            'chat_id': target_chat_id,
            'text': message,
            'parse_mode': 'HTML'  # Дозволяє використовувати HTML форматування
        }
        
        # Відправляємо запит
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get('ok'):
            current_app.logger.info(f"Telegram повідомлення успішно відправлено в чат {target_chat_id}")
            return True
        else:
            current_app.logger.error(f"Помилка відправки Telegram повідомлення: {result.get('description')}")
            return False
            
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Помилка при відправці Telegram повідомлення: {e}")
        return False
    except Exception as e:
        current_app.logger.error(f"Несподівана помилка при відправці Telegram повідомлення: {e}")
        return False

def send_test_maintenance_notification():
    """
    Відправляє тестове нагадування про обслуговування для перевірки Telegram бота
    Використовується для тестування налаштувань
    """
    from datetime import date, timedelta
    
    try:
        settings = get_telegram_settings()
        
        if not settings['enabled'] or not settings['bot_token']:
            current_app.logger.warning("Telegram нагадування вимкнено або токен не налаштовано")
            return False
        
        if not settings['chat_id']:
            current_app.logger.warning("Telegram chat_id не вказано")
            return False
        
        # Отримуємо першого активного користувача для тесту
        from models import User, Device, City, db
        test_user = User.query.filter_by(is_active=True).first()
        
        if not test_user:
            current_app.logger.warning("Не знайдено активних користувачів для тестового нагадування")
            return False
        
        # Створюємо тестове повідомлення
        today = date.today()
        test_date = today - timedelta(days=5)  # Прострочене на 5 днів
        
        message = (
            f"🧪 <b>ТЕСТОВЕ НАГАДУВАННЯ</b>\n\n"
            f"👤 <b>Користувач:</b> {test_user.username}\n"
            f"📦 <b>Пристрій:</b> Тестовий пристрій (для перевірки налаштувань)\n"
            f"🔢 <b>Інвентарний номер:</b> TEST-0001\n"
            f"📅 <b>Дата обслуговування:</b> {test_date.strftime('%d.%m.%Y')}\n"
            f"⏰ <b>Прострочено:</b> 5 дн.\n"
            f"📍 <b>Місцезнаходження:</b> Тестова локація\n"
            f"🏢 <b>Місто:</b> {test_user.city.name if test_user.city else 'Не вказано'}\n\n"
            f"<i>Це тестове повідомлення для перевірки налаштувань Telegram бота.</i>"
        )
        
        # Відправляємо повідомлення
        if send_telegram_notification(message):
            current_app.logger.info("Тестове нагадування про обслуговування успішно відправлено")
            return True
        else:
            current_app.logger.error("Помилка відправки тестового нагадування")
            return False
            
    except Exception as e:
        current_app.logger.error(f"Помилка при відправці тестового нагадування: {e}", exc_info=True)
        return False

def send_test_device_notification(device_id):
    """
    Відправляє тестове нагадування про обслуговування для конкретного пристрою
    Використовується для тестування нагадувань для конкретного пристрою
    
    Args:
        device_id: ID пристрою
    """
    from datetime import date, timedelta
    
    try:
        settings = get_telegram_settings()
        
        if not settings['enabled'] or not settings['bot_token']:
            current_app.logger.warning("Telegram нагадування вимкнено або токен не налаштовано")
            return False
        
        if not settings['chat_id']:
            current_app.logger.warning("Telegram chat_id не вказано")
            return False
        
        # Отримуємо пристрій з бази даних
        from models import Device, User, db
        from sqlalchemy.orm import joinedload
        device = Device.query.options(
            joinedload(Device.city)
        ).get(device_id)
        
        if not device:
            current_app.logger.warning(f"Пристрій з ID {device_id} не знайдено")
            return False
        
        # Отримуємо активних користувачів міста пристрою
        users = User.query.filter_by(city_id=device.city_id, is_active=True).all()
        
        if not users:
            current_app.logger.warning(f"Не знайдено активних користувачів для міста пристрою {device_id}")
            return False
        
        # Використовуємо першого користувача для тесту
        test_user = users[0]
        
        # Створюємо тестове повідомлення на основі реального пристрою
        today = date.today()
        if device.next_maintenance:
            days_overdue = (today - device.next_maintenance).days if device.next_maintenance < today else 0
            days_until = (device.next_maintenance - today).days if device.next_maintenance >= today else 0
        else:
            days_overdue = 5  # Тестове значення
            days_until = 0
        
        if days_overdue > 0:
            message = (
                f"🧪 <b>ТЕСТОВЕ НАГАДУВАННЯ</b>\n\n"
                f"👤 <b>Користувач:</b> {test_user.username}\n"
                f"📦 <b>Пристрій:</b> {device.name}\n"
                f"🔢 <b>Інвентарний номер:</b> {device.inventory_number}\n"
                f"📅 <b>Дата обслуговування:</b> {device.next_maintenance.strftime('%d.%m.%Y') if device.next_maintenance else 'Не вказано'}\n"
                f"⏰ <b>Прострочено:</b> {days_overdue} дн.\n"
                f"📍 <b>Місцезнаходження:</b> {device.location or 'Не вказано'}\n"
                f"🏢 <b>Місто:</b> {device.city.name if device.city else 'Не вказано'}\n\n"
                f"<i>Це тестове повідомлення для перевірки нагадувань Telegram бота для пристрою {device.inventory_number}.</i>"
            )
        else:
            message = (
                f"🧪 <b>ТЕСТОВЕ НАГАДУВАННЯ</b>\n\n"
                f"👤 <b>Користувач:</b> {test_user.username}\n"
                f"📦 <b>Пристрій:</b> {device.name}\n"
                f"🔢 <b>Інвентарний номер:</b> {device.inventory_number}\n"
                f"📅 <b>Дата обслуговування:</b> {device.next_maintenance.strftime('%d.%m.%Y') if device.next_maintenance else 'Не вказано'}\n"
                f"⏰ <b>Залишилось днів:</b> {days_until}\n"
                f"📍 <b>Місцезнаходження:</b> {device.location or 'Не вказано'}\n"
                f"🏢 <b>Місто:</b> {device.city.name if device.city else 'Не вказано'}\n\n"
                f"<i>Це тестове повідомлення для перевірки нагадувань Telegram бота для пристрою {device.inventory_number}.</i>"
            )
        
        # Відправляємо повідомлення
        if send_telegram_notification(message):
            current_app.logger.info(f"Тестове нагадування про обслуговування для пристрою {device_id} успішно відправлено")
            return True
        else:
            current_app.logger.error(f"Помилка відправки тестового нагадування для пристрою {device_id}")
            return False
            
    except Exception as e:
        current_app.logger.error(f"Помилка при відправці тестового нагадування для пристрою {device_id}: {e}", exc_info=True)
        return False

def check_additional_reminders():
    """
    Перевіряє додаткові ситуації та відправляє інформативні нагадування в Telegram.
    
    Типи нагадувань:
    - Пристрої без фото
    - Пристрої без призначеного співробітника
    - Пристрої з великими витратами на ремонт
    - Пристрої на ремонті довше 30 днів
    - Пристрої без фінансової інформації
    - Пристрої, які не оновлювались довгий час
    """
    from models import Device, User, db, DevicePhoto, RepairExpense, DeviceHistory
    from datetime import date, timedelta, datetime
    from sqlalchemy.orm import joinedload
    from sqlalchemy import func
    
    try:
        settings = get_telegram_settings()
        if not settings['enabled']:
            return {'notifications_sent': 0}
        
        today = date.today()
        notifications_sent = 0
        messages = []
        
        # 1. Пристрої без фото (якщо є пристрої без фото)
        devices_without_photos = Device.query.outerjoin(DevicePhoto).filter(
            DevicePhoto.id.is_(None),
            Device.status != 'Списано'
        ).options(joinedload(Device.city)).limit(10).all()
        
        if devices_without_photos:
            devices_list = ', '.join([f"{d.inventory_number} ({d.name})" for d in devices_without_photos[:5]])
            if len(devices_without_photos) > 5:
                devices_list += f" та ще {len(devices_without_photos) - 5} пристроїв"
            
            message = (
                f"📸 <b>Пристрої без фото</b>\n\n"
                f"Знайдено <b>{len(devices_without_photos)}</b> пристроїв без фотографій:\n"
                f"{devices_list}\n\n"
                f"<i>Рекомендується додати фото для повноти інформації.</i>"
            )
            messages.append(message)
        
        # 2. Пристрої без призначеного співробітника (якщо є такі)
        devices_without_employee = Device.query.filter(
            Device.assigned_to_employee_id.is_(None),
            Device.status == 'В роботі'
        ).options(joinedload(Device.city)).limit(10).all()
        
        if devices_without_employee:
            devices_list = ', '.join([f"{d.inventory_number} ({d.name})" for d in devices_without_employee[:5]])
            if len(devices_without_employee) > 5:
                devices_list += f" та ще {len(devices_without_employee) - 5} пристроїв"
            
            message = (
                f"👤 <b>Пристрої без призначеного співробітника</b>\n\n"
                f"Знайдено <b>{len(devices_without_employee)}</b> пристроїв без призначеного співробітника:\n"
                f"{devices_list}\n\n"
                f"<i>Рекомендується призначити відповідальну особу.</i>"
            )
            messages.append(message)
        
        # 3. Пристрої з великими витратами на ремонт (більше 50% від вартості покупки)
        devices_high_repair = Device.query.filter(
            Device.purchase_price.isnot(None),
            Device.purchase_price > 0,
            Device.status != 'Списано'
        ).options(joinedload(Device.city), joinedload(Device.repair_expenses)).all()
        
        high_repair_devices = []
        for device in devices_high_repair:
            if device.purchase_price and device.total_repair_expenses > 0:
                repair_percentage = (device.total_repair_expenses / float(device.purchase_price)) * 100
                if repair_percentage > 50:
                    high_repair_devices.append((device, repair_percentage))
        
        if high_repair_devices:
            devices_list = []
            for device, percentage in high_repair_devices[:5]:
                devices_list.append(f"{device.inventory_number} ({device.name}) - {percentage:.1f}%")
            devices_text = '\n'.join(devices_list)
            if len(high_repair_devices) > 5:
                devices_text += f"\nта ще {len(high_repair_devices) - 5} пристроїв"
            
            message = (
                f"💰 <b>Пристрої з високими витратами на ремонт</b>\n\n"
                f"Знайдено <b>{len(high_repair_devices)}</b> пристроїв, де витрати на ремонт перевищують 50% від вартості покупки:\n"
                f"{devices_text}\n\n"
                f"<i>Рекомендується перевірити доцільність подальшого використання.</i>"
            )
            messages.append(message)
        
        # 4. Пристрої на ремонті довше 30 днів
        # Шукаємо пристрої зі статусом "На ремонті", які не оновлювались довгий час
        # Використовуємо DeviceHistory для визначення, коли пристрій був переведений на ремонт
        thirty_days_ago = today - timedelta(days=30)
        thirty_days_ago_datetime = datetime.combine(thirty_days_ago, datetime.min.time())
        
        # Знаходимо пристрої на ремонті, які не мають недавніх оновлень
        devices_long_repair = Device.query.filter(
            Device.status == 'На ремонті',
            Device.status != 'Списано'
        ).options(joinedload(Device.city)).all()
        
        # Фільтруємо ті, які не оновлювались останні 30 днів (через DeviceHistory)
        long_repair_filtered = []
        for device in devices_long_repair:
            # Перевіряємо останню активність
            last_history = db.session.query(func.max(DeviceHistory.timestamp)).filter_by(device_id=device.id).scalar()
            if not last_history or last_history < thirty_days_ago_datetime:
                long_repair_filtered.append(device)
        
        devices_long_repair = long_repair_filtered[:10]
        
        if devices_long_repair:
            devices_list = ', '.join([f"{d.inventory_number} ({d.name})" for d in devices_long_repair[:5]])
            if len(devices_long_repair) > 5:
                devices_list += f" та ще {len(devices_long_repair) - 5} пристроїв"
            
            message = (
                f"🔧 <b>Пристрої на ремонті довше 30 днів</b>\n\n"
                f"Знайдено <b>{len(devices_long_repair)}</b> пристроїв, які знаходяться на ремонті більше 30 днів:\n"
                f"{devices_list}\n\n"
                f"<i>Рекомендується перевірити статус ремонту або оновити інформацію.</i>"
            )
            messages.append(message)
        
        # 5. Пристрої без фінансової інформації (дата покупки або вартість)
        devices_no_financial = Device.query.filter(
            db.or_(
                Device.purchase_date.is_(None),
                Device.purchase_price.is_(None)
            ),
            Device.status != 'Списано'
        ).options(joinedload(Device.city)).limit(10).all()
        
        if devices_no_financial:
            devices_list = ', '.join([f"{d.inventory_number} ({d.name})" for d in devices_no_financial[:5]])
            if len(devices_no_financial) > 5:
                devices_list += f" та ще {len(devices_no_financial) - 5} пристроїв"
            
            message = (
                f"💵 <b>Пристрої без фінансової інформації</b>\n\n"
                f"Знайдено <b>{len(devices_no_financial)}</b> пристроїв без дати покупки або вартості:\n"
                f"{devices_list}\n\n"
                f"<i>Рекомендується додати фінансову інформацію для повного обліку.</i>"
            )
            messages.append(message)
        
        # Відправляємо всі нагадування (якщо є)
        if messages:
            # Об'єднуємо всі повідомлення в одне
            combined_message = "📋 <b>Інформаційні нагадування</b>\n\n" + "\n\n---\n\n".join(messages)
            
            if send_telegram_notification(combined_message):
                notifications_sent = 1
                current_app.logger.info(f"Відправлено інформаційні нагадування: {len(messages)} типів")
        
        return {'notifications_sent': notifications_sent, 'types': len(messages)}
    except Exception as e:
        current_app.logger.error(f"Помилка при перевірці додаткових нагадувань: {e}", exc_info=True)
        return {'notifications_sent': 0, 'types': 0}

def check_maintenance_reminders(days_before=30):
    """
    Перевіряє пристрої, яким потрібне обслуговування та відправляє нагадування в Telegram.
    
    Логіка нагадувань:
    - Пристрої з простроченим обслуговуванням (next_maintenance < today) - відправляються щодня
    - Пристрої, яким час обслуговування настав сьогодні (next_maintenance == today) - відправляються щодня
    - Пристрої, яким скоро обслуговування (next_maintenance <= today + days_before) - відправляються один раз
    """
    from models import Device, User, db, SystemSettings
    from datetime import date, timedelta
    from sqlalchemy.orm import joinedload
    
    try:
        # Перевіряємо, чи увімкнено Telegram нагадування
        settings = get_telegram_settings()
        if not settings['enabled']:
            current_app.logger.debug("Telegram нагадування вимкнено")
            return {'overdue': 0, 'soon': 0, 'notifications_sent': 0}
        
        today = date.today()
        notifications_sent = 0
        
        # Пристрої, яким обслуговування прострочене або час вже вийшов (включаючи сьогодні)
        overdue_devices = Device.query.options(
            joinedload(Device.city)
        ).filter(
            Device.next_maintenance.isnot(None),
            Device.next_maintenance <= today,  # Включаємо сьогоднішню дату
            Device.status != 'Списано'
        ).all()
        
        # Пристрої, яким обслуговування наближається (але ще не настав час)
        soon_date = today + timedelta(days=days_before)
        soon_devices = Device.query.options(
            joinedload(Device.city)
        ).filter(
            Device.next_maintenance.isnot(None),
            Device.next_maintenance > today,  # Тільки майбутні дати
            Device.next_maintenance <= soon_date,
            Device.status != 'Списано'
        ).all()
        
        # Обробка прострочених пристроїв або пристроїв, яким час обслуговування вже вийшов
        for device in overdue_devices:
            # Отримуємо всіх активних користувачів міста
            users = User.query.filter_by(city_id=device.city_id, is_active=True).all()
            
            if not users:
                continue
            
            # Визначаємо, скільки днів прострочено
            days_overdue = (today - device.next_maintenance).days
            
            # Формуємо повідомлення залежно від ситуації
            if days_overdue == 0:
                # Час обслуговування настав сьогодні
                message = (
                    f"⏰ <b>Час обслуговування настав!</b>\n\n"
                    f"👤 <b>Користувач:</b> {users[0].username}\n"
                    f"📦 <b>Пристрій:</b> {device.name}\n"
                    f"🔢 <b>Інвентарний номер:</b> {device.inventory_number}\n"
                    f"📅 <b>Дата обслуговування:</b> {device.next_maintenance.strftime('%d.%m.%Y')} (сьогодні)\n"
                    f"📍 <b>Місцезнаходження:</b> {device.location or 'Не вказано'}\n"
                    f"🏢 <b>Місто:</b> {device.city.name if device.city else 'Не вказано'}\n\n"
                    f"<b>⚠️ Необхідно провести обслуговування пристрою!</b>"
                )
            else:
                # Обслуговування прострочене
                message = (
                    f"🔴 <b>Обслуговування прострочене!</b>\n\n"
                    f"👤 <b>Користувач:</b> {users[0].username}\n"
                    f"📦 <b>Пристрій:</b> {device.name}\n"
                    f"🔢 <b>Інвентарний номер:</b> {device.inventory_number}\n"
                    f"📅 <b>Дата обслуговування:</b> {device.next_maintenance.strftime('%d.%m.%Y')}\n"
                    f"⏰ <b>Прострочено:</b> {days_overdue} дн.\n"
                    f"📍 <b>Місцезнаходження:</b> {device.location or 'Не вказано'}\n"
                    f"🏢 <b>Місто:</b> {device.city.name if device.city else 'Не вказано'}\n\n"
                    f"<b>⚠️ Необхідно негайно провести обслуговування пристрою!</b>"
                )
            
            # Відправляємо нагадування в групу (одне повідомлення на пристрій)
            if send_telegram_notification(message):
                notifications_sent += 1
                current_app.logger.info(
                    f"Відправлено нагадування про обслуговування для пристрою {device.inventory_number} "
                    f"(прострочено: {days_overdue} дн.)"
                )
        
        # Обробка пристроїв, яким скоро обслуговування
        for device in soon_devices:
            users = User.query.filter_by(city_id=device.city_id, is_active=True).all()
            
            if not users:
                continue
            
            days_until = (device.next_maintenance - today).days
            
            # Перевіряємо, чи вже відправляли нагадування для цього пристрою
            # Використовуємо SystemSettings для зберігання інформації про відправлені нагадування
            reminder_key = f"maintenance_reminder_{device.id}_{device.next_maintenance}"
            existing_reminder = SystemSettings.query.filter_by(key=reminder_key).first()
            
            # Якщо нагадування вже відправлялось для цієї дати, пропускаємо
            if existing_reminder:
                continue
            
            message = (
                f"⚠️ <b>Незабаром обслуговування!</b>\n\n"
                f"👤 <b>Користувач:</b> {users[0].username}\n"
                f"📦 <b>Пристрій:</b> {device.name}\n"
                f"🔢 <b>Інвентарний номер:</b> {device.inventory_number}\n"
                f"📅 <b>Дата обслуговування:</b> {device.next_maintenance.strftime('%d.%m.%Y')}\n"
                f"⏰ <b>Залишилось днів:</b> {days_until}\n"
                f"📍 <b>Місцезнаходження:</b> {device.location or 'Не вказано'}\n"
                f"🏢 <b>Місто:</b> {device.city.name if device.city else 'Не вказано'}\n\n"
                f"<i>Підготуйте пристрій до обслуговування.</i>"
            )
            
            # Відправляємо нагадування
            if send_telegram_notification(message):
                # Зберігаємо інформацію про відправлене нагадування
                reminder_setting = SystemSettings(
                    key=reminder_key,
                    value='sent',
                    description=f'Нагадування про обслуговування для пристрою {device.inventory_number} на {device.next_maintenance}'
                )
                db.session.add(reminder_setting)
                db.session.commit()
                
                notifications_sent += 1
                current_app.logger.info(
                    f"Відправлено попереднє нагадування про обслуговування для пристрою {device.inventory_number} "
                    f"(залишилось: {days_until} дн.)"
                )
        
        # Очищаємо старі записи про нагадування (старіші за 60 днів)
        old_date = today - timedelta(days=60)
        old_datetime = datetime.combine(old_date, datetime.min.time())
        old_reminders = SystemSettings.query.filter(
            SystemSettings.key.like('maintenance_reminder_%'),
            SystemSettings.created_at < old_datetime
        ).all()
        for old_reminder in old_reminders:
            db.session.delete(old_reminder)
        if old_reminders:
            db.session.commit()
        
        current_app.logger.info(
            f"Перевірка обслуговування завершена. "
            f"Прострочено/час вийшов: {len(overdue_devices)}, Скоро: {len(soon_devices)}, "
            f"Повідомлень відправлено: {notifications_sent}"
        )
        
        return {
            'overdue': len(overdue_devices), 
            'soon': len(soon_devices), 
            'notifications_sent': notifications_sent
        }
    except Exception as e:
        current_app.logger.error(f"Помилка при перевірці обслуговування: {e}", exc_info=True)
        db.session.rollback()
        return {'overdue': 0, 'soon': 0, 'notifications_sent': 0}

# JWT функції для API автентифікації
def generate_jwt_token(user_id, token_name=None, expires_in_days=30):
    """
    Генерує JWT токен для користувача
    
    Args:
        user_id: ID користувача
        token_name: Назва токена (опціонально)
        expires_in_days: Термін дії токена в днях (за замовчуванням 30)
    
    Returns:
        tuple: (access_token, refresh_token, token_id)
    """
    from models import ApiToken, db
    
    # Генеруємо унікальний ID для токена
    token_id = secrets.token_urlsafe(32)
    
    # Термін дії токена
    expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    refresh_expires_at = datetime.utcnow() + timedelta(days=expires_in_days * 2)
    now = datetime.utcnow()
    
    # Секретний ключ з конфігурації
    secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key')
    
    # Створюємо access token
    access_payload = {
        'user_id': user_id,
        'jti': token_id,  # JWT ID
        'type': 'access',
        'exp': expires_at,
        'iat': now
    }
    access_token = jwt.encode(access_payload, secret_key, algorithm='HS256')
    
    # Створюємо refresh token
    refresh_token_id = secrets.token_urlsafe(32)
    refresh_payload = {
        'user_id': user_id,
        'jti': refresh_token_id,
        'type': 'refresh',
        'access_jti': token_id,  # Посилання на access token
        'exp': refresh_expires_at,
        'iat': now
    }
    refresh_token = jwt.encode(refresh_payload, secret_key, algorithm='HS256')
    
    # Зберігаємо токен в базі даних
    api_token = ApiToken(
        user_id=user_id,
        token_id=token_id,
        name=token_name or f'Token {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}',
        expires_at=expires_at,
        is_active=True
    )
    db.session.add(api_token)
    
    # Зберігаємо refresh token (опціонально, можна зберігати в окремій таблиці)
    refresh_token_record = ApiToken(
        user_id=user_id,
        token_id=refresh_token_id,
        name=f'Refresh token for {token_id}',
        expires_at=refresh_expires_at,
        is_active=True
    )
    db.session.add(refresh_token_record)
    
    try:
        db.session.commit()
        return access_token, refresh_token, token_id
    except Exception as e:
        current_app.logger.error(f"Помилка при збереженні токена: {e}")
        db.session.rollback()
        raise

def verify_jwt_token(token):
    """
    Валідує JWT токен та повертає користувача
    
    Args:
        token: JWT токен
    
    Returns:
        User: Користувач або None якщо токен невалідний
    """
    from models import User, ApiToken, db
    
    secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key')
    
    try:
        # Декодуємо токен
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        
        # Перевіряємо тип токена
        if payload.get('type') != 'access':
            return None
        
        # Перевіряємо наявність токена в базі
        token_id = payload.get('jti')
        api_token = ApiToken.query.filter_by(
            token_id=token_id,
            is_active=True
        ).first()
        
        if not api_token:
            return None
        
        # Перевіряємо термін дії
        if api_token.is_expired():
            api_token.is_active = False
            db.session.commit()
            return None
        
        # Оновлюємо час останнього використання
        api_token.last_used_at = datetime.utcnow()
        db.session.commit()
        
        # Отримуємо користувача
        user = User.query.get(payload.get('user_id'))
        
        if not user or not user.is_active:
            return None
        
        return user
        
    except jwt.ExpiredSignatureError:
        # Токен прострочений
        return None
    except jwt.InvalidTokenError:
        # Невірний токен
        return None
    except Exception as e:
        current_app.logger.error(f"Помилка при валідації токена: {e}")
        return None

def revoke_jwt_token(token_id):
    """
    Відкликає JWT токен
    
    Args:
        token_id: ID токена (jti)
    
    Returns:
        bool: True якщо токен відкликано, False якщо не знайдено
    """
    from models import ApiToken, db
    
    try:
        api_token = ApiToken.query.filter_by(token_id=token_id).first()
        if api_token:
            api_token.is_active = False
            db.session.commit()
            return True
        return False
    except Exception as e:
        current_app.logger.error(f"Помилка при відкликанні токена: {e}")
        db.session.rollback()
        return False

def refresh_access_token(refresh_token):
    """
    Генерує новий access token на основі refresh token
    
    Args:
        refresh_token: Refresh JWT токен
    
    Returns:
        str: Новий access token або None
    """
    from models import User, ApiToken, db
    
    secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key')
    
    try:
        # Декодуємо refresh token
        payload = jwt.decode(refresh_token, secret_key, algorithms=['HS256'])
        
        # Перевіряємо тип токена
        if payload.get('type') != 'refresh':
            return None
        
        # Перевіряємо наявність refresh token в базі
        refresh_token_id = payload.get('jti')
        refresh_token_record = ApiToken.query.filter_by(
            token_id=refresh_token_id,
            is_active=True
                ).first()
                
        if not refresh_token_record or refresh_token_record.is_expired():
            return None
        
        # Отримуємо access token ID
        access_token_id = payload.get('access_jti')
        
        # Відкликаємо старий access token
        old_token = ApiToken.query.filter_by(token_id=access_token_id).first()
        if old_token:
            old_token.is_active = False
        
        # Генеруємо новий access token
        user_id = payload.get('user_id')
        expires_at = datetime.utcnow() + timedelta(days=30)
        now = datetime.utcnow()
        new_token_id = secrets.token_urlsafe(32)
        
        new_payload = {
            'user_id': user_id,
            'jti': new_token_id,
            'type': 'access',
            'exp': expires_at,
            'iat': now
        }
        new_access_token = jwt.encode(new_payload, secret_key, algorithm='HS256')
        
        # Зберігаємо новий токен
        new_token_record = ApiToken(
            user_id=user_id,
            token_id=new_token_id,
            name=f'Refreshed token {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}',
            expires_at=expires_at,
            is_active=True
        )
        db.session.add(new_token_record)
        db.session.commit()
        
        return new_access_token
        
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception as e:
        current_app.logger.error(f"Помилка при оновленні токена: {e}")
        db.session.rollback()
        return None