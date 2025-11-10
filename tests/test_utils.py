import unittest
import sys
import os
import tempfile
from datetime import datetime

# Додаємо кореневий каталог проєкту до PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        # last_maintenance було 400 днів тому, інтервал 365 днів
        # next_maintenance = last_maintenance + 365 = date.today() - 35 днів (прострочене)
        last_maintenance = date.today() - timedelta(days=400)
        device = Device(
            name='Пристрій з простроченим обслуговуванням',
            type='Комп\'ютер',
            serial_number='SN_OVERDUE',
            inventory_number='2025-0001',
            city_id=self.city.id,
            status='В роботі',  # Встановлюємо статус, щоб пройти фільтр
            last_maintenance=last_maintenance,
            maintenance_interval=365
        )
        db.session.add(device)
        db.session.flush()  # Отримуємо ID пристрою
        
        # Оновлюємо дату наступного обслуговування
        device.update_next_maintenance()
        db.session.commit()
        
        # Перевіряємо, що next_maintenance встановлено правильно
        self.assertIsNotNone(device.next_maintenance)
        self.assertLess(device.next_maintenance, date.today())
        
        # Оновлюємо об'єкт з бази даних для перевірки
        db.session.refresh(device)
        self.assertIsNotNone(device.next_maintenance)
        self.assertLess(device.next_maintenance, date.today())
        
        # Перевіряємо, що пристрій знайдено в базі
        all_devices = Device.query.all()
        self.assertGreater(len(all_devices), 0, "Device should exist in database")
        
        # Перевіряємо, що пристрій проходить фільтр
        overdue_devices_query = Device.query.filter(
            Device.next_maintenance.isnot(None),
            Device.next_maintenance < date.today(),
            Device.status != 'Списано'
        ).all()
        self.assertGreater(len(overdue_devices_query), 0, f"Device should be found by query. Device status: {device.status}, next_maintenance: {device.next_maintenance}, today: {date.today()}")
        
        # Перевіряємо нагадування
        result = check_maintenance_reminders()
        
        self.assertGreater(result['overdue'], 0, f"Expected overdue > 0, got {result['overdue']}. Device next_maintenance: {device.next_maintenance}, today: {date.today()}, status: {device.status}")
        
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
        # last_maintenance було 350 днів тому, інтервал 365 днів
        # next_maintenance = last_maintenance + 365 = date.today() + 15 днів (скоро)
        last_maintenance = date.today() - timedelta(days=350)
        device = Device(
            name='Пристрій з майбутнім обслуговуванням',
            type='Комп\'ютер',
            serial_number='SN_SOON',
            inventory_number='2025-0002',
            city_id=self.city.id,
            status='В роботі',  # Встановлюємо статус, щоб пройти фільтр
            last_maintenance=last_maintenance,
            maintenance_interval=365
        )
        db.session.add(device)
        db.session.flush()  # Отримуємо ID пристрою
        
        # Оновлюємо дату наступного обслуговування
        device.update_next_maintenance()
        db.session.commit()
        
        # Перевіряємо, що next_maintenance встановлено правильно
        self.assertIsNotNone(device.next_maintenance)
        self.assertGreaterEqual(device.next_maintenance, date.today())
        self.assertLessEqual(device.next_maintenance, date.today() + timedelta(days=30))
        
        # Оновлюємо об'єкт з бази даних для перевірки
        db.session.refresh(device)
        self.assertIsNotNone(device.next_maintenance)
        self.assertGreaterEqual(device.next_maintenance, date.today())
        self.assertLessEqual(device.next_maintenance, date.today() + timedelta(days=30))
        
        # Перевіряємо, що пристрій знайдено в базі
        all_devices = Device.query.all()
        self.assertGreater(len(all_devices), 0, "Device should exist in database")
        
        # Перевіряємо, що пристрій проходить фільтр
        soon_date = date.today() + timedelta(days=30)
        soon_devices_query = Device.query.filter(
            Device.next_maintenance.isnot(None),
            Device.next_maintenance >= date.today(),
            Device.next_maintenance <= soon_date,
            Device.status != 'Списано'
        ).all()
        self.assertGreater(len(soon_devices_query), 0, f"Device should be found by query. Device status: {device.status}, next_maintenance: {device.next_maintenance}, today: {date.today()}, soon_date: {soon_date}")
        
        # Перевіряємо нагадування
        result = check_maintenance_reminders()
        
        self.assertGreater(result['soon'], 0, f"Expected soon > 0, got {result['soon']}. Device next_maintenance: {device.next_maintenance}, today: {date.today()}, soon_date: {date.today() + timedelta(days=30)}, status: {device.status}")
        
        # Перевіряємо, що створено нагадування
        notification = Notification.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.type, 'warning')

if __name__ == '__main__':
    unittest.main()

