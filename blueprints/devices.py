from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, send_from_directory, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_
import os
import uuid
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from datetime import datetime, date
import qrcode
from PIL import Image

# Імпорти моделей та функцій
from models import Device, DevicePhoto, DeviceHistory, City, User, db
from utils import allowed_file, record_device_history, generate_inventory_number, log_user_activity

devices_bp = Blueprint('devices', __name__)

@devices_bp.route('/devices')
@login_required
def devices():
    # Параметри пагінації та фільтрації
    selected_city_id = request.args.get('city_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)  # Збільшено до 20 записів
    
    # Параметри пошуку та фільтрації
    search = request.args.get('search', '').strip()
    device_type = request.args.get('type', '').strip()
    status = request.args.get('status', '').strip()
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    
    # Базовий запит
    if current_user.is_admin:
        cities = City.query.all()
        query = Device.query
        if selected_city_id:
            query = query.filter_by(city_id=selected_city_id)
    else:
        cities = [current_user.city]
        query = Device.query.filter_by(city_id=current_user.city_id)
        selected_city_id = current_user.city_id
    
    # Розширений пошук по всіх полях
    if search:
        search_filter = or_(
            Device.name.ilike(f'%{search}%'),
            Device.type.ilike(f'%{search}%'),
            Device.serial_number.ilike(f'%{search}%'),
            Device.inventory_number.ilike(f'%{search}%'),
            Device.location.ilike(f'%{search}%'),
            Device.notes.ilike(f'%{search}%')
        )
        query = query.filter(search_filter)
    
    # Фільтр по типу пристрою
    if device_type:
        query = query.filter(Device.type.ilike(f'%{device_type}%'))
    
    # Фільтр по статусу
    if status:
        query = query.filter(Device.status.ilike(f'%{status}%'))
    
    # Сортування
    if sort_by in ['name', 'type', 'serial_number', 'inventory_number', 'location', 'status', 'created_at', 'last_maintenance']:
        sort_column = getattr(Device, sort_by)
        if sort_order == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(Device.created_at.desc())
    
    # Застосовуємо пагінацію з оптимізацією
    pagination = query.paginate(
        page=page, 
        per_page=min(per_page, 100),  # Максимум 100 записів на сторінку
        error_out=False
    )
    devices = pagination.items
    
    # Отримуємо унікальні типи та статуси для фільтрів
    device_types = db.session.query(Device.type).distinct().filter(Device.type.isnot(None)).all()
    device_statuses = db.session.query(Device.status).distinct().filter(Device.status.isnot(None)).all()
    
    return render_template('devices.html', 
                          devices=devices, 
                          cities=cities,
                          selected_city_id=selected_city_id, 
                          pagination=pagination,
                          search=search,
                          device_type=device_type,
                          status=status,
                          sort_by=sort_by,
                          sort_order=sort_order,
                          device_types=[t[0] for t in device_types],
                          device_statuses=[s[0] for s in device_statuses],
                          per_page=per_page)

@devices_bp.route('/device/add', methods=['GET', 'POST'])
@login_required
def add_device():
    if request.method == 'POST':
        # Перевіряємо чи існує пристрій з таким серійним номером
        serial_number = request.form['serial_number']
        existing_device = Device.query.filter_by(serial_number=serial_number).first()
        if existing_device:
            flash('Пристрій з таким серійним номером вже існує!', 'error')
            if current_user.is_admin:
                cities = City.query.all()
            else:
                cities = [current_user.city]
            return render_template('add_device.html', cities=cities)

        # Визначаємо місто для пристрою
        if current_user.is_admin and request.form.get('city_id'):
            city_id = request.form.get('city_id', type=int)
            city = City.query.get(city_id)
            city_prefix = city.name if city else ""
        else:
            city_id = current_user.city_id
            city_prefix = current_user.city.name if current_user.city else ""
        
        # Генеруємо унікальний інвентарний номер
        inventory_number = generate_inventory_number()
        
        # Отримуємо дату останнього обслуговування
        last_maintenance = request.form.get('last_maintenance')
        maintenance_interval = request.form.get('maintenance_interval', 365, type=int)
        
        if last_maintenance:
            try:
                last_maintenance_date = datetime.strptime(last_maintenance, '%Y-%m-%d')
            except ValueError:
                last_maintenance_date = None
        else:
            last_maintenance_date = None
            
        device = Device(
            name=request.form['name'],
            type=request.form['type'],
            serial_number=request.form['serial_number'],
            inventory_number=inventory_number,
            location=request.form['location'],
            status=request.form['status'],
            notes=request.form['notes'],
            city_id=city_id,
            last_maintenance=last_maintenance_date,
            maintenance_interval=maintenance_interval
        )
        
        # Оновлюємо дату наступного обслуговування
        device.update_next_maintenance()
        
        db.session.add(device)
        db.session.flush()  # Отримуємо ID без коміту
        
        # Записуємо історію створення
        record_device_history(device.id, current_user.id, 'create')
        
        # Обробка файлів, якщо вони були завантажені
        if 'photos' in request.files:
            photos = request.files.getlist('photos')
            for photo in photos:
                if photo and allowed_file(photo.filename):
                    # Генеруємо унікальне ім'я файлу
                    filename = secure_filename(photo.filename)
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    
                    # Зберігаємо файл
                    photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
                    
                    # Створюємо запис у базі даних
                    device_photo = DevicePhoto(
                        filename=unique_filename,
                        original_filename=filename,
                        device_id=device.id
                    )
                    db.session.add(device_photo)
        
        db.session.commit()
        log_user_activity(current_user.id, f'Додано новий пристрій: {device.name}', request.remote_addr, request.url)
        flash('Пристрій успішно додано!')
        return redirect(url_for('devices.devices'))
    
    # Отримуємо список міст для адміністраторів
    if current_user.is_admin:
        cities = City.query.all()
    else:
        cities = [current_user.city]
        
    return render_template('add_device.html', cities=cities)

@devices_bp.route('/device/<int:device_id>')
@login_required
def device_detail(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
        
    return render_template('device_detail.html', device=device, now=date.today())

@devices_bp.route('/device/<int:device_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_device(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    if request.method == 'POST':
        # Визначаємо місто для пристрою
        if current_user.is_admin and request.form.get('city_id'):
            new_city_id = request.form.get('city_id', type=int)
            if device.city_id != new_city_id:
                old_city = device.city.name if device.city else "Не вказано"
                new_city = City.query.get(new_city_id).name
                record_device_history(device.id, current_user.id, 'update', 'city', old_city, new_city)
                device.city_id = new_city_id
        
        # Відстежуємо зміни основних полів
        fields_to_track = {
            'name': 'Назва',
            'type': 'Тип',
            'serial_number': 'Серійний номер',
            'location': 'Розташування',
            'status': 'Статус',
            'notes': 'Примітки'
        }
        
        for field, label in fields_to_track.items():
            old_value = getattr(device, field)
            new_value = request.form[field]
            if old_value != new_value:
                record_device_history(device.id, current_user.id, 'update', label, old_value, new_value)
                setattr(device, field, new_value)
        
        # Обробляємо дані обслуговування
        last_maintenance = request.form.get('last_maintenance')
        if last_maintenance:
            try:
                last_maintenance_date = datetime.strptime(last_maintenance, '%Y-%m-%d')
                if device.last_maintenance != last_maintenance_date:
                    old_value = device.last_maintenance.strftime('%Y-%m-%d') if device.last_maintenance else "Не вказано"
                    record_device_history(device.id, current_user.id, 'update', 'Дата обслуговування', old_value, last_maintenance)
                    device.last_maintenance = last_maintenance_date
            except ValueError:
                pass  # Ігноруємо неправильний формат дати
        else:
            if device.last_maintenance:
                old_value = device.last_maintenance.strftime('%Y-%m-%d')
                record_device_history(device.id, current_user.id, 'update', 'Дата обслуговування', old_value, "Не вказано")
                device.last_maintenance = None
        
        maintenance_interval = request.form.get('maintenance_interval', type=int)
        if maintenance_interval and device.maintenance_interval != maintenance_interval:
            old_value = str(device.maintenance_interval) if device.maintenance_interval else "365"
            record_device_history(device.id, current_user.id, 'update', 'Інтервал обслуговування', old_value, str(maintenance_interval))
            device.maintenance_interval = maintenance_interval
        
        # Оновлюємо дату наступного обслуговування
        device.update_next_maintenance()
        
        db.session.commit()
        flash('Пристрій успішно оновлено!')
        return redirect(url_for('devices.device_detail', device_id=device.id))
    
    # Отримуємо список міст для адміністраторів
    if current_user.is_admin:
        cities = City.query.all()
    else:
        cities = [current_user.city]
        
    return render_template('edit_device.html', device=device, cities=cities)

@devices_bp.route('/device/<int:device_id>/delete', methods=['POST'])
@login_required
def delete_device(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    # Записуємо історію видалення
    record_device_history(device.id, current_user.id, 'delete')
    
    # Видаляємо фотографії пристрою з файлової системи
    for photo in device.photos:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename))
        except:
            # Якщо файл не знайдено, просто продовжуємо
            pass
    
    # Видаляємо пристрій (каскадне видалення також видалить записи фото)
    db.session.delete(device)
    db.session.commit()
    
    flash('Пристрій успішно видалено!')
    return redirect(url_for('devices.devices'))



@devices_bp.route('/device/<int:device_id>/add_photo', methods=['POST'])
@login_required
def add_device_photo(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    if 'photo' in request.files:
        photo = request.files['photo']
        if photo and allowed_file(photo.filename):
            # Генеруємо унікальне ім'я файлу
            filename = secure_filename(photo.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            
            # Зберігаємо файл
            photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
            
            # Створюємо запис у базі даних
            device_photo = DevicePhoto(
                filename=unique_filename,
                original_filename=filename,
                device_id=device.id
            )
            db.session.add(device_photo)
            db.session.commit()
            
            flash('Фото успішно додано!')
    
    return redirect(url_for('devices.device_detail', device_id=device_id))

@devices_bp.route('/device/photo/<int:photo_id>/delete', methods=['POST'])
@login_required
def delete_device_photo(photo_id):
    photo = DevicePhoto.query.get_or_404(photo_id)
    device = photo.device
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    # Видаляємо файл
    try:
        os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename))
    except:
        # Якщо файл не знайдено, просто продовжуємо
        pass
    
    # Видаляємо запис з бази даних
    db.session.delete(photo)
    db.session.commit()
    
    flash('Фото успішно видалено!')
    return redirect(url_for('devices.device_detail', device_id=device.id))

@devices_bp.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    # Отримуємо фото, щоб перевірити права доступу
    photo = DevicePhoto.query.filter_by(filename=filename).first_or_404()
    device = photo.device
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
        
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@devices_bp.route('/device/<int:device_id>/history')
@login_required
def device_history(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    history = DeviceHistory.query.filter_by(device_id=device_id).order_by(DeviceHistory.timestamp.desc()).all()
    return render_template('device_history.html', device=device, history=history)

@devices_bp.route('/device/<int:device_id>/qrcode')
@login_required
def device_qrcode(device_id):
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    # Створюємо QR-код з інформацією про пристрій
    qr_data = f"""
    ID: {device.id}
    Назва: {device.name}
    Інв. номер: {device.inventory_number}
    Тип: {device.type}
    S/N: {device.serial_number}
    Розташування: {device.location}
    Статус: {device.status}
    Місто: {device.city.name}
    """
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Зберігаємо QR-код у буфер пам'яті
    img_buffer = io.BytesIO()
    img.save(img_buffer)
    img_buffer.seek(0)
    
    return send_file(
        img_buffer,
        mimetype='image/png',
        as_attachment=True,
        download_name=f'qrcode_{device.inventory_number}.png'
    )

@devices_bp.route('/device/<int:device_id>/print_qrcode')
@login_required
def print_device_qrcode(device_id):
    """Відображення сторінки для друку QR-коду пристрою"""
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    return render_template('print_qrcode.html', device=device)

@devices_bp.route('/device/<int:device_id>/print_inventory')
@login_required
def print_inventory(device_id):
    """Відображення сторінки для друку інвентарного номера пристрою"""
    device = Device.query.get_or_404(device_id)
    
    # Перевіряємо, чи має користувач доступ до цього пристрою
    if not current_user.is_admin and device.city_id != current_user.city_id:
        abort(403)
    
    # Логуємо активність користувача
    log_user_activity(current_user.id, f'Друк інвентарного номера пристрою: {device.name}', request.remote_addr, request.url)
    
    return render_template('print_inventory.html', device=device)

@devices_bp.route('/devices/import_excel', methods=['GET', 'POST'])
@login_required
def import_excel():
    """Імпорт пристроїв з Excel файлу"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не вибрано!', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Файл не вибрано!', 'error')
            return redirect(request.url)
        
        if file and file.filename.endswith(('.xlsx', '.xls')):
            try:
                # Читаємо Excel файл
                workbook = openpyxl.load_workbook(file)
                sheet = workbook.active
                
                imported_count = 0
                errors = []
                
                # Визначаємо місто для пристроїв
                if current_user.is_admin and request.form.get('city_id'):
                    city_id = request.form.get('city_id', type=int)
                    city = City.query.get(city_id)
                    city_prefix = city.name if city else ""
                else:
                    city_id = current_user.city_id
                    city_prefix = current_user.city.name if current_user.city else ""
                
                # Пропускаємо заголовок (перший рядок)
                for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                    if not any(row):  # Пропускаємо порожні рядки
                        continue
                    
                    try:
                        name = str(row[0]) if row[0] else f"Пристрій {row_num}"
                        device_type = str(row[1]) if row[1] else "Не вказано"
                        serial_number = str(row[2]) if row[2] else ""
                        location = str(row[3]) if row[3] else ""
                        status = str(row[4]) if row[4] else "Активний"
                        notes = str(row[5]) if row[5] else ""
                        
                        # Перевіряємо, чи існує пристрій з таким серійним номером
                        if serial_number and Device.query.filter_by(serial_number=serial_number).first():
                            errors.append(f"Рядок {row_num}: Пристрій з серійним номером {serial_number} вже існує")
                            continue
                        
                        # Генеруємо унікальний інвентарний номер
                        inventory_number = generate_inventory_number()
                        
                        device = Device(
                            name=name,
                            type=device_type,
                            serial_number=serial_number,
                            inventory_number=inventory_number,
                            location=location,
                            status=status,
                            notes=notes,
                            city_id=city_id
                        )
                        
                        db.session.add(device)
                        db.session.flush()  # Отримуємо ID без коміту
                        
                        # Записуємо історію створення
                        record_device_history(device.id, current_user.id, 'create')
                        
                        imported_count += 1
                        
                    except Exception as e:
                        errors.append(f"Рядок {row_num}: Помилка обробки - {str(e)}")
                        continue
                
                db.session.commit()
                
                if imported_count > 0:
                    flash(f'Успішно імпортовано {imported_count} пристрої(в)!', 'success')
                    log_user_activity(current_user.id, f'Імпортовано {imported_count} пристроїв з Excel', request.remote_addr, request.url)
                
                if errors:
                    for error in errors[:10]:  # Показуємо перші 10 помилок
                        flash(error, 'warning')
                    if len(errors) > 10:
                        flash(f'... та ще {len(errors) - 10} помилок', 'warning')
                
                return redirect(url_for('devices.devices'))
                
            except Exception as e:
                flash(f'Помилка при обробці файлу: {str(e)}', 'error')
                return redirect(request.url)
        else:
            flash('Дозволені тільки Excel файли (.xlsx, .xls)!', 'error')
            return redirect(request.url)
    
    # Отримуємо список міст для адміністраторів
    if current_user.is_admin:
        cities = City.query.all()
    else:
        cities = [current_user.city]
    
    return render_template('import_excel.html', cities=cities)

@devices_bp.route('/devices/export_excel')
@login_required
def export_excel():
    """Експорт пристроїв в Excel файл"""
    # Отримуємо пристрої відповідно до прав користувача
    if current_user.is_admin:
        devices = Device.query.all()
    else:
        devices = Device.query.filter_by(city_id=current_user.city_id).all()
    
    # Створюємо новий Excel файл
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Пристрої"
    
    # Заголовки стовпців
    headers = [
        'ID', 'Назва', 'Тип', 'Серійний номер', 'Інвентарний номер',
        'Розташування', 'Статус', 'Місто', 'Дата створення', 'Примітки'
    ]
    
    # Стилі для заголовків
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Записуємо заголовки
    for col, header in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = border
    
    # Записуємо дані пристроїв
    for row, device in enumerate(devices, 2):
        data = [
            device.id,
            device.name,
            device.type,
            device.serial_number,
            device.inventory_number,
            device.location,
            device.status,
            device.city.name if device.city else '',
            device.created_at.strftime('%Y-%m-%d %H:%M') if device.created_at else '',
            device.notes
        ]
        
        for col, value in enumerate(data, 1):
            cell = sheet.cell(row=row, column=col, value=value)
            cell.border = border
            cell.alignment = Alignment(vertical="center")
    
    # Автоматично підганяємо ширину стовпців
    for column in sheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        sheet.column_dimensions[column_letter].width = adjusted_width
    
    # Зберігаємо файл у буфер пам'яті
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    
    # Генеруємо ім'я файлу з поточною датою
    filename = f'devices_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    log_user_activity(current_user.id, f'Експортовано {len(devices)} пристроїв в Excel', request.remote_addr, request.url)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
     )

@devices_bp.route('/devices/bulk_print_inventory', methods=['GET', 'POST'])
@login_required
def bulk_print_inventory():
    """Масовий друк інвентарних номерів пристроїв"""
    if request.method == 'POST':
        device_ids = request.form.getlist('device_ids', type=int)
        
        if not device_ids:
            flash('Не вибрано жодного пристрою для друку!', 'warning')
            return redirect(url_for('devices.devices'))
        
        # Отримуємо пристрої відповідно до прав користувача
        if current_user.is_admin:
            devices = Device.query.filter(Device.id.in_(device_ids)).all()
        else:
            devices = Device.query.filter(
                Device.id.in_(device_ids),
                Device.city_id == current_user.city_id
            ).all()
        
        if not devices:
            flash('Не знайдено пристроїв для друку!', 'error')
            return redirect(url_for('devices.devices'))
        
        log_user_activity(current_user.id, f'Масовий друк {len(devices)} пристроїв', request.remote_addr, request.url)
        
        return render_template('bulk_print_inventory.html', devices=devices)
    
    # GET запит - показуємо сторінку вибору пристроїв
    # Отримуємо пристрої відповідно до прав користувача
    if current_user.is_admin:
        devices = Device.query.all()
        cities = City.query.all()
    else:
        devices = Device.query.filter_by(city_id=current_user.city_id).all()
        cities = [current_user.city]
    
    return render_template('bulk_print_select.html', devices=devices, cities=cities)