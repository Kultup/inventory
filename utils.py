from functools import wraps
from flask import abort, request, current_app
from flask_login import current_user
from datetime import datetime, timedelta
import os
import re
import shutil
import sqlite3
import time
import secrets
import jwt
from PIL import Image

# Дозволені розширення файлів
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Перевіряє, чи дозволене розширення файлу"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_password_strength(password):
    """
    Валідує складність пароля
    
    Вимоги:
    - Мінімум 8 символів
    - Обов'язково: великі літери, малі літери, цифри
    - Опціонально: спеціальні символи
    
    Args:
        password: Пароль для перевірки
    
    Returns:
        tuple: (is_valid: bool, errors: list) - чи валідний пароль та список помилок
    """
    errors = []
    
    if not password:
        return False, ['Пароль не може бути порожнім']
    
    if len(password) < 8:
        errors.append('Пароль має містити мінімум 8 символів')
    
    if not re.search(r'[A-Z]', password):
        errors.append('Пароль має містити принаймні одну велику літеру')
    
    if not re.search(r'[a-z]', password):
        errors.append('Пароль має містити принаймні одну малу літеру')
    
    if not re.search(r'\d', password):
        errors.append('Пароль має містити принаймні одну цифру')
    
    # Опціонально: спеціальні символи (не обов'язково, але рекомендується)
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        # Не додаємо помилку, але можемо додати попередження
        pass
    
    return len(errors) == 0, errors

