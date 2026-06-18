from trips.models import TourSpot

print(TourSpot.objects.filter(district__isnull=False).count(), 'with district')
print(TourSpot.objects.filter(district__isnull=True).count(), 'without district')
for spot in TourSpot.objects.filter(district__isnull=True)[:10]:
    print('no dist', spot.name)
