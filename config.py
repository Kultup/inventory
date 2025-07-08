import os
from datetime import timedelta

class Config:
    """Базова конфігурація"""
    
    # Основні налаштування Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Налаштування бази даних
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///inventory.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
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
    

    
    # Налаштування безпеки
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    # Налаштування локалізації
    LANGUAGES = ['uk', 'en']
    DEFAULT_LANGUAGE = 'uk'
    
    # Налаштування QR кодів
    QR_CODE_SIZE = int(os.environ.get('QR_CODE_SIZE', 200))
    QR_CODE_BORDER = int(os.environ.get('QR_CODE_BORDER', 4))
    
    @staticmethod
    def init_app(app):
        """Ініціалізація додатку з конфігурацією"""
        # Створення необхідних директорій
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


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
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///inventory.db'
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Налаштування логування для продакшену
        import logging
        from logging.handlers import RotatingFileHandler
        
        if not app.debug:
            file_handler = RotatingFileHandler(
                app.config['LOG_FILE'], 
                maxBytes=10240000, 
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info('Inventory system startup')

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}