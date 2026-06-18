import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from trips.location_resolver import SpotAdminResolver, UPAZILA_ALIASES
from trips.models import Album, CommunityPost, SavedSpot, Story, TourSpot, Trip, TripReminder, Upazila


class Command(BaseCommand):
    help = (
        "Repair TourSpot district/upazila assignment using official LGED boundary lookup, "
        "then sync related trip/community references."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional limit for number of spots to process (0 = all mapped spots).",
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
            help="Analyze and report changes without writing DB updates.",
        )
        parser.add_argument(
            "--cache",
            type=str,
            default="data/lged_point_admin_cache.json",
            help="Path to local official point lookup cache JSON.",
        )
        parser.add_argument(
            "--mapping",
            type=str,
            default="data/bd_admin_multilang.json",
            help="Path to multilingual district/upazila reference JSON.",
        )
        parser.add_argument(
            "--seed-path",
            type=str,
            default="data/seed_locations_full.json",
            help="Path to curated seed spot JSON used for repairing spots without coordinates.",
        )

    def handle(self, *args, **options):
        resolver = SpotAdminResolver(
            reference_path=options["mapping"],
            cache_path=options["cache"],
        )
        seed_spot_index = self._load_seed_spot_index(options["seed_path"])

        spots_qs = (
            TourSpot.objects.exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .select_related("upazila__district__division")
            .order_by("id")
        )
        if options["limit"]:
            spots_qs = spots_qs[: options["limit"]]

        spots = list(spots_qs)
        legacy_spots = list(
            TourSpot.objects.filter(latitude__isnull=True, longitude__isnull=True)
            .select_related("upazila__district__division")
            .order_by("id")
        )
        resolver.prime_cache(
            [(spot.latitude, spot.longitude) for spot in spots],
            workers=options["workers"],
        )

        stats = {
            "processed": len(spots),
            "unchanged": 0,
            "moved": 0,
            "merged": 0,
            "unresolved": 0,
            "created_upazilas": 0,
            "trip_sync_updates": 0,
            "community_sync_updates": 0,
            "saved_conflicts_resolved": 0,
            "duplicate_spot_reassignments": 0,
            "duplicate_trip_reassignments": 0,
            "duplicate_upazilas_deleted": 0,
            "legacy_processed": len(legacy_spots),
            "legacy_moved": 0,
            "legacy_unchanged": 0,
            "legacy_unresolved": 0,
        }
        samples = []
        existing_upazila_ids = set(TourSpot.objects.values_list("upazila_id", flat=True).distinct())

        with transaction.atomic():
            for spot in spots:
                resolved = resolver.resolve_db_location_for_coordinates(
                    spot.latitude,
                    spot.longitude,
                )
                if not resolved:
                    stats["unresolved"] += 1
                    continue

                _, _, target_upazila = resolved
                if target_upazila.id not in existing_upazila_ids:
                    stats["created_upazilas"] += 1
                    existing_upazila_ids.add(target_upazila.id)

                if spot.upazila_id == target_upazila.id:
                    stats["unchanged"] += 1
                    continue

                if len(samples) < 20:
                    samples.append(
                        (
                            spot.name,
                            spot.upazila.name,
                            target_upazila.name,
                            target_upazila.district.name,
                        )
                    )

                if options["dry_run"]:
                    stats["moved"] += 1
                    continue

                existing = (
                    TourSpot.objects.filter(upazila=target_upazila, name=spot.name)
                    .exclude(id=spot.id)
                    .first()
                )
                if existing:
                    self._merge_spots(source=spot, target=existing, stats=stats)
                    stats["merged"] += 1
                    continue

                spot.upazila = target_upazila
                spot.save(update_fields=["upazila"])
                stats["moved"] += 1
                self._sync_related_rows(spot, stats)

            for spot in legacy_spots:
                target_upazila = self._resolve_seed_target_upazila(spot, seed_spot_index)
                if not target_upazila:
                    stats["legacy_unresolved"] += 1
                    continue

                if spot.upazila_id == target_upazila.id:
                    stats["legacy_unchanged"] += 1
                    continue

                if len(samples) < 20:
                    samples.append(
                        (
                            spot.name,
                            spot.upazila.name,
                            target_upazila.name,
                            target_upazila.district.name,
                        )
                    )

                if options["dry_run"]:
                    stats["legacy_moved"] += 1
                    continue

                existing = (
                    TourSpot.objects.filter(upazila=target_upazila, name=spot.name)
                    .exclude(id=spot.id)
                    .first()
                )
                if existing:
                    self._merge_spots(source=spot, target=existing, stats=stats)
                    stats["merged"] += 1
                    continue

                spot.upazila = target_upazila
                spot.save(update_fields=["upazila"])
                stats["legacy_moved"] += 1
                self._sync_related_rows(spot, stats)

            if options["dry_run"]:
                transaction.set_rollback(True)
            else:
                self._cleanup_duplicate_upazilas(resolver, stats)
                resolver.save_cache()

        self.stdout.write(
            self.style.SUCCESS(
                "Processed={processed}, Moved={moved}, Merged={merged}, "
                "Unchanged={unchanged}, Unresolved={unresolved}, "
                "LegacyProcessed={legacy_processed}, LegacyMoved={legacy_moved}, "
                "LegacyUnchanged={legacy_unchanged}, LegacyUnresolved={legacy_unresolved}, "
                "CreatedUpazilas={created_upazilas}, TripSync={trip_sync_updates}, "
                "CommunitySync={community_sync_updates}, SavedConflicts={saved_conflicts_resolved}, "
                "DuplicateSpotReassign={duplicate_spot_reassignments}, "
                "DuplicateTripReassign={duplicate_trip_reassignments}, "
                "DuplicateUpazilasDeleted={duplicate_upazilas_deleted}".format(
                    **stats
                )
            )
        )
        if samples:
            self.stdout.write("Sample reassignments:")
            for name, source_name, target_name, district_name in samples:
                sample_text = (
                    f" - {name}: {source_name} -> {target_name} ({district_name})"
                )
                self.stdout.write(sample_text.encode("ascii", "backslashreplace").decode("ascii"))

    def _merge_spots(self, *, source, target, stats):
        update_fields = []
        if source.category and not target.category:
            target.category = source.category
            update_fields.append("category")
        if source.description and len(source.description) > len(target.description or ""):
            target.description = source.description
            update_fields.append("description")
        if target.latitude is None and source.latitude is not None:
            target.latitude = source.latitude
            update_fields.append("latitude")
        if target.longitude is None and source.longitude is not None:
            target.longitude = source.longitude
            update_fields.append("longitude")
        if update_fields:
            target.save(update_fields=sorted(set(update_fields)))

        Trip.objects.filter(spot=source).update(
            spot=target,
            division_id=target.division.id,
            district_id=target.district.id,
            upazila_id=target.upazila_id,
        )
        Album.objects.filter(spot=source).update(spot=target)
        Story.objects.filter(spot=source).update(spot=target)
        TripReminder.objects.filter(spot=source).update(spot=target)
        CommunityPost.objects.filter(spot=source).update(
            spot=target,
            district_id=target.district.id,
        )

        for saved in SavedSpot.objects.filter(spot=source):
            if SavedSpot.objects.filter(user=saved.user, spot=target).exists():
                saved.delete()
                stats["saved_conflicts_resolved"] += 1
                continue
            saved.spot = target
            saved.save(update_fields=["spot"])

        source.delete()
        self._sync_related_rows(target, stats)

    def _sync_related_rows(self, spot, stats):
        trip_updates = Trip.objects.filter(spot=spot).update(
            division_id=spot.division.id,
            district_id=spot.district.id,
            upazila_id=spot.upazila_id,
        )
        community_updates = CommunityPost.objects.filter(spot=spot).update(
            district_id=spot.district.id,
        )
        stats["trip_sync_updates"] += trip_updates
        stats["community_sync_updates"] += community_updates

    def _cleanup_duplicate_upazilas(self, resolver, stats):
        for district_id in Upazila.objects.order_by().values_list("district_id", flat=True).distinct():
            grouped = defaultdict(list)
            for upazila in Upazila.objects.filter(district_id=district_id).order_by("id"):
                normalized_name = resolver.normalize_admin_name(
                    upazila.name,
                    aliases=UPAZILA_ALIASES,
                )
                if not normalized_name:
                    continue
                grouped[normalized_name].append(upazila)

            for rows in grouped.values():
                if len(rows) < 2:
                    continue

                canonical = rows[0]
                for duplicate in rows[1:]:
                    moved_spots = TourSpot.objects.filter(upazila=duplicate).update(upazila=canonical)
                    moved_trips = Trip.objects.filter(upazila=duplicate).update(upazila=canonical)
                    stats["duplicate_spot_reassignments"] += moved_spots
                    stats["duplicate_trip_reassignments"] += moved_trips

                    has_spots = TourSpot.objects.filter(upazila=duplicate).exists()
                    has_trips = Trip.objects.filter(upazila=duplicate).exists()
                    if not has_spots and not has_trips:
                        duplicate.delete()
                    stats["duplicate_upazilas_deleted"] += 1

    def _load_seed_spot_index(self, seed_path):
        path = Path(seed_path)
        if not path.exists():
            return {}

        payload = json.loads(path.read_text(encoding="utf-8"))
        index = defaultdict(list)
        for division_item in payload.get("divisions", []):
            division_name = (division_item.get("name") or "").strip()
            for district_item in division_item.get("districts", []):
                district_name = (district_item.get("name") or "").strip()
                for upazila_item in district_item.get("upazilas", []):
                    upazila_name = (upazila_item.get("name") or "").strip()
                    for spot_item in upazila_item.get("spots", []):
                        spot_name = (spot_item.get("name") or "").strip()
                        if not spot_name:
                            continue
                        index[spot_name].append(
                            {
                                "division": division_name,
                                "district": district_name,
                                "upazila": upazila_name,
                            }
                        )
        return dict(index)

    def _resolve_seed_target_upazila(self, spot, seed_spot_index):
        candidates = seed_spot_index.get(spot.name) or []
        if not candidates:
            return None

        selected = None
        if len(candidates) == 1:
            selected = candidates[0]
        else:
            selected = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate["district"] == spot.district.name
                ),
                None,
            )
            if not selected:
                selected = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate["division"] == spot.division.name
                    ),
                    None,
                )

        if not selected:
            return None

        return Upazila.objects.filter(
            district__division__name=selected["division"],
            district__name=selected["district"],
            name=selected["upazila"],
        ).first()
