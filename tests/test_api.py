import unittest
import json
from app import app
from models import db, User, City, Device
from werkzeug.security import generate_password_hash

class APITestCase(unittest.TestCase):
    """Тести для REST API"""
    
    def setUp(self):
        """Налаштування тестового середовища"""
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        
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
            username='testapi',
            password_hash=generate_password_hash('password'),
            is_admin=True,
            city_id=self.city.id
        )
        db.session.add(self.user)
        db.session.commit()
        
        self.headers = {
            'X-API-Key': 'testapi',
            'Content-Type': 'application/json'
        }
    
    def tearDown(self):
        """Очищення після тестів"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def test_get_devices_without_api_key(self):
        """Тест доступу без API ключа"""
        response = self.client.get('/api/v1/devices')
        self.assertEqual(response.status_code, 401)
        
        data = json.loads(response.data)
        self.assertIn('error', data)
    
    def test_get_devices_with_api_key(self):
        """Тест отримання списку пристроїв"""
        # Створюємо тестовий пристрій
        device = Device(
            name='API Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='API_SN_001',
            inventory_number='2025-0001',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        
        response = self.client.get('/api/v1/devices', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('devices', data)
        self.assertGreater(len(data['devices']), 0)
    
    def test_get_single_device(self):
        """Тест отримання одного пристрою"""
        device = Device(
            name='API Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='API_SN_002',
            inventory_number='2025-0002',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        
        response = self.client.get(f'/api/v1/devices/{device.id}', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['name'], 'API Тестовий пристрій')
        self.assertEqual(data['serial_number'], 'API_SN_002')
    
    def test_create_device(self):
        """Тест створення пристрою через API"""
        device_data = {
            'name': 'Новий API пристрій',
            'type': 'Принтер',
            'serial_number': 'API_SN_NEW',
            'location': 'Офіс 1',
            'status': 'В роботі'
        }
        
        response = self.client.post(
            '/api/v1/devices',
            headers=self.headers,
            data=json.dumps(device_data)
        )
        
        self.assertEqual(response.status_code, 201)
        
        data = json.loads(response.data)
        self.assertIn('id', data)
        self.assertIn('inventory_number', data)
        
        # Перевіряємо, що пристрій створено
        device = Device.query.get(data['id'])
        self.assertIsNotNone(device)
        self.assertEqual(device.name, 'Новий API пристрій')
    
    def test_create_device_duplicate_serial(self):
        """Тест створення пристрою з дублікатом серійного номера"""
        # Створюємо пристрій
        device = Device(
            name='Існуючий пристрій',
            type='Комп\'ютер',
            serial_number='DUPLICATE_SN',
            inventory_number='2025-0003',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        
        # Намагаємось створити пристрій з тим же серійним номером
        device_data = {
            'name': 'Дублікат',
            'type': 'Комп\'ютер',
            'serial_number': 'DUPLICATE_SN'
        }
        
        response = self.client.post(
            '/api/v1/devices',
            headers=self.headers,
            data=json.dumps(device_data)
        )
        
        self.assertEqual(response.status_code, 409)
    
    def test_update_device(self):
        """Тест оновлення пристрою"""
        device = Device(
            name='Пристрій для оновлення',
            type='Комп\'ютер',
            serial_number='UPDATE_SN',
            inventory_number='2025-0004',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        
        update_data = {
            'status': 'На ремонті',
            'notes': 'Потребує діагностики'
        }
        
        response = self.client.put(
            f'/api/v1/devices/{device.id}',
            headers=self.headers,
            data=json.dumps(update_data)
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Перевіряємо оновлення
        db.session.refresh(device)
        self.assertEqual(device.status, 'На ремонті')
        self.assertEqual(device.notes, 'Потребує діагностики')
    
    def test_delete_device(self):
        """Тест видалення пристрою"""
        device = Device(
            name='Пристрій для видалення',
            type='Комп\'ютер',
            serial_number='DELETE_SN',
            inventory_number='2025-0005',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        device_id = device.id
        
        response = self.client.delete(
            f'/api/v1/devices/{device_id}',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Перевіряємо, що пристрій видалено
        device = Device.query.get(device_id)
        self.assertIsNone(device)
    
    def test_get_stats(self):
        """Тест отримання статистики"""
        # Створюємо декілька пристроїв
        for i in range(5):
            device = Device(
                name=f'Пристрій {i}',
                type='Комп\'ютер',
                serial_number=f'STAT_SN_{i}',
                inventory_number=f'2025-{i+1:04d}',
                status='В роботі' if i < 3 else 'На ремонті',
                city_id=self.city.id
            )
            db.session.add(device)
        db.session.commit()
        
        response = self.client.get('/api/v1/stats', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('total_devices', data)
        self.assertEqual(data['total_devices'], 5)
        self.assertEqual(data['active_devices'], 3)
        self.assertEqual(data['repair_devices'], 2)

if __name__ == '__main__':
    unittest.main()

