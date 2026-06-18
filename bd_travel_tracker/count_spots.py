import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django

django.setup()
from trips.models import TourSpot, District

print('all spots', TourSpot.objects.count())
print('spot without district', TourSpot.objects.filter(district__isnull=True).count())
print('spot without upa', TourSpot.objects.filter(upazila__isnull=True).count())
for d in District.objects.all()[:5]:
    # districts only have name_bn in our model
    print(d.name_bn, 'spots', TourSpot.objects.filter(district=d).count())
