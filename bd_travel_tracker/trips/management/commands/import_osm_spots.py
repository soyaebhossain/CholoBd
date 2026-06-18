import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from trips.location_resolver import SpotAdminResolver
from trips.models import TourSpot


class Command(BaseCommand):
    help = "Import bulk tourism spots from OSM JSON and map them to official district/upazila."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="data/osm_spots_bulk_raw.json",
            help="Path to OSM raw JSON file (elements with tags and coordinates).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional max number of source elements to process (0 = all).",
        )
        parser.add_argument(
            "--mapping",
            type=str,
            default="data/bd_admin_multilang.json",
            help="Path to multilingual district/upazila reference JSON.",
        )
        parser.add_argument(
            "--cache",
            type=str,
            default="data/lged_point_admin_cache.json",
            help="Path to local official point lookup cache JSON.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=8,
            help="Concurrent workers for official point lookup cache priming.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show stats only; do not write database changes.",
        )

    def handle(self, *args, **options):
        source_path = Path(options["path"])

        if not source_path.exists():
            raise CommandError(f"OSM source file not found: {source_path}")

        payload = json.loads(source_path.read_text(encoding="utf-8"))
        elements = payload.get("elements", [])
        if options["limit"] and options["limit"] > 0:
            elements = elements[: options["limit"]]

        resolver = SpotAdminResolver(
            reference_path=options["mapping"],
            cache_path=options["cache"],
        )

        existing = {
            (spot.upazila_id, self._normalize_name(spot.name)): spot
            for spot in TourSpot.objects.only("id", "name", "upazila_id", "category", "description", "latitude", "longitude")
        }

        stats = {
            "processed": 0,
            "skipped_missing_name": 0,
            "skipped_missing_coord": 0,
            "skipped_unresolved_admin": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
        }

        to_create = []
        to_update = []

        coordinates = []
        for element in elements:
            latitude, longitude = self._pick_coordinates(element)
            if latitude is not None and longitude is not None:
                coordinates.append((latitude, longitude))
        resolver.prime_cache(coordinates, workers=options["workers"])

        for element in elements:
            stats["processed"] += 1
            tags = element.get("tags") or {}

            name = self._pick_name(tags)
            if not name:
                stats["skipped_missing_name"] += 1
                continue

            latitude, longitude = self._pick_coordinates(element)
            if latitude is None or longitude is None:
                stats["skipped_missing_coord"] += 1
                continue

            db_location = resolver.resolve_db_location_for_coordinates(latitude, longitude)
            if not db_location:
                stats["skipped_unresolved_admin"] += 1
                continue

            _, _, upazila = db_location
            upazila_id = upazila.id

            key = (upazila_id, self._normalize_name(name))
            category = self._pick_category(tags)
            description = self._build_description(tags)

            if key in existing:
                spot = existing[key]
                changed = False

                if category and (spot.category or "") != category:
                    spot.category = category
                    changed = True
                if description and not spot.description:
                    spot.description = description
                    changed = True
                if spot.latitude is None and latitude is not None:
                    spot.latitude = latitude
                    changed = True
                if spot.longitude is None and longitude is not None:
                    spot.longitude = longitude
                    changed = True

                if changed:
                    to_update.append(spot)
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
                continue

            new_spot = TourSpot(
                upazila_id=upazila_id,
                name=name,
                category=category,
                description=description,
                latitude=latitude,
                longitude=longitude,
            )
            to_create.append(new_spot)
            existing[key] = new_spot
            stats["created"] += 1

        self.stdout.write(
            f"Processed={stats['processed']}, Created={stats['created']}, "
            f"Updated={stats['updated']}, Unchanged={stats['unchanged']}, "
            f"Skip(no-name)={stats['skipped_missing_name']}, "
            f"Skip(no-coord)={stats['skipped_missing_coord']}, "
            f"Skip(unresolved-admin)={stats['skipped_unresolved_admin']}"
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run enabled. No DB writes performed."))
            return

        with transaction.atomic():
            if to_create:
                TourSpot.objects.bulk_create(to_create, batch_size=500)
            if to_update:
                TourSpot.objects.bulk_update(
                    to_update,
                    fields=["category", "description", "latitude", "longitude"],
                    batch_size=500,
                )
            resolver.save_cache()

        self.stdout.write(self.style.SUCCESS("OSM spot import completed."))

    def _pick_name(self, tags):
        candidates = [tags.get("name:bn"), tags.get("name:en"), tags.get("name")]
        for candidate in candidates:
            clean = self._clean_name(candidate)
            if clean:
                return clean
        return ""

    def _pick_coordinates(self, element):
        lat = element.get("lat")
        lon = element.get("lon")

        if lat is None or lon is None:
            center = element.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            return None, None

        return float(lat), float(lon)

    def _pick_category(self, tags):
        for key in ("tourism", "historic", "natural", "leisure"):
            value = (tags.get(key) or "").strip()
            if value:
                return value[:80]
        return ""

    def _build_description(self, tags):
        source_parts = []
        for key in ("tourism", "historic", "natural", "leisure"):
            value = tags.get(key)
            if value:
                source_parts.append(f"{key}={value}")

        if not source_parts:
            return ""

        text = "Imported from OpenStreetMap (" + ", ".join(source_parts) + ")."
        return text[:1000]

    def _clean_name(self, value):
        if not value:
            return ""

        text = self._normalize_text(str(value))
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < 2:
            return ""

        if text.isdigit():
            return ""

        return text[:180]

    def _normalize_text(self, text):
        return " ".join(str(text).split()).strip()

    def _normalize_name(self, text):
        return self._normalize_text(text).casefold()
