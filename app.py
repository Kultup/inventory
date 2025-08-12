from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from datetime import datetime

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
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
csrf = CSRFProtect(app)

# Створення директорій, якщо вони не існують
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])



# Додаємо фільтр для перетворення переносів рядків у HTML-теги <br>
@app.template_filter('nl2br')
def nl2br(value):
    if value:
        return re.sub(r'\n', '<br>', value)
    return ''

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Реєстрація blueprints
from blueprints.auth import auth_bp
from blueprints.devices import devices_bp
from blueprints.admin import admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(devices_bp)
app.register_blueprint(admin_bp)

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



# Обробка помилок CSRF
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template('error.html', error_code=400, error_message="Помилка запиту. Можливо, закінчився час сесії. Спробуйте оновити сторінку."), 400

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()

    app.run(debug=True)  # Для розробки