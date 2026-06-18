import argparse
import json
from pathlib import Path


DEFAULT_INPUT = Path("data/tour_spots_by_area.json")
DEFAULT_OUTPUT = Path("data/seed_locations_curated.json")


def build_seed_payload(area_payload):
    divisions = []

    for division_item in area_payload.get("divisions", []):
        districts = []
        for district_item in division_item.get("districts", []):
            upazilas = []
            for area_item in district_item.get("areas", []):
                spots = []
                for spot_item in area_item.get("spots", []):
                    spots.append(
                        {
                            "name": (spot_item.get("name") or "").strip(),
                            "category": (spot_item.get("category") or "").strip(),
                            "description": (spot_item.get("description") or "").strip(),
                            "latitude": None,
                            "longitude": None,
                        }
                    )

                upazilas.append(
                    {
                        "name": (area_item.get("name") or "").strip(),
                        "area_type": (area_item.get("type") or "upazila").strip(),
                        "spots": [spot for spot in spots if spot["name"]],
                    }
                )

            districts.append(
                {
                    "name": (district_item.get("name") or "").strip(),
                    "upazilas": [upazila for upazila in upazilas if upazila["name"]],
                }
            )

        divisions.append(
            {
                "name": (division_item.get("name") or "").strip(),
                "districts": [district for district in districts if district["name"]],
            }
        )

    return {
        "dataset_name": "Seed dataset generated from tour_spots_by_area.json",
        "schema_version": 1,
        "generated_on": area_payload.get("generated_on"),
        "source_file": str(DEFAULT_INPUT).replace("\\", "/"),
        "notes": (
            "Generated for the existing seed_locations importer. "
            "Metropolitan thana entries are flattened into the upazilas list and "
            "retain their original type in the optional area_type field."
        ),
        "divisions": [division for division in divisions if division["name"]],
    }


def count_payload(payload):
    division_count = len(payload.get("divisions", []))
    district_count = 0
    upazila_count = 0
    spot_count = 0

    for division_item in payload.get("divisions", []):
        for district_item in division_item.get("districts", []):
            district_count += 1
            for upazila_item in district_item.get("upazilas", []):
                upazila_count += 1
                spot_count += len(upazila_item.get("spots", []))

    return division_count, district_count, upazila_count, spot_count


def main():
    parser = argparse.ArgumentParser(
        description="Generate a seed_locations-compatible dataset from the area-based spot dataset."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Source area dataset path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output seed dataset path.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    area_payload = json.loads(input_path.read_text(encoding="utf-8"))
    seed_payload = build_seed_payload(area_payload)

    output_path.write_text(
        json.dumps(seed_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    division_count, district_count, upazila_count, spot_count = count_payload(seed_payload)
    print(
        "Generated seed dataset:",
        f"divisions={division_count},",
        f"districts={district_count},",
        f"upazilas={upazila_count},",
        f"spots={spot_count}",
    )
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
