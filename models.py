from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class City(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    users = db.relationship('User', backref='city', lazy=True)
    devices = db.relationship('Device', backref='city', lazy=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    city_id = db.Column(db.Integer, db.ForeignKey('city.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Зв'язки
    activities = db.relationship('UserActivity', backref='user', lazy=True)
    device_histories = db.relationship('DeviceHistory', backref='user', lazy=True)

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False, index=True)
    serial_number = db.Column(db.String(100), unique=True, index=True)
    inventory_number = db.Column(db.String(20), unique=True, index=True)
    location = db.Column(db.String(200), index=True)
    status = db.Column(db.String(50), index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    city_id = db.Column(db.Integer, db.ForeignKey('city.id'), nullable=False, index=True)
    assigned_to_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True, index=True)
    last_maintenance = db.Column(db.Date, index=True)
    maintenance_interval = db.Column(db.Integer, default=365)
    next_maintenance = db.Column(db.Date, index=True)
    
    # Фінансові поля
    purchase_price = db.Column(db.Numeric(10, 2))  # Вартість покупки
    purchase_date = db.Column(db.Date)  # Дата покупки
    depreciation_rate = db.Column(db.Numeric(5, 2), default=20.0)  # Відсоток амортизації річний
    repair_expenses = db.relationship('RepairExpense', backref='device', lazy=True, cascade='all, delete-orphan')
    
    # Зв'язки
    photos = db.relationship('DevicePhoto', backref='device', lazy=True, cascade='all, delete-orphan')
    histories = db.relationship('DeviceHistory', backref='device', lazy=True)
    
    def update_next_maintenance(self):
        """Оновлює дату наступного обслуговування на основі останнього обслуговування та інтервалу"""
        if self.last_maintenance and self.maintenance_interval:
            from datetime import timedelta
            self.next_maintenance = self.last_maintenance + timedelta(days=self.maintenance_interval)
        else:
            self.next_maintenance = None
    
    @property
    def current_value(self):
        """Поточна вартість пристрою з урахуванням амортизації"""
        if not self.purchase_price or not self.purchase_date:
            return None
        
        from datetime import date
        today = date.today()
        years_old = (today - self.purchase_date).days / 365.25
        
        if years_old <= 0:
            return float(self.purchase_price)
        
        # Лінійна амортизація
        depreciation_amount = float(self.purchase_price) * (float(self.depreciation_rate) / 100) * years_old
        current = float(self.purchase_price) - depreciation_amount
        
        return max(current, 0)  # Не може бути від'ємним
    
    @property
    def total_repair_expenses(self):
        """Загальні витрати на ремонт"""
        if not self.repair_expenses:
            return 0
        return sum(float(exp.amount) for exp in self.repair_expenses)
    
    @property
    def total_cost(self):
        """Загальна вартість (покупка + ремонт)"""
        purchase = float(self.purchase_price) if self.purchase_price else 0
        return purchase + self.total_repair_expenses

class RepairExpense(db.Model):
    """Модель витрат на ремонт пристрою"""
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)  # Сума витрат
    description = db.Column(db.String(500))  # Опис робіт
    repair_date = db.Column(db.Date, nullable=False)  # Дата ремонту
    invoice_number = db.Column(db.String(100))  # Номер накладної
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<RepairExpense {self.amount} for device {self.device_id}>'

class DevicePhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class DeviceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=True)  # Може бути NULL для видалених пристроїв
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    field = db.Column(db.String(50))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Додаткові поля для збереження інформації про видалені пристрої
    device_name = db.Column(db.String(100))
    device_inventory_number = db.Column(db.String(20))
    device_type = db.Column(db.String(50))
    device_serial_number = db.Column(db.String(100))

class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    url = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Employee(db.Model):
    """Модель співробітника"""
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    position = db.Column(db.String(100))  # Посада
    department = db.Column(db.String(100))  # Відділ
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    city_id = db.Column(db.Integer, db.ForeignKey('city.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Зв'язки
    city = db.relationship('City', backref='employees', lazy=True)
    
    def __repr__(self):
        return f'<Employee {self.first_name} {self.last_name}>'
    
    @property
    def full_name(self):
        """Повне ім'я співробітника"""
        name_parts = [self.last_name, self.first_name]
        if self.middle_name:
            name_parts.append(self.middle_name)
        return ' '.join(name_parts)
    
    @property
    def short_name(self):
        """Коротке ім'я (Прізвище І. П.)"""
        result = self.last_name
        if self.first_name:
            result += f' {self.first_name[0]}.'
        if self.middle_name:
            result += f' {self.middle_name[0]}.'
        return result


class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    type = db.Column(db.String(50), default='info')  # info, warning, danger, success
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    user = db.relationship('User', backref='notifications', lazy=True)