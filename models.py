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
    last_maintenance = db.Column(db.Date, index=True)
    maintenance_interval = db.Column(db.Integer, default=365)
    next_maintenance = db.Column(db.Date, index=True)
    
    # Зв'язки
    photos = db.relationship('DevicePhoto', backref='device', lazy=True, cascade='all, delete-orphan')
    histories = db.relationship('DeviceHistory', backref='device', lazy=True, cascade='all, delete-orphan')
    
    def update_next_maintenance(self):
        """Оновлює дату наступного обслуговування на основі останнього обслуговування та інтервалу"""
        if self.last_maintenance and self.maintenance_interval:
            from datetime import timedelta
            self.next_maintenance = self.last_maintenance + timedelta(days=self.maintenance_interval)
        else:
            self.next_maintenance = None

class DevicePhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class DeviceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    field = db.Column(db.String(50))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    url = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)



class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)