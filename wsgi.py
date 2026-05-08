"""
CINEMAWAY — Point d'entrée WSGI pour la production
Compatible avec : Gunicorn, uWSGI, Heroku, Railway, Render

Usage :
  gunicorn wsgi:application --workers 4 --bind 0.0.0.0:5000
  gunicorn wsgi:application --workers 4 --bind 0.0.0.0:$PORT --timeout 120
"""

import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env
load_dotenv()

from app import app as application

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    application.run(host='0.0.0.0', port=port, debug=debug)
