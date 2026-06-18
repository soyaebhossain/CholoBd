import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django

django.setup()
from trips.models import TourSpot
print('total spots:', TourSpot.objects.count())
print('spots with district:', TourSpot.objects.filter(district__isnull=False).count())
print('spots without district:', TourSpot.objects.filter(district__isnull=True).count())
print('spots with upazila:', TourSpot.objects.filter(upazila__isnull=False).count())
print('spots without upazila:', TourSpot.objects.filter(upazila__isnull=True).count())
print('\nExamples missing district:')
for s in TourSpot.objects.filter(district__isnull=True)[:15]:
    print('-', s.name)
print('\nExamples missing upazila:')
for s in TourSpot.objects.filter(upazila__isnull=True)[:15]:
    print('-', s.name)
