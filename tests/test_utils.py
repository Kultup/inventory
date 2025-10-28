import unittest
import os
import tempfile
from datetime import datetime
from app import app
from models import db, Device, City, User, Notification
from utils import (
    generate_inventory_number,
    allowed_file,
    backup_database,
    check_maintenance_reminders
)
from werkzeug.security import generate_password_hash

class UtilsTestCase(unittest.TestCase):
    """Тести для допоміжних функцій"""
    
    def setUp(self):
        """Налаштування тестового середовища"""
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        
        self.app = app
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        db.create_all()
        
        # Створюємо тестове місто
        self.city = City(name='Тестове місто')
        db.session.add(self.city)
        db.session.commit()
    
    def tearDown(self):
        """Очищення після тестів"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def test_allowed_file(self):
        """Тест перевірки дозволених файлів"""
        self.assertTrue(allowed_file('image.png'))
        self.assertTrue(allowed_file('photo.jpg'))
        self.assertTrue(allowed_file('picture.jpeg'))
        self.assertTrue(allowed_file('animation.gif'))
        
        self.assertFalse(allowed_file('document.pdf'))
        self.assertFalse(allowed_file('script.exe'))
        self.assertFalse(allowed_file('noextension'))
    
    def test_generate_inventory_number(self):
        """Тест генерації інвентарного номера"""
        inv_num = generate_inventory_number()
        
        # Перевіряємо формат YYYY-NNNN
        self.assertRegex(inv_num, r'^\d{4}-\d{4}$')
        
        # Перевіряємо рік
        current_year = datetime.now().year
        self.assertTrue(inv_num.startswith(str(current_year)))
    
    def test_generate_inventory_number_sequential(self):
        """Тест послідовної генерації інвентарних номерів"""
        # Створюємо декілька пристроїв
        for i in range(3):
            inv_num = generate_inventory_number()
            device = Device(
                name=f'Пристрій {i}',
                type='Тест',
                serial_number=f'SN{i}',
                inventory_number=inv_num,
                city_id=self.city.id
            )
            db.session.add(device)
            db.session.commit()
        
        # Перевіряємо, що номери йдуть послідовно
        devices = Device.query.order_by(Device.inventory_number).all()
        self.assertEqual(len(devices), 3)
        
        for i, device in enumerate(devices):
            expected_num = f'{datetime.now().year}-{i+1:04d}'
            self.assertEqual(device.inventory_number, expected_num)
    
    def test_check_maintenance_reminders_overdue(self):
        """Тест перевірки прострочених обслуговувань"""
        from datetime import date, timedelta
        
        # Створюємо користувача
        user = User(
            username='testuser',
            password_hash=generate_password_hash('password'),
            city_id=self.city.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Створюємо пристрій з простроченим обслуговуванням
        device = Device(
            name='Пристрій з простроченим обслуговуванням',
            type='Комп\'ютер',
            serial_number='SN_OVERDUE',
            inventory_number='2025-0001',
            city_id=self.city.id,
            last_maintenance=date.today() - timedelta(days=400),
            maintenance_interval=365
        )
        device.update_next_maintenance()
        db.session.add(device)
        db.session.commit()
        
        # Перевіряємо нагадування
        result = check_maintenance_reminders()
        
        self.assertGreater(result['overdue'], 0)
        
        # Перевіряємо, що створено нагадування
        notification = Notification.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.type, 'danger')
    
    def test_check_maintenance_reminders_soon(self):
        """Тест перевірки майбутніх обслуговувань"""
        from datetime import date, timedelta
        
        # Створюємо користувача
        user = User(
            username='testuser',
            password_hash=generate_password_hash('password'),
            city_id=self.city.id
        )
        db.session.add(user)
        db.session.commit()
        
        # Створюємо пристрій з майбутнім обслуговуванням
        device = Device(
            name='Пристрій з майбутнім обслуговуванням',
            type='Комп\'ютер',
            serial_number='SN_SOON',
            inventory_number='2025-0002',
            city_id=self.city.id,
            last_maintenance=date.today() - timedelta(days=350),
            maintenance_interval=365
        )
        device.update_next_maintenance()
        db.session.add(device)
        db.session.commit()
        
        # Перевіряємо нагадування
        result = check_maintenance_reminders()
        
        self.assertGreater(result['soon'], 0)
        
        # Перевіряємо, що створено нагадування
        notification = Notification.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.type, 'warning')

if __name__ == '__main__':
    unittest.main()

