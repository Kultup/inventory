"""
Служба нагадувань для системи інвентаризації

Ця служба відповідає за:
- Нагадування про обслуговування пристроїв (за 3 дні)
- Нагадування про незаповнені дані (щодня, поки не виправлять)
"""

from flask import current_app
from datetime import date, timedelta, datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from models import Device, User, db, SystemSettings, DevicePhoto


class ReminderService:
    """Служба для управління нагадуваннями"""
    
    # Налаштування нагадувань
    MAINTENANCE_REMINDER_DAYS = 3  # За скільки днів нагадувати про обслуговування
    INCOMPLETE_DATA_CHECK_DAILY = True  # Перевіряти незаповнені дані щодня
    
    @staticmethod
    def _get_or_create_setting(key, value, description):
        """
        Безпечно отримує або створює запис SystemSettings.
        Обробляє race condition при одночасному створенні записів.
        
        Args:
            key: Ключ налаштування
            value: Значення
            description: Опис
            
        Returns:
            SystemSettings: Об'єкт налаштування
        """
        # Спочатку пробуємо отримати існуючий запис
        setting = SystemSettings.query.filter_by(key=key).first()
        if setting:
            return setting
        
        # Якщо не знайдено, пробуємо створити новий
        try:
            setting = SystemSettings(
                key=key,
                value=value,
                description=description
            )
            db.session.add(setting)
            db.session.commit()
            return setting
        except IntegrityError:
            # Якщо виникла помилка унікальності (race condition),
            # отримуємо запис, який створив інший процес
            db.session.rollback()
            setting = SystemSettings.query.filter_by(key=key).first()
            if setting:
                return setting
            # Якщо все ще не знайдено, повторюємо спробу
            raise
    
    @staticmethod
    def _try_create_lock(key, value, description):
        """
        Атомарно намагається створити lock. Повертає True, якщо lock був створений
        (ми перші), або False, якщо lock вже існує (інший процес вже створив його).
        
        Args:
            key: Ключ lock
            value: Значення
            description: Опис
            
        Returns:
            bool: True якщо lock був створений, False якщо вже існує
        """
        # Пробуємо створити lock атомарно
        # Якщо lock вже існує, отримаємо IntegrityError
        try:
            lock = SystemSettings(
                key=key,
                value=value,
                description=description
            )
            db.session.add(lock)
            db.session.commit()
            return True
        except IntegrityError:
            # Якщо виникла помилка унікальності (race condition),
            # інший процес вже створив lock
            db.session.rollback()
            return False
    
    @staticmethod
    def check_maintenance_reminders():
        """
        Інтеграцію з Telegram видалено. Функція залишена як заглушка.
        
        Повертає нульові значення без відправки повідомлень.
        """
        try:
            return {'overdue': 0, 'soon': 0, 'notifications_sent': 0}
        except Exception as e:
            current_app.logger.error(f"Помилка при перевірці обслуговування: {e}", exc_info=True)
            db.session.rollback()
            return {'overdue': 0, 'soon': 0, 'notifications_sent': 0}
    
    @staticmethod
    def check_incomplete_data_reminders():
        """
        Інтеграцію з Telegram видалено. Функція залишена як заглушка.
        
        Повертає нульові значення без відправки повідомлень.
        """
        try:
                return {'notifications_sent': 0, 'types': 0}
        except Exception as e:
            current_app.logger.error(f"Помилка при перевірці незаповнених даних: {e}", exc_info=True)
            db.session.rollback()
            return {'notifications_sent': 0, 'types': 0}

