from trips.models import District

for d in District.objects.filter(division__isnull=False)[:10]:
    print(d.name_bn, '->', d.division.name_bn)
