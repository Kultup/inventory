"""
Конфігурація pytest для тестів
"""
import pytest
import sys
import os

# Додаємо кореневий каталог проєкту до PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import User, City, Device
from werkzeug.security import generate_password_hash

@pytest.fixture
def client():
    """Фікстура для тестового клієнта"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

@pytest.fixture
def test_city():
    """Фікстура для тестового міста"""
    city = City(name='Тестове місто')
    db.session.add(city)
    db.session.commit()
    return city

@pytest.fixture
def test_user(test_city):
    """Фікстура для тестового користувача"""
    user = User(
        username='testuser',
        password_hash=generate_password_hash('password'),
        is_admin=True,
        city_id=test_city.id
    )
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture
def test_device(test_city):
    """Фікстура для тестового пристрою"""
    device = Device(
        name='Тестовий пристрій',
        type='Комп\'ютер',
        serial_number='TEST_SN_001',
        inventory_number='2025-0001',
        city_id=test_city.id
    )
    db.session.add(device)
    db.session.commit()
    return device

