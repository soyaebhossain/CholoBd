from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Deprecated command. Use `python manage.py seed_locations --path data/seed_locations_full.json`."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(self.help))
