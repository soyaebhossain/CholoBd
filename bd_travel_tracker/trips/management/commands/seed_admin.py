from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Deprecated. Use `python manage.py seed_locations --path data/seed_locations_full.json`."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="data/seed_locations_full.json",
            help="Path to JSON/CSV seed file.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("seed_admin is deprecated; running seed_locations."))
        call_command("seed_locations", path=options["path"])
