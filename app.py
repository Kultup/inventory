from flask import Flask, render_template, request, jsonify, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import os
import re

# Імпорт конфігурації
from config import DevelopmentConfig

# Імпорт моделей
from models import db, User

# Ініціалізація Flask додатку
app = Flask(__name__)
app.config.from_object(DevelopmentConfig)

# Ініціалізація розширень
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
csrf = CSRFProtect(app)

# Ініціалізація Flask-Limiter для rate limiting
# Використовуємо налаштування з конфігурації
rate_limit_per_hour = app.config.get('RATE_LIMIT_PER_HOUR', 3600)
rate_limit_per_day = app.config.get('RATE_LIMIT_PER_DAY', 20000)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[f"{rate_limit_per_day} per day", f"{rate_limit_per_hour} per hour"],
    storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
)

# Ініціалізація Flask-Caching для кешування
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',  # Для production використовуйте 'redis' або 'memcached'
    'CACHE_DEFAULT_TIMEOUT': 300  # 5 хвилин за замовчуванням
})

# Створення директорій, якщо вони не існують
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['BACKUP_FOLDER']):
    os.makedirs(app.config['BACKUP_FOLDER'])

# Додаємо фільтр для перетворення переносів рядків у HTML-теги <br>
@app.template_filter('nl2br')
def nl2br(value):
    if value:
        return re.sub(r'\n', '<br>', value)
    return ''

# Додаємо фільтр для конвертації UTC часу в локальний часовий пояс (Europe/Kyiv)
@app.template_filter('local_time')
def local_time(value, format='%d.%m.%Y %H:%M'):
    """Конвертує UTC datetime в локальний часовий пояс (Europe/Kyiv)"""
    if not value:
        return ''
    
    try:
        from flask import current_app
        import pytz
        
        # Якщо це naive datetime (без timezone), вважаємо що це UTC
        if value.tzinfo is None:
            utc_time = pytz.UTC.localize(value)
        else:
            utc_time = value.astimezone(pytz.UTC)
        
        # Конвертуємо в часовий пояс Києва
        kyiv_tz = pytz.timezone('Europe/Kyiv')
        local_time = utc_time.astimezone(kyiv_tz)
        
        return local_time.strftime(format)
    except Exception as e:
        # Якщо помилка, повертаємо оригінальний формат
        try:
            from flask import current_app
            current_app.logger.warning(f"Помилка конвертації часу: {e}")
        except:
            pass
        return value.strftime(format) if hasattr(value, 'strftime') else str(value)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Middleware для оновлення активності сесії
@app.before_request
def update_session_activity():
    """Оновлює активність сесії при кожному запиті"""
    from flask_login import current_user
    from flask import session as flask_session
    from utils import update_session_activity
    
    if current_user.is_authenticated:
        session_id = flask_session.get('_id', flask_session.sid if hasattr(flask_session, 'sid') else None)
        if session_id:
            update_session_activity(str(session_id))

# Context processor для підрахунку прострочених пристроїв
@app.context_processor
def inject_overdue_devices_count():
    """Обслуговування вимкнено: завжди 0 прострочених пристроїв"""
    return {'overdue_devices_count': 0}

# Реєстрація blueprints
from blueprints.auth import auth_bp
from blueprints.devices import devices_bp
from blueprints.admin import admin_bp
from blueprints.api import api_bp
from blueprints.employees import employees_bp

app.register_blueprint(auth_bp)
app.register_blueprint(devices_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)
app.register_blueprint(employees_bp)

# Health check endpoints для моніторингу
@app.route('/health')
def health_check():
    """Health check endpoint для перевірки стану застосунку"""
    try:
        # Перевіряємо підключення до бази даних
        db.session.execute(db.text('SELECT 1'))
        return {'status': 'healthy', 'database': 'connected'}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'database': 'disconnected', 'error': str(e)}, 503

@app.route('/ready')
def readiness_check():
    """Readiness check endpoint для перевірки готовності застосунку"""
    try:
        # Перевіряємо підключення до бази даних
        db.session.execute(db.text('SELECT 1'))
        # Перевіряємо наявність основних таблиць
        from models import User, Device, City
        User.query.first()
        Device.query.first()
        City.query.first()
        return {'status': 'ready', 'database': 'connected', 'tables': 'ok'}, 200
    except Exception as e:
        return {'status': 'not ready', 'error': str(e)}, 503

