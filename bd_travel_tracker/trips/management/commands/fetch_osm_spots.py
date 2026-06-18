import json
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError


OVERPASS_QUERY = '''
[out:json][timeout:420];
area["ISO3166-1"="BD"][admin_level=2]->.bd;
(
  nwr(area.bd)[name][tourism];
  nwr(area.bd)[name][historic~"archaeological_site|castle|fort|monument|memorial|ruins"];
  nwr(area.bd)[name][natural~"beach|waterfall|peak|cave|island|hot_spring|cliff|bay|cape|spring"];
  nwr(area.bd)[name][leisure~"park|nature_reserve|garden|water_park"];
);
out center tags;
'''


class Command(BaseCommand):
    help = "Fetch bulk Bangladesh tourism-like spots from Overpass OSM and save as JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="data/osm_spots_bulk_raw.json",
            help="Output path for OSM raw JSON.",
        )
        parser.add_argument(
            "--endpoint",
            type=str,
            default="https://overpass.kumi.systems/api/interpreter",
            help="Overpass endpoint URL.",
        )

    def handle(self, *args, **options):
        endpoint = options["endpoint"]
        output_path = Path(options["path"])

        self.stdout.write(f"Requesting OSM data from: {endpoint}")
        try:
            response = requests.post(
                endpoint,
                data={"data": OVERPASS_QUERY},
                timeout=540,
                headers={"User-Agent": "BD-Travel-Tracker/1.0"},
            )
        except Exception as exc:
            raise CommandError(f"Overpass request failed: {exc}")

        if response.status_code != 200:
            raise CommandError(
                f"Overpass request failed with status={response.status_code}: {response.text[:500]}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise CommandError(f"Invalid JSON response from Overpass: {exc}")

        elements = payload.get("elements", [])
        output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Saved {len(elements)} OSM elements to {output_path}"
            )
        )
