import os
from datetime import timedelta
from dotenv import load_dotenv

# Завантажуємо змінні оточення з .env файлу
load_dotenv()

class Config:
    """Базова конфігурація"""
    
    # Основні налаштування Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Налаштування бази даних
    # Підтримка PostgreSQL та SQLite
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        # Якщо вказано DATABASE_URL, використовуємо його (для PostgreSQL)
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
        # Налаштування для PostgreSQL
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 10,
            'max_overflow': 20,
        }
    else:
        # За замовчуванням використовуємо SQLite
        SQLALCHEMY_DATABASE_URI = 'sqlite:///inventory.db'
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
        }
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Налаштування завантаження файлів
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'static/uploads'
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB
    
    # Налаштування пагінації
    DEVICES_PER_PAGE = int(os.environ.get('DEVICES_PER_PAGE', 20))
    MAX_DEVICES_PER_PAGE = int(os.environ.get('MAX_DEVICES_PER_PAGE', 100))
    
    # Налаштування сесії
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get('SESSION_LIFETIME_HOURS', 24)))
    
    # Налаштування логування
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'inventory.log')
    LOG_FORMAT = os.environ.get('LOG_FORMAT', 'json')  # 'json' або 'text'
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 10 * 1024 * 1024))  # 10MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 10))
    

    
    # Налаштування безпеки
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    # Налаштування локалізації
    LANGUAGES = ['uk', 'en']
    DEFAULT_LANGUAGE = 'uk'
    
    # Налаштування QR кодів
    QR_CODE_SIZE = int(os.environ.get('QR_CODE_SIZE', 200))
    QR_CODE_BORDER = int(os.environ.get('QR_CODE_BORDER', 4))
    
    # Налаштування резервного копіювання
    BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER') or 'backups'
    BACKUP_KEEP_DAYS = int(os.environ.get('BACKUP_KEEP_DAYS', 30))
    BACKUP_AUTO_ENABLED = os.environ.get('BACKUP_AUTO_ENABLED', 'false').lower() == 'true'
    
    # Налаштування Telegram бота для нагадувань
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')  # ID групи для нагадувань
    TELEGRAM_ENABLED = os.environ.get('TELEGRAM_ENABLED', 'false').lower() == 'true'
    
    @staticmethod
    def init_app(app):
        """Ініціалізація додатку з конфігурацією"""
        # Створення необхідних директорій
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)


class DevelopmentConfig(Config):
    """Конфігурація для розробки"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or 'sqlite:///inventory_dev.db'
    
class TestingConfig(Config):
    """Конфігурація для тестування"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    
class ProductionConfig(Config):
    """Конфігурація для продакшену"""
    DEBUG = False
    # Для production рекомендується використовувати PostgreSQL
    # Формат DATABASE_URL: postgresql://user:password@host:port/database
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
        # Оптимізовані налаштування для PostgreSQL в production
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'pool_size': 20,
            'max_overflow': 40,
            'connect_args': {
                'connect_timeout': 10,
                'application_name': 'inventory_system'
            }
        }
    else:
        # Fallback до SQLite (не рекомендується для production)
        SQLALCHEMY_DATABASE_URI = 'sqlite:///inventory.db'
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
        }
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Налаштування структурованого логування для продакшену
        import logging
        import json
        from logging.handlers import RotatingFileHandler
        from datetime import datetime
        
        if not app.debug:
            # Створюємо handler з ротацією
            file_handler = RotatingFileHandler(
                app.config['LOG_FILE'], 
                maxBytes=app.config.get('LOG_MAX_BYTES', 10 * 1024 * 1024), 
                backupCount=app.config.get('LOG_BACKUP_COUNT', 10)
            )
            
            # Форматер для структурованого логування
            log_format = app.config.get('LOG_FORMAT', 'json')
            
            if log_format == 'json':
                class JSONFormatter(logging.Formatter):
                    def format(self, record):
                        log_data = {
                            'timestamp': datetime.utcnow().isoformat(),
                            'level': record.levelname,
                            'logger': record.name,
                            'message': record.getMessage(),
                            'module': record.module,
                            'function': record.funcName,
                            'line': record.lineno,
                            'pathname': record.pathname
                        }
                        if record.exc_info:
                            log_data['exception'] = self.formatException(record.exc_info)
                        return json.dumps(log_data, ensure_ascii=False)
                
                file_handler.setFormatter(JSONFormatter())
            else:
                # Текстовий формат
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s [%(levelname)s] %(name)s: %(message)s [in %(pathname)s:%(lineno)d]'
                ))
            
            file_handler.setLevel(getattr(logging, app.config.get('LOG_LEVEL', 'INFO')))
            app.logger.addHandler(file_handler)
            app.logger.setLevel(getattr(logging, app.config.get('LOG_LEVEL', 'INFO')))
            app.logger.info('Inventory system startup')

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}