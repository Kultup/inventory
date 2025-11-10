from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, selectinload
from models import Employee, City, db, Device
from utils import log_user_activity, admin_required
from datetime import datetime

employees_bp = Blueprint('employees', __name__)

@employees_bp.route('/employees')
@login_required
@admin_required
def employees():
    """Список співробітників"""
    # Для адміністраторів - всі міста, для звичайних користувачів - тільки своє місто
    if current_user.is_admin:
        employees_list = Employee.query.options(joinedload(Employee.city)).order_by(Employee.last_name, Employee.first_name).all()
        cities = City.query.all()
    else:
        employees_list = Employee.query.options(joinedload(Employee.city)).filter_by(city_id=current_user.city_id).order_by(Employee.last_name, Employee.first_name).all()
        cities = [current_user.city]
    
    return render_template('employees.html', employees=employees_list, cities=cities, current_user=current_user)

@employees_bp.route('/employees/<int:employee_id>')
@login_required
@admin_required
def employee_detail(employee_id):
    """Деталі співробітника"""
    employee = Employee.query.options(joinedload(Employee.city)).get_or_404(employee_id)
    
    # Перевіряємо доступ
    if not current_user.is_admin and employee.city_id != current_user.city_id:
        abort(403)
    
    # Отримуємо пристрої співробітника з eager loading
    devices = Device.query.options(joinedload(Device.city)).filter_by(assigned_to_employee_id=employee_id).all()
    
    return render_template('employee_detail.html', employee=employee, devices=devices)

@employees_bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_employee():
    """Додавання нового співробітника"""
    if request.method == 'POST':
        # Визначаємо місто
        if current_user.is_admin and request.form.get('city_id'):
            city_id = request.form.get('city_id', type=int)
        else:
            city_id = current_user.city_id
        
        employee = Employee(
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            middle_name=request.form.get('middle_name', ''),
            position=request.form.get('position', ''),
            department=request.form.get('department', ''),
            phone=request.form.get('phone', ''),
            email=request.form.get('email', ''),
            city_id=city_id,
            notes=request.form.get('notes', '')
        )
        
        db.session.add(employee)
        db.session.commit()
        
        log_user_activity(current_user.id, f'Додано співробітника: {employee.full_name}', request.remote_addr, request.url)
        flash(f'Співробітника {employee.full_name} успішно додано!', 'success')
        return redirect(url_for('employees.employees'))
    
    # GET request - показуємо форму
    if current_user.is_admin:
        cities = City.query.all()
    else:
        cities = [current_user.city]
    
    return render_template('add_employee.html', cities=cities)

@employees_bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_employee(employee_id):
    """Редагування співробітника"""
    employee = Employee.query.options(joinedload(Employee.city)).get_or_404(employee_id)
    
    # Перевіряємо доступ
    if not current_user.is_admin and employee.city_id != current_user.city_id:
        abort(403)
    
    if request.method == 'POST':
        employee.first_name = request.form['first_name']
        employee.last_name = request.form['last_name']
        employee.middle_name = request.form.get('middle_name', '')
        employee.position = request.form.get('position', '')
        employee.department = request.form.get('department', '')
        employee.phone = request.form.get('phone', '')
        employee.email = request.form.get('email', '')
        
        if current_user.is_admin and request.form.get('city_id'):
            employee.city_id = request.form.get('city_id', type=int)
        
        employee.notes = request.form.get('notes', '')
        employee.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        log_user_activity(current_user.id, f'Оновлено співробітника: {employee.full_name}', request.remote_addr, request.url)
        flash(f'Інформацію про {employee.full_name} успішно оновлено!', 'success')
        return redirect(url_for('employees.employee_detail', employee_id=employee_id))
    
    # GET request - показуємо форму
    if current_user.is_admin:
        cities = City.query.all()
    else:
        cities = [current_user.city]
    
    return render_template('edit_employee.html', employee=employee, cities=cities)

@employees_bp.route('/employees/<int:employee_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_employee(employee_id):
    """Видалення співробітника"""
    employee = Employee.query.options(joinedload(Employee.city)).get_or_404(employee_id)
    
    # Перевіряємо доступ
    if not current_user.is_admin and employee.city_id != current_user.city_id:
        abort(403)
    
    # Перевіряємо чи є пристрої, прив'язані до співробітника
    devices_count = Device.query.filter_by(assigned_to_employee_id=employee_id).count()
    if devices_count > 0:
        flash(f'Неможливо видалити: до співробітника прив\'язано {devices_count} пристрої(в)! Спочатку видаліть або переназначте пристрої.', 'error')
        return redirect(url_for('employees.employee_detail', employee_id=employee_id))
    
    employee_name = employee.full_name
    db.session.delete(employee)
    db.session.commit()
    
    log_user_activity(current_user.id, f'Видалено співробітника: {employee_name}', request.remote_addr, request.url)
    flash(f'Співробітника {employee_name} успішно видалено!', 'success')
    return redirect(url_for('employees.employees'))

@employees_bp.route('/employees/<int:employee_id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_employee_active(employee_id):
    """Активація/деактивація співробітника"""
    employee = Employee.query.options(joinedload(Employee.city)).get_or_404(employee_id)
    
    # Перевіряємо доступ
    if not current_user.is_admin and employee.city_id != current_user.city_id:
        abort(403)
    
    employee.is_active = not employee.is_active
    db.session.commit()
    
    status = 'активовано' if employee.is_active else 'деактивовано'
    log_user_activity(current_user.id, f'Співробітника {employee.full_name} {status}', request.remote_addr, request.url)
    flash(f'Співробітника {employee.full_name} {status}!', 'success')
    
    return redirect(url_for('employees.employee_detail', employee_id=employee_id))

