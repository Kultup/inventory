"""
Тести для фінансового модуля
"""
import unittest
import sys
import os
from datetime import date, timedelta

# Додаємо кореневий каталог проєкту до PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Device, City, RepairExpense
from werkzeug.security import generate_password_hash

class FinancialTestCase(unittest.TestCase):
    """Тести для фінансових розрахунків"""
    
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
    
    def tearDown(self):
        """Очищення після тестів"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def test_current_value_calculation(self):
        """Тест розрахунку поточної вартості з амортизацією"""
        # Створюємо пристрій з фінансовими даними
        purchase_date = date.today() - timedelta(days=365)  # 1 рік тому
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='FIN_SN_001',
            inventory_number='2025-0001',
            city_id=self.city.id,
            purchase_price=10000.00,
            purchase_date=purchase_date,
            depreciation_rate=20.0  # 20% на рік
        )
        db.session.add(device)
        db.session.commit()
        
        # Перевіряємо поточну вартість
        current_value = device.current_value
        self.assertIsNotNone(current_value)
        # Після 1 року з амортизацією 20% має бути близько 8000
        # Використовуємо 365.25 днів на рік, тому значення може трохи відрізнятися
        # Точний розрахунок: 10000 - (10000 * 0.20 * (365/365.25)) ≈ 8001.37
        expected_value = 10000.00 - (10000.00 * 0.20 * (365 / 365.25))
        self.assertAlmostEqual(current_value, expected_value, places=0)  # Округлюємо до цілого
        # Перевіряємо, що значення в межах 7990-8010
        self.assertGreaterEqual(current_value, 7990.0)
        self.assertLessEqual(current_value, 8010.0)
    
    def test_total_repair_expenses(self):
        """Тест розрахунку загальних витрат на ремонт"""
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='FIN_SN_002',
            inventory_number='2025-0002',
            city_id=self.city.id,
            purchase_price=5000.00
        )
        db.session.add(device)
        db.session.commit()
        
        # Додаємо витрати на ремонт
        expense1 = RepairExpense(
            device_id=device.id,
            amount=500.00,
            description='Заміна жорсткого диска',
            repair_date=date.today() - timedelta(days=30)
        )
        expense2 = RepairExpense(
            device_id=device.id,
            amount=300.00,
            description='Чистка від пилу',
            repair_date=date.today() - timedelta(days=10)
        )
        db.session.add(expense1)
        db.session.add(expense2)
        db.session.commit()
        
        # Перевіряємо загальні витрати
        total_expenses = device.total_repair_expenses
        self.assertEqual(total_expenses, 800.00)
    
    def test_total_cost_calculation(self):
        """Тест розрахунку загальної вартості (покупка + ремонт)"""
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='FIN_SN_003',
            inventory_number='2025-0003',
            city_id=self.city.id,
            purchase_price=10000.00
        )
        db.session.add(device)
        db.session.commit()
        
        # Додаємо витрати на ремонт
        expense = RepairExpense(
            device_id=device.id,
            amount=1500.00,
            description='Капітальний ремонт',
            repair_date=date.today()
        )
        db.session.add(expense)
        db.session.commit()
        
        # Перевіряємо загальну вартість
        total_cost = device.total_cost
        self.assertEqual(total_cost, 11500.00)
    
    def test_depreciation_over_time(self):
        """Тест амортизації з часом"""
        purchase_date = date.today() - timedelta(days=730)  # 2 роки тому
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='FIN_SN_004',
            inventory_number='2025-0004',
            city_id=self.city.id,
            purchase_price=10000.00,
            purchase_date=purchase_date,
            depreciation_rate=20.0  # 20% на рік
        )
        db.session.add(device)
        db.session.commit()
        
        # Після 2 років з амортизацією 20% має бути близько 6000
        # Використовуємо 365.25 днів на рік, тому значення може трохи відрізнятися
        # Точний розрахунок: 10000 - (10000 * 0.20 * (730/365.25)) ≈ 6002.74
        current_value = device.current_value
        expected_value = 10000.00 - (10000.00 * 0.20 * (730 / 365.25))
        self.assertAlmostEqual(current_value, expected_value, places=0)  # Округлюємо до цілого
        # Перевіряємо, що значення в межах 5990-6010
        self.assertGreaterEqual(current_value, 5990.0)
        self.assertLessEqual(current_value, 6010.0)
    
    def test_no_financial_data(self):
        """Тест пристрою без фінансових даних"""
        device = Device(
            name='Тестовий пристрій',
            type='Комп\'ютер',
            serial_number='FIN_SN_005',
            inventory_number='2025-0005',
            city_id=self.city.id
        )
        db.session.add(device)
        db.session.commit()
        
        # Перевіряємо, що поточна вартість None
        self.assertIsNone(device.current_value)
        # Але загальні витрати на ремонт мають бути 0
        self.assertEqual(device.total_repair_expenses, 0)
        # І загальна вартість теж 0
        self.assertEqual(device.total_cost, 0)

if __name__ == '__main__':
    unittest.main()

