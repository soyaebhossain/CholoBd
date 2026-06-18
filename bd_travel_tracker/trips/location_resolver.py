import difflib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests

from .models import District, Upazila


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_ADMIN_REFERENCE_PATH = DATA_DIR / "bd_admin_multilang.json"
DEFAULT_POINT_CACHE_PATH = DATA_DIR / "lged_point_admin_cache.json"
OFFICIAL_UPAZILA_QUERY_URL = (
    "https://mapgis.lged.gov.bd/arcgis/rest/services/GSIMS/GsimsBaseMap/MapServer/16/query"
)

DISTRICT_ALIASES = {
    "jashore": "jessore",
    "khagrachhari": "khagrachari",
    "maulvibazar": "moulvibazar",
    "jhalokati": "jhalokathi",
    "netrakona": "netrokona",
    "nawabganj": "chapainawabganj",
    "\u09a8\u0993\u09af\u09bc\u09be\u09ac\u0997\u099e\u09cd\u099c": "\u099a\u09be\u0981\u09aa\u09be\u0987\u09a8\u09ac\u09be\u09ac\u0997\u099e\u09cd\u099c",
}

UPAZILA_ALIASES = {
    "anowara": "anwara",
    "gaurnadi": "gournadi",
    "burhanuddin": "borhanuddin",
    "dhupchanchia": "dupchanchia",
    "brahamanbaria": "brahmanbaria",
    "manoharganj": "monohorgonj",
    "banchharampur": "bancharampur",
    "baghaichhari": "bagaichhari",
    "baghaichari": "bagaichhari",
    "naikhongchhari": "naikhongchari",
    "jhalokatisadar": "jhalokathisadar",
    "barishalsadarkotwali": "barishalsadar",
    "bagerhatsadar": "bagerhatsadar",
    "brahmanbariasadar": "brahmanbariasadar",
    "khagrachharisadar": "khagracharisadar",
    "maulvibazarsadar": "moulvibazarsadar",
    "maulvibazar": "moulvibazar",
    "maulvibazarsadar": "moulvibazarsadar",
    "maulvibazarbarlekha": "moulvibazarbaralekha",
    "kalapara": "kalapara",
    "kalarpara": "kalapara",
    "gangachara": "gangachhara",
    "bishwanath": "biswanath",
    "golabganj": "golapganj",
    "dhanbari": "danbari",
    "hajiganj": "haziganj",
    "saghatta": "saghata",
    "bakshiganj": "baksiganj",
    "kanthalia": "kathalia",
    "jhenaidahasadar": "jhenaidahsadar",
    "serajdikhan": "sirajdikhan",
    "manohardi": "monohardi",
    "nesarabadswarupkati": "nesarabadswarupkathi",
    "baghmara": "bagmara",
    "zanjira": "zajira",
    "bishwambarpur": "bishambarpur",
    "dharampasha": "dharamapasha",
    "jamalganj": "jamalgonj",
    "uttarmatlab": "matlabuttar",
    "mohanganjthana": "mohanganj",
    "noakhalisadarsudharam": "noakhalisadar",
    "nawabganjsadar": "chapainawabganjsadar",
    "\u09a8\u0993\u09af\u09bc\u09be\u09ac\u0997\u099e\u09cd\u099c\u09b8\u09a6\u09b0": "\u099a\u09be\u0981\u09aa\u09be\u0987\u09a8\u09ac\u09be\u09ac\u0997\u099e\u09cd\u099c\u09b8\u09a6\u09b0",
    "goalanda": "goalandaghat",
    "raumari": "rajarhat",  # prevents poor fuzzy fallbacks
}


@dataclass
class OfficialAdminPoint:
    division_en: str
    district_en: str
    upazila_en: str


