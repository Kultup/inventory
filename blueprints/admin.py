from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from datetime import datetime, timedelta
import os
import json
import io

# Імпорти моделей та функцій
from models import User, City, Device, DeviceHistory, UserActivity, SystemSettings, db
from utils import admin_required, log_user_activity

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/user/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form
        city_id = request.form.get('city_id', type=int)
        
        # Перевірка чи користувач вже існує
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Користувач з таким іменем вже існує!', 'danger')
            cities = City.query.all()
            return render_template('admin/add_user.html', cities=cities)
            
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            is_admin=is_admin,
            city_id=city_id
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Користувача успішно додано!')
        return redirect(url_for('admin.admin_users'))
    
    cities = City.query.all()
    return render_template('admin/add_user.html', cities=cities)

@admin_bp.route('/user/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Заборонити редагування власного облікового запису адміністратора
    if user.id == current_user.id:
        flash('Ви не можете редагувати власний обліковий запис через цю форму!', 'danger')
        return redirect(url_for('admin.admin_users'))
    
    if request.method == 'POST':
        username = request.form['username']
        
        # Перевірка чи нове ім'я вже зайняте
        existing_user = User.query.filter(User.username == username, User.id != user_id).first()
        if existing_user:
            flash('Користувач з таким іменем вже існує!', 'danger')
            cities = City.query.all()
            return render_template('admin/edit_user.html', user=user, cities=cities)
            
        user.username = username
        
        # Оновлення паролю лише якщо вказано новий
        if request.form['password']:
            user.password_hash = generate_password_hash(request.form['password'])
            
        user.is_admin = 'is_admin' in request.form
        user.is_active = 'is_active' in request.form
        user.city_id = request.form.get('city_id', type=int)
        
        db.session.commit()
        flash('Користувача успішно оновлено!')
        return redirect(url_for('admin.admin_users'))
    
    cities = City.query.all()
    return render_template('admin/edit_user.html', user=user, cities=cities)

@admin_bp.route('/user/toggle/<int:user_id>')
@login_required
@admin_required
def admin_toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Заборонити блокування власного облікового запису
    if user.id == current_user.id:
        flash('Ви не можете заблокувати власний обліковий запис!', 'danger')
        return redirect(url_for('admin.admin_users'))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    action = "розблоковано" if user.is_active else "заблоковано"
    flash(f'Користувача {user.username} успішно {action}!')
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/user/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Заборонити видалення власного облікового запису
    if user.id == current_user.id:
        flash('Ви не можете видалити власний обліковий запис!', 'danger')
        return redirect(url_for('admin.admin_users'))
    
    db.session.delete(user)
    db.session.commit()
    flash(f'Користувача {user.username} успішно видалено!')
    return redirect(url_for('admin.admin_users'))

# Адміністрування міст
@admin_bp.route('/cities')
@login_required
@admin_required
def admin_cities():
    cities = City.query.all()
    return render_template('admin/cities.html', cities=cities)

@admin_bp.route('/city/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_city():
    if request.method == 'POST':
        name = request.form['name']
        
        # Перевірка чи місто вже існує
        existing_city = City.query.filter_by(name=name).first()
        if existing_city:
            flash('Місто з такою назвою вже існує!', 'danger')
            return render_template('admin/add_city.html')
            
        new_city = City(name=name)
        db.session.add(new_city)
        db.session.commit()
        flash('Місто успішно додано!')
        return redirect(url_for('admin.admin_cities'))
        
    return render_template('admin/add_city.html')

@admin_bp.route('/city/edit/<int:city_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_city(city_id):
    city = City.query.get_or_404(city_id)
    
    if request.method == 'POST':
        name = request.form['name']
        
        # Перевірка чи нова назва вже зайнята
        existing_city = City.query.filter(City.name == name, City.id != city_id).first()
        if existing_city:
            flash('Місто з такою назвою вже існує!', 'danger')
            return render_template('admin/edit_city.html', city=city)
            
        city.name = name
        db.session.commit()
        flash('Місто успішно оновлено!')
        return redirect(url_for('admin.admin_cities'))
        
    return render_template('admin/edit_city.html', city=city)

@admin_bp.route('/city/delete/<int:city_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_city(city_id):
    city = City.query.get_or_404(city_id)
    
    # Перевірка, чи є пристрої або користувачі, прив'язані до цього міста
    if Device.query.filter_by(city_id=city_id).first() or User.query.filter_by(city_id=city_id).first():
        flash('Неможливо видалити місто, оскільки існують пристрої або користувачі, прив\'язані до нього!', 'danger')
        return redirect(url_for('admin.admin_cities'))
    
    db.session.delete(city)
    db.session.commit()
    flash(f'Місто {city.name} успішно видалено!')
    return redirect(url_for('admin.admin_cities'))

@admin_bp.route('/dashboard')
@login_required
@admin_required
def admin_dashboard():
    # Загальна статистика
    total_devices = Device.query.count()
    total_users = User.query.count()
    total_cities = City.query.count()
    
    # Розподіл пристроїв за містами
    devices_by_city = db.session.query(
        City.name, func.count(Device.id)
    ).join(City).group_by(City.name).all()
    
    # Розподіл пристроїв за типом
    devices_by_type = db.session.query(
        Device.type, func.count(Device.id)
    ).group_by(Device.type).all()
    
    # Розподіл пристроїв за статусом
    devices_by_status = db.session.query(
        Device.status, func.count(Device.id)
    ).group_by(Device.status).all()
    
    # Нові пристрої за останні 30 днів
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_devices_count = Device.query.filter(Device.created_at >= thirty_days_ago).count()
    
    # Пристрої, додані за останні 12 місяців
    devices_by_month = []
    for i in range(12):
        start_date = datetime.utcnow().replace(day=1) - timedelta(days=30*i)
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        count = Device.query.filter(Device.created_at >= start_date, Device.created_at < end_date).count()
        month_name = start_date.strftime('%B %Y')
        devices_by_month.append((month_name, count))
    devices_by_month.reverse()
    
    return render_template('admin/dashboard.html', 
                           total_devices=total_devices,
                           total_users=total_users,
                           total_cities=total_cities,
                           devices_by_city=devices_by_city,
                           devices_by_type=devices_by_type,
                           devices_by_status=devices_by_status,
                           new_devices_count=new_devices_count,
                           devices_by_month=devices_by_month)

@admin_bp.route('/user-activity')
@login_required
@admin_required
def admin_user_activity():
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Збільшуємо кількість записів на сторінку для журналу
    
    activities = UserActivity.query.order_by(UserActivity.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/user_activity.html', activities=activities)



@admin_bp.route('/settings/export')
@login_required
@admin_required
def admin_export_settings():
    """Експортує налаштування системи в JSON-файл"""
    # Імпортуємо функцію export_settings з utils
    from ..utils import export_settings
    
    settings_dict = export_settings()
    
    # Створюємо байтовий потік з JSON-даними
    json_data = json.dumps(settings_dict, indent=4, ensure_ascii=False).encode('utf-8')
    file_stream = io.BytesIO(json_data)
    
    # Формуємо ім'я файлу з датою експорту
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"settings_export_{timestamp}.json"
    
    log_user_activity(current_user.id, 'Експорт налаштувань системи', request.remote_addr, request.url)
    
    return send_file(
        file_stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/json'
    )

@admin_bp.route('/settings/import', methods=['POST'])
@login_required
@admin_required
def admin_import_settings():
    # Перевіряємо, чи був завантажений файл
    if 'settings_file' not in request.files:
        flash('Файл налаштувань не завантажено', 'danger')
        return redirect(url_for('admin.admin_backup'))
    
    file = request.files['settings_file']
    if file.filename == '':
        flash('Не вибрано файл', 'danger')
        return redirect(url_for('admin.admin_backup'))
    
    if file and file.filename.endswith('.json'):
        try:
            # Читаємо файл налаштувань
            settings_data = json.loads(file.read().decode('utf-8'))
            
            # Імпортуємо налаштування
            from ..utils import import_settings
            import_settings(settings_data)
            
            flash('Налаштування успішно імпортовано', 'success')
            return redirect(url_for('admin.admin_backup'))
        except Exception as e:
            current_app.logger.error(f"Помилка при імпорті налаштувань: {str(e)}")
            flash(f'Помилка імпорту налаштувань: {str(e)}', 'danger')
            return redirect(url_for('admin.admin_backup'))
    else:
        flash('Дозволені тільки файли формату JSON', 'danger')
        return redirect(url_for('admin.admin_backup'))