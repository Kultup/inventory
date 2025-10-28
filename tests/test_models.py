import unittest
from datetime import datetime, date, timedelta
from app import app
from models import db, User, City, Device, DeviceHistory, Notification
from werkzeug.security import generate_password_hash

class ModelsTestCase(unittest.TestCase):
    """Тести для моделей"""
    
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
    
    def test_city_creation(self):
        """Тест створення міста"""
        city = City(name='Нове місто')
        db.session.add(city)
        db.session.commit()
        
        self.assertIsNotNone(city.id)
        self.assertEqual(city.name, 'Нове місто')
        self.assertIsNotNone(city.created_at)
    
    def test_user_creation(self):
        """Тест створення користувача"""
        user = User(
            username='testuser',
            password_hash=generate_password_hash('password'),
            is_admin=False,
            city_id=self.city.id
        )
        db.session.add(user)
        db.session.commit()
        
        self.assertIsNotNone(user.id)
        self.assertEqual(user.username, 'testuser')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_admin)
    
    def test_device_creation(self):
        """Тест створення пристрою"""
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='SN123456',
            inventory_number='2025-0001',
            location='Офіс 1',
            status='В роботі',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        
        self.assertIsNotNone(device.id)
        self.assertEqual(device.name, 'Тестовий пристрій')
        self.assertEqual(device.serial_number, 'SN123456')
    
    def test_device_maintenance_update(self):
        """Тест оновлення дати обслуговування"""
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='SN123456',
            inventory_number='2025-0001',
            city_id=self.city.id,
            last_maintenance=date.today(),
            maintenance_interval=365
        )
        
        device.update_next_maintenance()
        
        expected_date = date.today() + timedelta(days=365)
        self.assertEqual(device.next_maintenance, expected_date)
    
    def test_device_history_creation(self):
        """Тест створення історії пристрою"""
        user = User(
            username='testuser',
            password_hash=generate_password_hash('password'),
            city_id=self.city.id
        )
        db.session.add(user)
        db.session.commit()
        
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='SN123456',
            inventory_number='2025-0001',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        
        history = DeviceHistory(
            device_id=device.id,
            user_id=user.id,
            action='create',
            device_name=device.name,
            device_inventory_number=device.inventory_number
        )
        db.session.add(history)
        db.session.commit()
        
        self.assertIsNotNone(history.id)
        self.assertEqual(history.action, 'create')
        self.assertEqual(history.device_name, 'Тестовий пристрій')
    
    def test_notification_creation(self):
        """Тест створення нагадування"""
        user = User(
            username='testuser',
            password_hash=generate_password_hash('password'),
            city_id=self.city.id
        )
        db.session.add(user)
        db.session.commit()
        
        notification = Notification(
            user_id=user.id,
            title='Тестове нагадування',
            message='Це тестове повідомлення',
            type='info'
        )
        db.session.add(notification)
        db.session.commit()
        
        self.assertIsNotNone(notification.id)
        self.assertEqual(notification.title, 'Тестове нагадування')
        self.assertFalse(notification.is_read)

if __name__ == '__main__':
    unittest.main()