class SpotAdminResolver:
    def __init__(
        self,
        *,
        reference_path=None,
        cache_path=None,
        service_url=OFFICIAL_UPAZILA_QUERY_URL,
        reference_payload=None,
    ):
        self.reference_path = Path(reference_path or DEFAULT_ADMIN_REFERENCE_PATH)
        self.cache_path = Path(cache_path or DEFAULT_POINT_CACHE_PATH)
        self.service_url = service_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BD-Travel-Tracker/1.0"})
        self._cache_dirty = False

        if reference_payload is None:
            reference_payload = json.loads(self.reference_path.read_text(encoding="utf-8"))
        self.reference_payload = reference_payload
        self.cache = self._load_cache()

        self.division_reference = {}
        self.district_reference = {}
        self.upazila_reference = {}
        self.reference_centroids = []
        self._build_reference_indexes()

    def _load_cache(self):
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save_cache(self):
        if not self._cache_dirty:
            return
        self.cache_path.write_text(
            json.dumps(self.cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache_dirty = False

    @staticmethod
    def normalize_admin_name(text, *, aliases=None):
        normalized_text = unicodedata.normalize("NFKC", str(text or "")).casefold()
        compact = "".join(
            ch
            for ch in normalized_text
            if unicodedata.category(ch)[0] in {"L", "N", "M"}
        )
        if compact.endswith("upazila"):
            compact = compact[: -len("upazila")]
        if compact.endswith("thana"):
            compact = compact[: -len("thana")]
        return (aliases or {}).get(compact, compact)

    @staticmethod
    def cache_key(latitude, longitude):
        return f"{float(latitude):.6f},{float(longitude):.6f}"

    def _build_reference_indexes(self):
        for row in self.reference_payload.get("divisions", []):
            key = self.normalize_admin_name(row["name_en"])
            self.division_reference[key] = row

        for row in self.reference_payload.get("districts", []):
            key = self.normalize_admin_name(row["name_en"], aliases=DISTRICT_ALIASES)
            self.district_reference[key] = row

        for row in self.reference_payload.get("upazilas", []):
            district_key = self.normalize_admin_name(
                row["district_name_en"],
                aliases=DISTRICT_ALIASES,
            )
            upazila_key = self.normalize_admin_name(
                row["name_en"],
                aliases=UPAZILA_ALIASES,
            )
            self.upazila_reference.setdefault(district_key, {})[upazila_key] = row
            if row.get("lat") not in (None, "") and row.get("long") not in (None, ""):
                self.reference_centroids.append(
                    (
                        district_key,
                        float(row["lat"]),
                        float(row["long"]),
                        row,
                    )
                )

    def fetch_official_point(self, latitude, longitude):
        params = {
            "f": "json",
            "geometry": f"{float(longitude):.6f},{float(latitude):.6f}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "DIVISION,DISTRICT,UPAZILA",
            "returnGeometry": "false",
        }
        try:
            response = self.session.get(self.service_url, params=params, timeout=60)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            return None
        features = payload.get("features") or []
        if not features:
            return None

        attributes = features[0].get("attributes") or {}
        return OfficialAdminPoint(
            division_en=(attributes.get("DIVISION") or "").strip(),
            district_en=(attributes.get("DISTRICT") or "").strip(),
            upazila_en=(attributes.get("UPAZILA") or "").strip(),
        )

    def resolve_point(self, latitude, longitude):
        key = self.cache_key(latitude, longitude)
        cached = self.cache.get(key)
        if cached:
            return OfficialAdminPoint(
                division_en=cached["division_en"],
                district_en=cached["district_en"],
                upazila_en=cached["upazila_en"],
            )

        point = self.fetch_official_point(latitude, longitude)
        if point:
            self.cache[key] = {
                "division_en": point.division_en,
                "district_en": point.district_en,
                "upazila_en": point.upazila_en,
            }
            self._cache_dirty = True
        return point

    def prime_cache(self, coordinates, *, workers=8):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        missing = []
        for latitude, longitude in coordinates:
            key = self.cache_key(latitude, longitude)
            if key not in self.cache:
                missing.append((key, float(latitude), float(longitude)))

        if not missing:
            return

        def fetch(item):
            key, latitude, longitude = item
            point = self.fetch_official_point(latitude, longitude)
            if not point:
                return key, None
            return key, {
                "division_en": point.division_en,
                "district_en": point.district_en,
                "upazila_en": point.upazila_en,
            }

        with ThreadPoolExecutor(max_workers=max(1, int(workers or 1))) as executor:
            futures = [executor.submit(fetch, item) for item in missing]
            for future in as_completed(futures):
                key, payload = future.result()
                if payload:
                    self.cache[key] = payload
                    self._cache_dirty = True

    def _best_reference_match(self, target_key, reference_map):
        if target_key in reference_map:
            return reference_map[target_key]

        candidate_keys = list(reference_map.keys())
        if not candidate_keys:
            return None

        matches = difflib.get_close_matches(target_key, candidate_keys, n=1, cutoff=0.74)
        if not matches:
            return None
        return reference_map[matches[0]]

    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2):
        radius = 6371.0
        p = math.pi / 180.0

        d_lat = (lat2 - lat1) * p
        d_lon = (lon2 - lon1) * p

        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(d_lon / 2) ** 2
        )
        return 2 * radius * math.asin(math.sqrt(a))

    def nearest_reference_upazila(self, latitude, longitude, district_en=""):
        district_key = self.normalize_admin_name(district_en, aliases=DISTRICT_ALIASES)
        candidates = [
            item
            for item in self.reference_centroids
            if not district_key or item[0] == district_key
        ]
        if not candidates:
            candidates = self.reference_centroids
        if not candidates:
            return None

        best_row = None
        best_distance = float("inf")
        for _, ref_lat, ref_lon, row in candidates:
            distance = self._haversine_km(float(latitude), float(longitude), ref_lat, ref_lon)
            if distance < best_distance:
                best_distance = distance
                best_row = row
        return best_row

    def resolve_district_record(self, district_en):
        district_key = self.normalize_admin_name(district_en, aliases=DISTRICT_ALIASES)
        reference_row = self._best_reference_match(district_key, self.district_reference)
        existing_by_normalized = {}
        for item in District.objects.select_related("division").order_by("id"):
            normalized_name = self.normalize_admin_name(item.name, aliases=DISTRICT_ALIASES)
            if normalized_name and normalized_name not in existing_by_normalized:
                existing_by_normalized[normalized_name] = item

        if reference_row:
            district_name_bn = reference_row["name_bn"]
            district = District.objects.filter(name=district_name_bn).select_related("division").first()
            if district:
                return district

        candidate_names = [district_en]
        if reference_row:
            candidate_names.append(reference_row["name_en"])
            candidate_names.append(reference_row["name_bn"])

        for candidate in candidate_names:
            district = District.objects.filter(name=candidate).select_related("division").first()
            if district:
                return district
            normalized_candidate = self.normalize_admin_name(
                candidate,
                aliases=DISTRICT_ALIASES,
            )
            district = existing_by_normalized.get(normalized_candidate)
            if district:
                return district

        fallback_district = None
        fallback_score = 0
        fallback_candidates = [district_key]
        if reference_row:
            fallback_candidates.append(
                self.normalize_admin_name(reference_row["name_bn"], aliases=DISTRICT_ALIASES)
            )
        for key, item in existing_by_normalized.items():
            score = max(
                difflib.SequenceMatcher(None, candidate, key).ratio()
                for candidate in fallback_candidates
                if candidate
            )
            if score > fallback_score:
                fallback_score = score
                fallback_district = item

        if fallback_district and fallback_score >= 0.74:
            return fallback_district
        return None

    def resolve_upazila_record(self, district, upazila_en, district_en=""):
        district_key = self.normalize_admin_name(district_en, aliases=DISTRICT_ALIASES)
        reference_candidates = self.upazila_reference.get(district_key, {})
        upazila_key = self.normalize_admin_name(upazila_en, aliases=UPAZILA_ALIASES)
        reference_row = self._best_reference_match(upazila_key, reference_candidates)

        existing_by_normalized = {}
        for row in Upazila.objects.filter(district=district).order_by("id"):
            normalized_name = self.normalize_admin_name(row.name, aliases=UPAZILA_ALIASES)
            if normalized_name and normalized_name not in existing_by_normalized:
                existing_by_normalized[normalized_name] = row

        if reference_row:
            target_bn_name = reference_row["name_bn"]
            target_bn_key = self.normalize_admin_name(
                target_bn_name,
                aliases=UPAZILA_ALIASES,
            )
            existing = existing_by_normalized.get(target_bn_key)
            if existing:
                return existing
            existing = Upazila.objects.filter(district=district, name=target_bn_name).first()
            if existing:
                return existing

        existing = existing_by_normalized.get(upazila_key)
        if existing:
            return existing

        fallback_candidates = [upazila_key]
        if reference_row:
            fallback_candidates.append(
                self.normalize_admin_name(reference_row["name_bn"], aliases=UPAZILA_ALIASES)
            )
        fallback_candidates = [candidate for candidate in fallback_candidates if candidate]
        fuzzy_row = None
        fuzzy_score = 0
        for existing_key, existing_row in existing_by_normalized.items():
            score = max(
                difflib.SequenceMatcher(None, candidate, existing_key).ratio()
                for candidate in fallback_candidates
            )
            if score > fuzzy_score:
                fuzzy_score = score
                fuzzy_row = existing_row
        if fuzzy_row and fuzzy_score >= 0.74:
            return fuzzy_row

        create_name = reference_row["name_bn"] if reference_row else upazila_en
        upazila, _ = Upazila.objects.get_or_create(district=district, name=create_name)
        return upazila

    def resolve_db_location(self, division_en, district_en, upazila_en):
        district = self.resolve_district_record(district_en)
        if not district:
            return None

        division = district.division
        upazila = self.resolve_upazila_record(district, upazila_en, district_en=district_en)
        return division, district, upazila

    def resolve_db_location_for_coordinates(self, latitude, longitude):
        official = self.resolve_point(latitude, longitude)
        if official:
            resolved = self.resolve_db_location(
                official.division_en,
                official.district_en,
                official.upazila_en,
            )
            if resolved:
                return resolved

            fallback_row = self.nearest_reference_upazila(
                latitude,
                longitude,
                district_en=official.district_en,
            )
            if fallback_row:
                resolved = self.resolve_db_location(
                    fallback_row["division_name_en"],
                    fallback_row["district_name_en"],
                    fallback_row["name_en"],
                )
                if resolved:
                    return resolved

        fallback_row = self.nearest_reference_upazila(latitude, longitude)
        if not fallback_row:
            return None
        return self.resolve_db_location(
            fallback_row["division_name_en"],
            fallback_row["district_name_en"],
            fallback_row["name_en"],
        )
