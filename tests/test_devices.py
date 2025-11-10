"""
Тести для групових операцій з пристроями
"""
import unittest
import json
import sys
import os

# Додаємо кореневий каталог проєкту до PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Device, City, User
from werkzeug.security import generate_password_hash
from flask_login import login_user

class DevicesTestCase(unittest.TestCase):
    """Тести для групових операцій з пристроями"""
    
    def setUp(self):
        """Налаштування тестового середовища"""
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        self.app = app
        self.client = app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        db.create_all()
        
        # Створюємо тестові дані
        self.city = City(name='Тестове місто')
        db.session.add(self.city)
        db.session.commit()
        
        self.user = User(
            username='testuser',
            password_hash=generate_password_hash('password'),
            is_admin=True,
            city_id=self.city.id
        )
        db.session.add(self.user)
        db.session.commit()
        
        # Створюємо тестові пристрої
        self.devices = []
        for i in range(5):
            device = Device(
                name=f'Пристрій {i+1}',
                type='Комп\'ютер',
                serial_number=f'BULK_SN_{i+1:03d}',
                inventory_number=f'2025-{i+1:04d}',
                status='В роботі',
                city_id=self.city.id
            )
            db.session.add(device)
            self.devices.append(device)
        db.session.commit()
    
    def tearDown(self):
        """Очищення після тестів"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def login(self):
        """Допоміжна функція для входу"""
        # Використовуємо Flask-Login для входу через сесію
        # Правильний спосіб - встановити сесію для тестового клієнта
        # Flask-Login зберігає user_id в сесії під ключем '_user_id'
        # Також потрібно встановити правильний формат для Flask-Login
        with self.client.session_transaction() as sess:
            # Flask-Login використовує '_user_id' як ключ
            sess['_user_id'] = str(self.user.id)
            sess['_fresh'] = True
            sess['_permanent'] = True
            # Додаємо інформацію про сесію
            sess['_remember'] = False
    
    def test_bulk_update_status(self):
        """Тест масового оновлення статусу"""
        self.login()
        
        # Отримуємо ID пристроїв
        device_ids = [d.id for d in self.devices[:3]]
        
        # Flask форми передають списки як окремі поля з однаковим ім'ям
        # Використовуємо MultiDict для передачі списку
        from werkzeug.datastructures import MultiDict
        data = MultiDict([('new_status', 'На ремонті')])
        for device_id in device_ids:
            data.add('device_ids', device_id)
        
        # Оновлюємо статус
        response = self.client.post(
            '/devices/bulk-update-status',
            data=data,
            follow_redirects=True
        )
        
        # Перевіряємо відповідь
        self.assertIn(response.status_code, [200, 302], f"Expected 200 or 302, got {response.status_code}")
        
        # Перевіряємо, що статус оновлено
        db.session.expire_all()  # Оновлюємо об'єкти з БД
        for device_id in device_ids:
            device = Device.query.get(device_id)
            self.assertIsNotNone(device, f"Device {device_id} should exist")
            self.assertEqual(device.status, 'На ремонті', f"Device {device_id} status should be 'На ремонті', got '{device.status}'")
    
    def test_bulk_export_excel(self):
        """Тест масового експорту в Excel"""
        self.login()
        
        device_ids = [d.id for d in self.devices]
        
        # Використовуємо MultiDict для передачі списку
        from werkzeug.datastructures import MultiDict
        data = MultiDict()
        for device_id in device_ids:
            data.add('device_ids', device_id)
        
        response = self.client.post(
            '/devices/bulk-export-excel',
            data=data
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    
    def test_bulk_export_pdf(self):
        """Тест масового експорту в PDF"""
        self.login()
        
        device_ids = [d.id for d in self.devices]
        
        # Використовуємо MultiDict для передачі списку
        from werkzeug.datastructures import MultiDict
        data = MultiDict()
        for device_id in device_ids:
            data.add('device_ids', device_id)
        
        # Правильний маршрут - /devices/export_pdf
        response = self.client.post(
            '/devices/export_pdf',
            data=data
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')

if __name__ == '__main__':
    unittest.main()

