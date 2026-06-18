import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from trips.models import District, Division, TourSpot, Trip, Upazila


class Command(BaseCommand):
    help = "Seed Division, District, Upazila, and TourSpot from JSON/CSV data files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="data/seed_locations_full.json",
            help="Path to seed data file (.json or .csv)",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing trips and location hierarchy before seeding.",
        )
        parser.add_argument(
            "--with-osm",
            action="store_true",
            help="After seeding admin data, import bulk OSM tourism spots.",
        )
        parser.add_argument(
            "--osm-path",
            type=str,
            default="data/osm_spots_bulk_raw.json",
            help="Path to OSM raw JSON file for --with-osm import.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]) if options["path"] else Path("data/seed_locations_full.json")

        if not path.exists():
            raise CommandError(f"Seed file not found: {path}")

        if options.get("reset"):
            self._reset_existing_data()

        suffix = path.suffix.lower()
        if suffix == ".json":
            summary = self._seed_from_json(path)
        elif suffix == ".csv":
            summary = self._seed_from_csv(path)
        else:
            raise CommandError("Only .json and .csv files are supported.")

        self.stdout.write(
            self.style.SUCCESS(
                "Seed completed: "
                f"{summary['divisions']} divisions, "
                f"{summary['districts']} districts, "
                f"{summary['upazilas']} upazilas, "
                f"{summary['spots']} tour spots."
            )
        )

        if options.get("with_osm"):
            self.stdout.write("Running OSM bulk spot import...")
            call_command("import_osm_spots", path=options["osm_path"])

    @transaction.atomic
    def _reset_existing_data(self):
        self.stdout.write("Resetting existing travel/location data...")
        Trip.objects.all().delete()
        TourSpot.objects.all().delete()
        Upazila.objects.all().delete()
        District.objects.all().delete()
        Division.objects.all().delete()
        self.stdout.write(self.style.WARNING("Existing data cleared."))

    def _seed_from_json(self, path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        divisions_payload = payload.get("divisions", [])

        summary = {"divisions": 0, "districts": 0, "upazilas": 0, "spots": 0}

        for division_item in divisions_payload:
            division_name = (division_item.get("name") or "").strip()
            if not division_name:
                continue

            division, division_created = Division.objects.get_or_create(name=division_name)
            summary["divisions"] += int(division_created)

            for district_item in division_item.get("districts", []):
                district_name = (district_item.get("name") or "").strip()
                if not district_name:
                    continue

                district, district_created = District.objects.get_or_create(
                    division=division,
                    name=district_name,
                )
                summary["districts"] += int(district_created)

                for upazila_item in district_item.get("upazilas", []):
                    upazila_name = (upazila_item.get("name") or "").strip()
                    if not upazila_name:
                        continue

                    upazila, upazila_created = Upazila.objects.get_or_create(
                        district=district,
                        name=upazila_name,
                    )
                    summary["upazilas"] += int(upazila_created)

                    for spot_item in upazila_item.get("spots", []):
                        spot_name = (spot_item.get("name") or "").strip()
                        if not spot_name:
                            continue

                        defaults = {
                            "category": (spot_item.get("category") or "").strip(),
                            "description": (spot_item.get("description") or "").strip(),
                            "latitude": self._decimal_or_none(spot_item.get("latitude")),
                            "longitude": self._decimal_or_none(spot_item.get("longitude")),
                        }

                        _, spot_created = TourSpot.objects.update_or_create(
                            upazila=upazila,
                            name=spot_name,
                            defaults=defaults,
                        )
                        summary["spots"] += int(spot_created)

        return summary

    def _seed_from_csv(self, path):
        summary = {"divisions": 0, "districts": 0, "upazilas": 0, "spots": 0}

        with path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            required_columns = {
                "division",
                "district",
                "upazila",
                "spot",
                "category",
                "description",
                "latitude",
                "longitude",
            }
            if not required_columns.issubset(reader.fieldnames or []):
                raise CommandError(
                    "CSV must include columns: " + ", ".join(sorted(required_columns))
                )

            for row in reader:
                division_name = (row.get("division") or "").strip()
                district_name = (row.get("district") or "").strip()
                upazila_name = (row.get("upazila") or "").strip()
                spot_name = (row.get("spot") or "").strip()

                if not all([division_name, district_name, upazila_name, spot_name]):
                    continue

                division, division_created = Division.objects.get_or_create(name=division_name)
                summary["divisions"] += int(division_created)

                district, district_created = District.objects.get_or_create(
                    division=division,
                    name=district_name,
                )
                summary["districts"] += int(district_created)

                upazila, upazila_created = Upazila.objects.get_or_create(
                    district=district,
                    name=upazila_name,
                )
                summary["upazilas"] += int(upazila_created)

                defaults = {
                    "category": (row.get("category") or "").strip(),
                    "description": (row.get("description") or "").strip(),
                    "latitude": self._decimal_or_none(row.get("latitude")),
                    "longitude": self._decimal_or_none(row.get("longitude")),
                }

                _, spot_created = TourSpot.objects.update_or_create(
                    upazila=upazila,
                    name=spot_name,
                    defaults=defaults,
                )
                summary["spots"] += int(spot_created)

        return summary

    def _decimal_or_none(self, value):
        if value in (None, ""):
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