# Головна сторінка
@app.route('/')
def index():
    from flask_login import current_user
    from models import Device
    
    # Статистика для авторизованих користувачів
    stats = {}
    if current_user.is_authenticated:
        # Якщо користувач адміністратор - показуємо всі дані
        if current_user.is_admin:
            base_query = Device.query
        else:
            # Звичайні користувачі бачать тільки дані свого міста
            base_query = Device.query.filter_by(city_id=current_user.city_id)
        
        stats['total_devices'] = base_query.count()
        stats['active_devices'] = base_query.filter_by(status='В роботі').count()
        stats['repair_devices'] = base_query.filter_by(status='На ремонті').count()
        stats['decommissioned_devices'] = base_query.filter_by(status='Списано').count()
    
    return render_template('index.html', **stats)

# Маршрут для перемикання теми
@app.route('/api/search')
@login_required
def search():
    """API endpoint для пошуку всіх сутностей в системі: пристроїв, співробітників, міст, користувачів"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 5, type=int)
    
    if not query or len(query) < 2:
        return jsonify({
            'devices': [],
            'employees': [],
            'cities': [],
            'users': []
        })
    
    results = {
        'devices': [],
        'employees': [],
        'cities': [],
        'users': []
    }
    
    # Пошук пристроїв
    from models import Device
    from sqlalchemy import or_
    
    if current_user.is_admin:
        device_query = Device.query
    else:
        device_query = Device.query.filter_by(city_id=current_user.city_id)
    
    device_query = device_query.filter(
        or_(
            Device.name.ilike(f'%{query}%'),
            Device.type.ilike(f'%{query}%'),
            Device.serial_number.ilike(f'%{query}%'),
            Device.inventory_number.ilike(f'%{query}%'),
            Device.location.ilike(f'%{query}%')
        )
    ).limit(limit)
    
    devices = device_query.all()
    results['devices'] = [{
        'id': d.id,
        'name': d.name,
        'type': d.type,
        'serial_number': d.serial_number,
        'inventory_number': d.inventory_number,
        'url': url_for('devices.device_detail', device_id=d.id)
    } for d in devices]
    
    # Пошук співробітників (тільки для адмінів)
    if current_user.is_admin:
        from models import Employee
        
        employee_query = Employee.query.filter(
            or_(
                Employee.first_name.ilike(f'%{query}%'),
                Employee.last_name.ilike(f'%{query}%'),
                Employee.middle_name.ilike(f'%{query}%'),
                Employee.position.ilike(f'%{query}%'),
                Employee.department.ilike(f'%{query}%')
            )
        ).limit(limit)
        
        employees = employee_query.all()
        results['employees'] = [{
            'id': e.id,
            'name': f'{e.last_name} {e.first_name} {e.middle_name or ""}'.strip(),
            'position': e.position or '',
            'url': url_for('employees.employee_detail', employee_id=e.id)
        } for e in employees]
        
        # Пошук міст (тільки для адмінів)
        from models import City
        
        city_query = City.query.filter(
            City.name.ilike(f'%{query}%')
        ).limit(limit)
        
        cities = city_query.all()
        results['cities'] = [{
            'id': c.id,
            'name': c.name,
            'url': url_for('admin.admin_cities')
        } for c in cities]
        
        # Пошук користувачів (тільки для адмінів)
        from models import User
        
        user_query = User.query.filter(
            or_(
                User.username.ilike(f'%{query}%')
            )
        ).limit(limit)
        
        users = user_query.all()
        results['users'] = [{
            'id': u.id,
            'name': u.username,
            'is_admin': u.is_admin,
            'is_active': u.is_active,
            'url': url_for('admin.admin_edit_user', user_id=u.id)
        } for u in users]
    
    return jsonify(results)


# Функція для створення адміністратора
def create_admin():
    """Створює адміністратора за замовчуванням, якщо його немає"""
    from werkzeug.security import generate_password_hash
    from models import City
    
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        # Створюємо місто за замовчуванням
        default_city = City.query.filter_by(name='Головний офіс').first()
        if not default_city:
            default_city = City(name='Головний офіс')
            db.session.add(default_city)
            db.session.commit()
        
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin'),
            is_admin=True,
            city_id=default_city.id,
            must_change_password=True  # Обов'язкова зміна пароля при першому вході
        )
        db.session.add(admin)
        db.session.commit()
        print("Створено адміністратора: admin/admin")

# Ініціалізація планувальника задач
def init_scheduler():
    """Ініціалізує планувальник для автоматичних задач"""
    from utils import backup_database, cleanup_old_backups
    
    scheduler = BackgroundScheduler()
    
    # Автоматичний backup щодня о 2:00
    if app.config.get('BACKUP_AUTO_ENABLED', False):
        # Обгорткові функції для backup з контекстом Flask
        def backup_with_context():
            """Обгортка для backup з контекстом Flask"""
            with app.app_context():
                backup_database(app.config['BACKUP_FOLDER'])
        
        def cleanup_backups_with_context():
            """Обгортка для очищення backup з контекстом Flask"""
            with app.app_context():
                cleanup_old_backups(
                    app.config['BACKUP_FOLDER'], 
                    app.config.get('BACKUP_KEEP_DAYS', 30)
                )
        
        scheduler.add_job(
            func=backup_with_context,
            trigger=CronTrigger(hour=2, minute=0),
            id='daily_backup',
            name='Щоденне резервне копіювання',
            replace_existing=True
        )
        
        # Очищення старих backup щотижня
        scheduler.add_job(
            func=cleanup_backups_with_context,
            trigger=CronTrigger(day_of_week=0, hour=3, minute=0),
            id='cleanup_backups',
            name='Очищення старих backup',
            replace_existing=True
        )
    
    # Очищення прострочених сесій кожні 30 хвилин
    from utils import cleanup_expired_sessions, cleanup_expired_blacklist
    
    def cleanup_sessions_with_context():
        """Обгортка для очищення сесій з контекстом Flask"""
        with app.app_context():
            count = cleanup_expired_sessions(inactivity_timeout_minutes=30)
            if count > 0:
                app.logger.info(f"Очищено {count} прострочених сесій")
    
    scheduler.add_job(
        func=cleanup_sessions_with_context,
        trigger=CronTrigger(minute='*/30'),  # Кожні 30 хвилин
        id='cleanup_expired_sessions',
        name='Очищення прострочених сесій',
        replace_existing=True
    )
    
    # Очищення прострочених записів з blacklist щодня о 3:00
    def cleanup_blacklist_with_context():
        """Обгортка для очищення blacklist з контекстом Flask"""
        with app.app_context():
            count = cleanup_expired_blacklist()
            if count > 0:
                app.logger.info(f"Очищено {count} прострочених записів з blacklist")
    
    scheduler.add_job(
        func=cleanup_blacklist_with_context,
        trigger=CronTrigger(hour=3, minute=0),  # Щодня о 3:00
        id='cleanup_expired_blacklist',
        name='Очищення прострочених записів з blacklist',
        replace_existing=True
    )
    
    # Очищення невикористаних фото щодня о 4:00
    from utils import cleanup_unused_photos
    
    def cleanup_photos_with_context():
        """Обгортка для очищення фото з контекстом Flask"""
        with app.app_context():
            count = cleanup_unused_photos()
            if count > 0:
                app.logger.info(f"Очищено {count} невикористаних фото")
    
    scheduler.add_job(
        func=cleanup_photos_with_context,
        trigger=CronTrigger(hour=4, minute=0),  # Щодня о 4:00
        id='cleanup_unused_photos',
        name='Очищення невикористаних фото',
        replace_existing=True
    )
    
    
    scheduler.start()
    print("Планувальник задач запущено")



# Глобальні обробники помилок
@app.errorhandler(404)
def not_found_error(error):
    """Обробка помилки 404 - сторінка не знайдена"""
    return render_template('error_404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    """Обробка помилки 403 - доступ заборонено"""
    return render_template('error_403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    """Обробка помилки 500 - внутрішня помилка сервера"""
    from flask import current_app
    current_app.logger.error(f'Server Error: {error}', exc_info=True)
    return render_template('error_500.html'), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Обробка помилки CSRF"""
    return render_template('error_400.html', 
                         error_title='Помилка безпеки',
                         error_message="Помилка запиту. Можливо, закінчився час сесії. Спробуйте оновити сторінку."), 400

@app.errorhandler(429)
def handle_rate_limit(e):
    """Обробка помилки 429 (Too Many Requests)"""
    rate_limit_per_hour = app.config.get('RATE_LIMIT_PER_HOUR', 200)
    return render_template('error_429.html',
                         error_title='Забагато запитів',
                         error_message=f"Ви перевищили ліміт запитів. Спробуйте пізніше. Ліміт: {rate_limit_per_hour} запитів на годину."), 429

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
        init_scheduler()

    # Отримуємо IP адресу комп'ютера для доступу з інших пристроїв
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    print("\n" + "="*60)
    print("Сервер запущено!")
    print("="*60)
    print(f"Локальна адреса: http://127.0.0.1:8000")
    print(f"Мережева адреса: http://{local_ip}:8000")
    print("="*60)
    print("Для доступу з інших пристроїв використовуйте мережеву адресу")
    print("="*60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=8000)  # Для розробки