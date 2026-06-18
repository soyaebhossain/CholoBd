import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django

django.setup()
from trips.models import Trip
for t in Trip.objects.all():
    print(t.id, t.district, t.upazila, t.spot)
