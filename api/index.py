import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent / "bd_travel_tracker"
sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()
application = app
