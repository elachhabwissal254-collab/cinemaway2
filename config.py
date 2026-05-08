"""
CINEMAWAY — Configuration par environnement
Usage dans app.py :
    from config import get_config
    app.config.from_object(get_config())
"""

import os


class BaseConfig:
    """Configuration de base partagée par tous les environnements."""
    SECRET_KEY            = os.environ.get('SECRET_KEY', 'change-this-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH    = 50 * 1024 * 1024   # 50 MB upload max
    JSON_SORT_KEYS        = False
    PERMANENT_SESSION_LIFETIME = 86400 * 30     # 30 jours

    # SMTP
    SMTP_HOST  = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT  = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USER  = os.environ.get('SMTP_USER', 'cinemaway26@gmail.com')
    SMTP_PASS  = os.environ.get('SMTP_PASS', '')
    FROM_EMAIL = os.environ.get('FROM_EMAIL', 'cinemaway26@gmail.com')

    # Cinemaway info
    AGENCY_NAME    = 'CINEMAWAY'
    AGENCY_EMAIL   = 'cinemaway26@gmail.com'
    AGENCY_PHONE   = '+212 654 045 836'
    AGENCY_ADDRESS = 'Appt 15 Imm 12 Lot SINE ALLAL EL FASSI, Marrakech'
    AGENCY_ICE     = '003766068000003'


class DevelopmentConfig(BaseConfig):
    """Configuration de développement."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///cinemaway_dev.db'
    )
    # Logs SQL en dev
    SQLALCHEMY_ECHO = False


class TestingConfig(BaseConfig):
    """Configuration de tests."""
    TESTING = True
    DEBUG   = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(BaseConfig):
    """Configuration de production."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///cinemaway_prod.db'
    )
    # En production, forcer HTTPS
    SESSION_COOKIE_SECURE   = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


_configs = {
    'development': DevelopmentConfig,
    'testing':     TestingConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}


def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return _configs.get(env, DevelopmentConfig)
