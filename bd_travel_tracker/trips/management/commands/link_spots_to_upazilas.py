from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Deprecated command. Spot-upazila mapping is now handled inside seed_locations data."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(self.help))
