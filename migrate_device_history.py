#!/usr/bin/env python3
"""
Скрипт міграції для додавання нових полів до таблиці DeviceHistory
"""

import sqlite3
import os

def migrate_database():
    """Додає нові поля до таблиці device_history"""
    
    # Шлях до бази даних
    db_path = os.path.join('instance', 'inventory.db')
    
    if not os.path.exists(db_path):
        print(f"База даних не знайдена: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Перевіряємо, чи існують нові поля
        cursor.execute("PRAGMA table_info(device_history)")
        columns = [column[1] for column in cursor.fetchall()]
        
        new_columns = [
            'device_name',
            'device_inventory_number', 
            'device_type',
            'device_serial_number'
        ]
        
        # Додаємо нові поля, якщо їх немає
        for column in new_columns:
            if column not in columns:
                if column == 'device_name':
                    cursor.execute(f"ALTER TABLE device_history ADD COLUMN {column} VARCHAR(100)")
                elif column == 'device_inventory_number':
                    cursor.execute(f"ALTER TABLE device_history ADD COLUMN {column} VARCHAR(20)")
                elif column == 'device_type':
                    cursor.execute(f"ALTER TABLE device_history ADD COLUMN {column} VARCHAR(50)")
                elif column == 'device_serial_number':
                    cursor.execute(f"ALTER TABLE device_history ADD COLUMN {column} VARCHAR(100)")
                print(f"Додано поле: {column}")
            else:
                print(f"Поле вже існує: {column}")
        
        # Змінюємо device_id на nullable (SQLite не підтримує ALTER COLUMN, тому пропускаємо)
        print("Увага: device_id залишається NOT NULL в SQLite. Це нормально для існуючих записів.")
        
        # Оновлюємо існуючі записи історії з інформацією про пристрої
        cursor.execute("""
            UPDATE device_history 
            SET device_name = (SELECT name FROM device WHERE device.id = device_history.device_id),
                device_inventory_number = (SELECT inventory_number FROM device WHERE device.id = device_history.device_id),
                device_type = (SELECT type FROM device WHERE device.id = device_history.device_id),
                device_serial_number = (SELECT serial_number FROM device WHERE device.id = device_history.device_id)
            WHERE device_name IS NULL
        """)
        
        updated_rows = cursor.rowcount
        print(f"Оновлено {updated_rows} існуючих записів історії")
        
        conn.commit()
        conn.close()
        
        print("Міграція успішно завершена!")
        return True
        
    except Exception as e:
        print(f"Помилка при міграції: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    migrate_database()