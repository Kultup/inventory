from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
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
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
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
@app.route('/toggle-theme')
def toggle_theme():
    from flask import redirect, request, make_response
    current_theme = request.cookies.get('theme', 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    
    response = make_response(redirect(request.referrer or '/'))
    response.set_cookie('theme', new_theme, max_age=365*24*60*60)  # Зберігаємо на рік
    return response

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
            city_id=default_city.id
        )
        db.session.add(admin)
        db.session.commit()
        print("Створено адміністратора: admin/admin")

# Ініціалізація планувальника задач
def init_scheduler():
    """Ініціалізує планувальник для автоматичних задач"""
    from utils import backup_database, cleanup_old_backups
    from reminder_service import ReminderService
    
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
    
    # Перевірка обслуговування та незаповнених даних (Telegram-бoт)
    import pytz
    kyiv_tz = pytz.timezone('Europe/Kyiv')
    
    # Вимкнено за замовчуванням: не створюємо задачі Telegram-нагадувань
    # Увімкнути можна, встановивши TELEGRAM_REMINDERS_ENABLED=True у конфігурації
    if app.config.get('TELEGRAM_REMINDERS_ENABLED', False):
        # Обгорткові функції для роботи з контекстом Flask
        def check_maintenance_with_context():
            """Обгортка для перевірки обслуговування з контекстом Flask"""
            with app.app_context():
                ReminderService.check_maintenance_reminders()
        
        def check_incomplete_data_with_context():
            """Обгортка для перевірки незаповнених даних з контекстом Flask"""
            with app.app_context():
                ReminderService.check_incomplete_data_reminders()
        
        scheduler.add_job(
            func=check_maintenance_with_context,
            trigger=CronTrigger(hour=16, minute=51, timezone=kyiv_tz),
            id='check_maintenance',
            name='Перевірка обслуговування пристроїв (за 3 дні)',
            replace_existing=True
        )
        
        scheduler.add_job(
            func=check_incomplete_data_with_context,
            trigger=CronTrigger(hour=16, minute=51, timezone=kyiv_tz),
            id='check_incomplete_data',
            name='Перевірка незаповнених даних (щодня)',
            replace_existing=True
        )
    else:
        print("Telegram-нагадування вимкнено (TELEGRAM_REMINDERS_ENABLED=False). Задачі не створюються.")
    
    scheduler.start()
    print("Планувальник задач запущено")



# Глобальні обробники помилок
@app.errorhandler(404)
def not_found_error(error):
    """Обробка помилки 404 - сторінка не знайдена"""
    return render_template('error.html', 
                         error_code=404, 
                         error_title='Сторінка не знайдена',
                         error_message="Запитана сторінка не існує. Перевірте правильність URL."), 404

@app.errorhandler(403)
def forbidden_error(error):
    """Обробка помилки 403 - доступ заборонено"""
    return render_template('error.html', 
                         error_code=403, 
                         error_title='Доступ заборонено',
                         error_message="У вас немає прав доступу до цього ресурсу."), 403

@app.errorhandler(500)
def internal_error(error):
    """Обробка помилки 500 - внутрішня помилка сервера"""
    from flask import current_app
    current_app.logger.error(f'Server Error: {error}', exc_info=True)
    return render_template('error.html', 
                         error_code=500, 
                         error_title='Внутрішня помилка сервера',
                         error_message="Сталася несподівана помилка. Будь ласка, спробуйте пізніше або зверніться до адміністратора."), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Обробка помилки CSRF"""
    return render_template('error.html', 
                         error_code=400, 
                         error_title='Помилка безпеки',
                         error_message="Помилка запиту. Можливо, закінчився час сесії. Спробуйте оновити сторінку."), 400

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
    print(f"Локальна адреса: http://127.0.0.1:5000")
    print(f"Мережева адреса: http://{local_ip}:5000")
    print("="*60)
    print("Для доступу з інших пристроїв використовуйте мережеву адресу")
    print("="*60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)  # Для розробки