def optimize_image(image_path, max_width=1920, max_height=1920, quality=85):
    """
    Оптимізує зображення: зменшує розмір, стискає
    
    Args:
        image_path: Шлях до зображення
        max_width: Максимальна ширина (px)
        max_height: Максимальна висота (px)
        quality: Якість JPEG (1-100)
    
    Returns:
        str: Шлях до оптимізованого зображення або False у випадку помилки
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
        
        return False
    except Exception as e:
        print(f"Помилка оптимізації зображення {image_path}: {e}")
        return False

def generate_thumbnails(image_path, sizes=None):
    """
    Генерує thumbnail'и різних розмірів для зображення
    
    Args:
        image_path: Шлях до оригінального зображення
        sizes: Список кортежів (width, height, suffix) для thumbnail'ів
               За замовчуванням: [(150, 150, 'thumb'), (300, 300, 'medium'), (800, 800, 'large')]
    
    Returns:
        dict: Словник з шляхами до thumbnail'ів {suffix: path} або False у випадку помилки
    """
    if sizes is None:
        sizes = [
            (150, 150, 'thumb'),   # Маленький thumbnail
            (300, 300, 'medium'),  # Середній
            (800, 800, 'large')    # Великий
        ]
    
    try:
        base_path = os.path.splitext(image_path)[0]
        ext = os.path.splitext(image_path)[1].lower()
        thumbnails = {}
        
        with Image.open(image_path) as img:
            # Конвертуємо RGBA в RGB якщо потрібно
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            for width, height, suffix in sizes:
                # Створюємо копію для thumbnail'а
                thumb = img.copy()
                thumb.thumbnail((width, height), Image.Resampling.LANCZOS)
                
                # Зберігаємо thumbnail
                thumb_path = f"{base_path}_{suffix}{ext}"
                thumb.save(thumb_path, 'JPEG', quality=85, optimize=True)
                thumbnails[suffix] = thumb_path
        
        return thumbnails
    except Exception as e:
        print(f"Помилка генерації thumbnail'ів для {image_path}: {e}")
        return False

def convert_to_webp(image_path, quality=85):
    """
    Конвертує зображення в WebP формат (якщо браузер підтримує)
    
    Args:
        image_path: Шлях до зображення
        quality: Якість WebP (1-100)
    
    Returns:
        str: Шлях до WebP файлу або False у випадку помилки
    """
    try:
        with Image.open(image_path) as img:
            # Конвертуємо RGBA в RGB якщо потрібно
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Створюємо WebP версію
            webp_path = os.path.splitext(image_path)[0] + '.webp'
            img.save(webp_path, 'WEBP', quality=quality, method=6)
            
            return webp_path
    except Exception as e:
        print(f"Помилка конвертації в WebP {image_path}: {e}")
        return False

def cleanup_unused_photos():
    """
    Видаляє невикористані фото з файлової системи
    
    Returns:
        int: Кількість видалених файлів
    """
    from models import DevicePhoto, db
    import glob
    
    try:
        # Отримуємо всі фото з бази даних
        used_photos = {photo.filename for photo in DevicePhoto.query.all()}
        
        # Отримуємо всі файли в папці uploads
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
        all_files = set()
        
        # Шукаємо всі файли (включаючи thumbnail'и та WebP)
        for pattern in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']:
            for file_path in glob.glob(os.path.join(upload_folder, pattern)):
                filename = os.path.basename(file_path)
                # Видаляємо суфікси thumbnail'ів (_thumb, _medium, _large)
                base_filename = filename
                for suffix in ['_thumb', '_medium', '_large']:
                    if suffix in base_filename:
                        base_filename = base_filename.replace(suffix, '')
                        # Також видаляємо розширення для порівняння
                        base_filename = os.path.splitext(base_filename)[0] + os.path.splitext(filename)[1]
                        break
                
                # Перевіряємо чи файл використовується
                if base_filename not in used_photos and filename not in used_photos:
                    all_files.add(file_path)
        
        # Видаляємо невикористані файли
        count = 0
        for file_path in all_files:
            try:
                os.remove(file_path)
                count += 1
            except Exception as e:
                print(f"Помилка видалення файлу {file_path}: {e}")
        
        return count
    except Exception as e:
        print(f"Помилка очищення невикористаних фото: {e}")
        return 0

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
        print(f"Помилка логування активності: {e}")

def record_failed_login_attempt(ip_address, username=None):
    """
    Записує невдалу спробу входу та блокує IP після 5 спроб на 15 хвилин
    
    Args:
        ip_address: IP адреса з якої була спроба
        username: Ім'я користувача (опціонально)
    
    Returns:
        tuple: (is_blocked: bool, remaining_seconds: int, attempt_count: int)
    """
    from models import FailedLoginAttempt, db
    from datetime import timedelta
    
    # Знаходимо або створюємо запис для цього IP
    attempt = FailedLoginAttempt.query.filter_by(ip_address=ip_address).first()
    
    if not attempt:
        attempt = FailedLoginAttempt(
            ip_address=ip_address,
            username=username,
            attempt_count=1,
            last_attempt=datetime.utcnow()
        )
        db.session.add(attempt)
    else:
        # Оновлюємо лічильник спроб
        attempt.attempt_count += 1
        attempt.last_attempt = datetime.utcnow()
        if username:
            attempt.username = username  # Оновлюємо username якщо він змінився
    
    # Блокуємо IP після 5 невдалих спроб на 15 хвилин
    if attempt.attempt_count >= 5:
        if not attempt.blocked_until or datetime.utcnow() >= attempt.blocked_until:
            attempt.blocked_until = datetime.utcnow() + timedelta(minutes=15)
            # Логуємо підозрілу активність
            log_suspicious_activity(ip_address, f"IP заблоковано після {attempt.attempt_count} невдалих спроб входу", username)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Помилка запису невдалої спроби: {e}")
        return False, 0, 0
    
    # Перевіряємо чи IP заблоковано
    is_blocked = attempt.is_blocked()
    remaining_seconds = attempt.get_remaining_block_time()
    
    return is_blocked, remaining_seconds, attempt.attempt_count

def check_ip_blocked(ip_address):
    """
    Перевіряє чи IP адреса заблокована
    
    Args:
        ip_address: IP адреса для перевірки
    
    Returns:
        tuple: (is_blocked: bool, remaining_seconds: int, attempt_count: int)
    """
    from models import FailedLoginAttempt
    
    attempt = FailedLoginAttempt.query.filter_by(ip_address=ip_address).first()
    
    if not attempt:
        return False, 0, 0
    
    is_blocked = attempt.is_blocked()
    remaining_seconds = attempt.get_remaining_block_time()
    
    return is_blocked, remaining_seconds, attempt.attempt_count

def reset_failed_login_attempts(ip_address):
    """
    Скидає лічильник невдалих спроб для IP адреси (викликається при успішному вході)
    
    Args:
        ip_address: IP адреса для скидання
    """
    from models import FailedLoginAttempt, db
    
    attempt = FailedLoginAttempt.query.filter_by(ip_address=ip_address).first()
    if attempt:
        try:
            db.session.delete(attempt)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Помилка скидання невдалих спроб: {e}")

def log_suspicious_activity(ip_address, description, username=None):
    """
    Логує підозрілу активність (блокировки, багато невдалих спроб тощо)
    
    Args:
        ip_address: IP адреса
        description: Опис підозрілої активності
        username: Ім'я користувача (опціонально)
    """
    try:
        from flask import current_app
        current_app.logger.warning(
            f"SUSPICIOUS ACTIVITY - IP: {ip_address}, "
            f"Username: {username or 'N/A'}, "
            f"Description: {description}, "
            f"Time: {datetime.utcnow().isoformat()}"
        )
    except:
        # Якщо не можемо залогувати, просто ігноруємо
        pass

def create_user_session(user_id, session_id, ip_address=None, user_agent=None):
    """
    Створює запис про активну сесію користувача
    
    Args:
        user_id: ID користувача
        session_id: Flask session ID
        ip_address: IP адреса (опціонально)
        user_agent: User-Agent заголовок (опціонально)
    
    Returns:
        UserSession: Створений об'єкт сесії
    """
    from models import UserSession, db
    from flask import request
    
    # Використовуємо request якщо не передано
    if not ip_address:
        ip_address = request.remote_addr if request else 'unknown'
    if not user_agent:
        user_agent = request.headers.get('User-Agent') if request else None
    
    # Перевіряємо чи сесія вже існує
    existing_session = UserSession.query.filter_by(session_id=session_id).first()
    if existing_session:
        # Оновлюємо існуючу сесію
        existing_session.is_active = True
        existing_session.last_activity = datetime.utcnow()
        existing_session.ip_address = ip_address
        if user_agent:
            existing_session.user_agent = user_agent
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Помилка оновлення сесії: {e}")
        return existing_session
    
    # Створюємо нову сесію
    session = UserSession(
        user_id=user_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        is_active=True
    )
    db.session.add(session)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Помилка створення сесії: {e}")
        return None
    
    return session

def update_session_activity(session_id):
    """
    Оновлює час останньої активності для сесії
    
    Args:
        session_id: Flask session ID
    """
    from models import UserSession, db
    
    session = UserSession.query.filter_by(session_id=session_id, is_active=True).first()
    if session:
        session.update_activity()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Помилка оновлення активності сесії: {e}")

def deactivate_user_session(session_id):
    """
    Деактивує сесію користувача
    
    Args:
        session_id: Flask session ID
    """
    from models import UserSession, db
    
    session = UserSession.query.filter_by(session_id=session_id).first()
    if session:
        session.is_active = False
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Помилка деактивації сесії: {e}")

def deactivate_all_user_sessions(user_id, exclude_session_id=None):
    """
    Деактивує всі сесії користувача, крім поточної
    
    Args:
        user_id: ID користувача
        exclude_session_id: Session ID яку не потрібно деактивувати (поточна сесія)
    
    Returns:
        int: Кількість деактивованих сесій
    """
    from models import UserSession, db
    
    query = UserSession.query.filter_by(user_id=user_id, is_active=True)
    if exclude_session_id:
        query = query.filter(UserSession.session_id != exclude_session_id)
    
    sessions = query.all()
    count = len(sessions)
    
    for session in sessions:
        session.is_active = False
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Помилка деактивації сесій: {e}")
        return 0
    
    return count

def cleanup_expired_sessions(inactivity_timeout_minutes=30):
    """
    Очищає прострочені сесії (неактивні більше 30 хвилин)
    
    Args:
        inactivity_timeout_minutes: Таймаут неактивності в хвилинах
    
    Returns:
        int: Кількість очищених сесій
    """
    from models import UserSession, db
    
    expired_sessions = UserSession.query.filter_by(is_active=True).all()
    count = 0
    
    for session in expired_sessions:
        if session.is_expired(inactivity_timeout_minutes):
            session.is_active = False
            count += 1
    
    if count > 0:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Помилка очищення сесій: {e}")
            return 0
    
    return count

def cleanup_expired_blacklist():
    """
    Очищає прострочені записи з blacklist токенів
    
    Returns:
        int: Кількість очищених записів
    """
    from models import TokenBlacklist, db
    
    expired_blacklist = TokenBlacklist.query.all()
    count = 0
    
    for blacklisted in expired_blacklist:
        if blacklisted.is_expired():
            try:
                db.session.delete(blacklisted)
                count += 1
            except Exception as e:
                db.session.rollback()
                print(f"Помилка видалення запису з blacklist: {e}")
                continue
    
    if count > 0:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Помилка очищення blacklist: {e}")
            return 0
    
    return count

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
    """
    Перевіряє пристрої, яким потрібне обслуговування.
    
    Логіка нагадувань:
    - Пристрої з простроченим обслуговуванням (next_maintenance < today) - відправляються щодня
    - Пристрої, яким час обслуговування настав сьогодні (next_maintenance == today) - відправляються щодня
    - Пристрої, яким скоро обслуговування (next_maintenance <= today + days_before) - відправляються один раз
    
    Примітка: Функція повертає статистику про пристрої, які потребують обслуговування.
    Telegram нагадування видалено.
    """
    from models import Device, User, db, SystemSettings
    from datetime import date, timedelta
    from sqlalchemy.orm import joinedload
    
    try:
        today = date.today()
        
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
        
        current_app.logger.info(
            f"Перевірка обслуговування завершена. "
            f"Прострочено/час вийшов: {len(overdue_devices)}, Скоро: {len(soon_devices)}"
        )
        
        return {
            'overdue': len(overdue_devices), 
            'soon': len(soon_devices), 
            'notifications_sent': 0
        }
    except Exception as e:
        current_app.logger.error(f"Помилка при перевірці обслуговування: {e}", exc_info=True)
        db.session.rollback()
        return {'overdue': 0, 'soon': 0, 'notifications_sent': 0}

# JWT функції для API автентифікації
def generate_jwt_token(user_id, token_name=None, expires_in_days=None):
    """
    Генерує JWT токен для користувача
    
    Args:
        user_id: ID користувача
        token_name: Назва токена (опціонально)
        expires_in_days: Термін дії refresh token в днях (за замовчуванням 7, не використовується для access token)
    
    Returns:
        tuple: (access_token, refresh_token, token_id)
    """
    from models import ApiToken, db
    
    # Генеруємо унікальний ID для токена
    token_id = secrets.token_urlsafe(32)
    
    # Термін дії токенів
    # Access token: 15 хвилин
    access_expires_at = datetime.utcnow() + timedelta(minutes=15)
    # Refresh token: 7 днів (або вказаний термін)
    refresh_expires_days = expires_in_days if expires_in_days is not None else 7
    refresh_expires_at = datetime.utcnow() + timedelta(days=refresh_expires_days)
    now = datetime.utcnow()
    
    # Секретний ключ з конфігурації
    secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key')
    
    # Створюємо access token (15 хвилин)
    access_payload = {
        'user_id': user_id,
        'jti': token_id,  # JWT ID
        'type': 'access',
        'exp': int(access_expires_at.timestamp()),  # Unix timestamp
        'iat': int(now.timestamp())
    }
    access_token = jwt.encode(access_payload, secret_key, algorithm='HS256')
    
    # Створюємо refresh token (7 днів)
    refresh_token_id = secrets.token_urlsafe(32)
    refresh_payload = {
        'user_id': user_id,
        'jti': refresh_token_id,
        'type': 'refresh',
        'access_jti': token_id,  # Посилання на access token
        'exp': int(refresh_expires_at.timestamp()),
        'iat': int(now.timestamp())
    }
    refresh_token = jwt.encode(refresh_payload, secret_key, algorithm='HS256')
    
    # Зберігаємо access token в базі даних
    api_token = ApiToken(
        user_id=user_id,
        token_id=token_id,
        name=token_name or f'Token {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}',
        expires_at=access_expires_at,
        is_active=True
    )
    db.session.add(api_token)
    
    # Зберігаємо refresh token
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

def is_token_blacklisted(token_id):
    """
    Перевіряє чи токен в blacklist
    
    Args:
        token_id: JWT ID токена
    
    Returns:
        bool: True якщо токен в blacklist, False якщо ні
    """
    from models import TokenBlacklist
    
    blacklisted = TokenBlacklist.query.filter_by(token_id=token_id).first()
    if blacklisted:
        # Якщо токен прострочений, можна видалити з blacklist
        if blacklisted.is_expired():
            try:
                from models import db
                db.session.delete(blacklisted)
                db.session.commit()
            except:
                pass
            return False
        return True
    return False

def add_token_to_blacklist(token_id, token_type, user_id, expires_at):
    """
    Додає токен до blacklist
    
    Args:
        token_id: JWT ID токена
        token_type: Тип токена ('access' або 'refresh')
        user_id: ID користувача
        expires_at: Час прострочення токена
    """
    from models import TokenBlacklist, db
    
    # Перевіряємо чи токен вже в blacklist
    existing = TokenBlacklist.query.filter_by(token_id=token_id).first()
    if existing:
        return
    
    blacklisted = TokenBlacklist(
        token_id=token_id,
        token_type=token_type,
        user_id=user_id,
        expires_at=expires_at
    )
    db.session.add(blacklisted)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Помилка додавання токена до blacklist: {e}")

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
        
        # Перевіряємо чи токен в blacklist
        token_id = payload.get('jti')
        if is_token_blacklisted(token_id):
            return None
        
        # Перевіряємо наявність токена в базі
        api_token = ApiToken.query.filter_by(
            token_id=token_id,
            is_active=True
        ).first()
        
        if not api_token:
            return None
        
        # Перевіряємо термін дії
        if api_token.is_expired():
            api_token.is_active = False
            # Додаємо до blacklist
            add_token_to_blacklist(token_id, 'access', api_token.user_id, api_token.expires_at)
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
        # Токен прострочений - додаємо до blacklist якщо можливо
        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'], options={"verify_signature": False, "verify_exp": False})
            token_id = payload.get('jti')
            user_id = payload.get('user_id')
            exp = payload.get('exp')
            if exp and token_id and user_id:
                expires_at = datetime.fromtimestamp(exp)
                add_token_to_blacklist(token_id, 'access', user_id, expires_at)
        except:
            pass
        return None
    except jwt.InvalidTokenError:
        # Невірний токен
        return None
    except Exception as e:
        current_app.logger.error(f"Помилка при валідації токена: {e}")
        return None

def revoke_jwt_token(token_id):
    """
    Відкликає JWT токен (додає до blacklist)
    
    Args:
        token_id: ID токена (jti)
    
    Returns:
        bool: True якщо токен відкликано, False якщо не знайдено
    """
    from models import ApiToken, db
    
    try:
        api_token = ApiToken.query.filter_by(token_id=token_id).first()
        if api_token:
            # Деактивуємо токен
            api_token.is_active = False
            
            # Додаємо до blacklist
            token_type = 'access'  # За замовчуванням access, але можна визначити з payload
            add_token_to_blacklist(token_id, token_type, api_token.user_id, api_token.expires_at)
            
            # Також відкликаємо пов'язаний refresh token якщо є
            # Шукаємо refresh token який посилається на цей access token
            refresh_token = ApiToken.query.filter(
                ApiToken.name.like(f'Refresh token for {token_id}'),
                ApiToken.is_active == True
            ).first()
            
            if refresh_token:
                refresh_token.is_active = False
                add_token_to_blacklist(refresh_token.token_id, 'refresh', refresh_token.user_id, refresh_token.expires_at)
            
            db.session.commit()
            return True
        return False
    except Exception as e:
        current_app.logger.error(f"Помилка при відкликанні токена: {e}")
        db.session.rollback()
        return False

def refresh_access_token(refresh_token):
    """
    Генерує новий access token та новий refresh token на основі старого refresh token (ротація)
    
    Args:
        refresh_token: Refresh JWT токен
    
    Returns:
        tuple: (new_access_token, new_refresh_token) або (None, None) якщо невалідний
    """
    from models import User, ApiToken, db
    
    secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key')
    
    try:
        # Декодуємо refresh token
        payload = jwt.decode(refresh_token, secret_key, algorithms=['HS256'])
        
        # Перевіряємо тип токена
        if payload.get('type') != 'refresh':
            return None, None
        
        # Перевіряємо чи refresh token в blacklist
        refresh_token_id = payload.get('jti')
        if is_token_blacklisted(refresh_token_id):
            return None, None
        
        # Перевіряємо наявність refresh token в базі
        refresh_token_record = ApiToken.query.filter_by(
            token_id=refresh_token_id,
            is_active=True
        ).first()
                
        if not refresh_token_record or refresh_token_record.is_expired():
            # Додаємо до blacklist якщо прострочений
            if refresh_token_record:
                add_token_to_blacklist(refresh_token_id, 'refresh', refresh_token_record.user_id, refresh_token_record.expires_at)
            return None, None
        
        # Отримуємо access token ID
        access_token_id = payload.get('access_jti')
        user_id = payload.get('user_id')
        
        # Відкликаємо старий access token (додаємо до blacklist)
        old_token = ApiToken.query.filter_by(token_id=access_token_id).first()
        if old_token:
            old_token.is_active = False
            add_token_to_blacklist(access_token_id, 'access', old_token.user_id, old_token.expires_at)
        
        # Відкликаємо старий refresh token (ротація)
        refresh_token_record.is_active = False
        add_token_to_blacklist(refresh_token_id, 'refresh', refresh_token_record.user_id, refresh_token_record.expires_at)
        
        # Генеруємо новий access token (15 хвилин)
        access_expires_at = datetime.utcnow() + timedelta(minutes=15)
        now = datetime.utcnow()
        new_token_id = secrets.token_urlsafe(32)
        
        new_access_payload = {
            'user_id': user_id,
            'jti': new_token_id,
            'type': 'access',
            'exp': int(access_expires_at.timestamp()),
            'iat': int(now.timestamp())
        }
        new_access_token = jwt.encode(new_access_payload, secret_key, algorithm='HS256')
        
        # Генеруємо новий refresh token (7 днів) - ротація
        new_refresh_token_id = secrets.token_urlsafe(32)
        refresh_expires_at = datetime.utcnow() + timedelta(days=7)
        
        new_refresh_payload = {
            'user_id': user_id,
            'jti': new_refresh_token_id,
            'type': 'refresh',
            'access_jti': new_token_id,  # Посилання на новий access token
            'exp': int(refresh_expires_at.timestamp()),
            'iat': int(now.timestamp())
        }
        new_refresh_token = jwt.encode(new_refresh_payload, secret_key, algorithm='HS256')
        
        # Зберігаємо новий access token
        new_token_record = ApiToken(
            user_id=user_id,
            token_id=new_token_id,
            name=f'Refreshed token {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}',
            expires_at=access_expires_at,
            is_active=True
        )
        db.session.add(new_token_record)
        
        # Зберігаємо новий refresh token
        new_refresh_record = ApiToken(
            user_id=user_id,
            token_id=new_refresh_token_id,
            name=f'Refresh token for {new_token_id}',
            expires_at=refresh_expires_at,
            is_active=True
        )
        db.session.add(new_refresh_record)
        
        db.session.commit()
        
        return new_access_token, new_refresh_token
        
    except jwt.ExpiredSignatureError:
        # Додаємо до blacklist якщо можливо
        try:
            payload = jwt.decode(refresh_token, secret_key, algorithms=['HS256'], options={"verify_signature": False, "verify_exp": False})
            refresh_token_id = payload.get('jti')
            user_id = payload.get('user_id')
            exp = payload.get('exp')
            if exp and refresh_token_id and user_id:
                expires_at = datetime.fromtimestamp(exp)
                add_token_to_blacklist(refresh_token_id, 'refresh', user_id, expires_at)
        except:
            pass
        return None, None
    except jwt.InvalidTokenError:
        return None, None
    except Exception as e:
        current_app.logger.error(f"Помилка при оновленні токена: {e}")
        db.session.rollback()
        return None, None