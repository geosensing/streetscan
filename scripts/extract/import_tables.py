"""Copy per-unit tables from the application repositories into data/raw.

One-off: run from a checkout that has the sibling repositories beside this one.
The pipeline never runs this; it starts from the committed files in data/raw.

    uv run python scripts/extract/import_tables.py

Columns that identify people (annotator emails), that point at images (paths and
storage URLs), or that repeat coordinates as a street address are left behind.
"""

import json

import pandas as pd

from streetscan.config import PROJECT_ROOT, RAW_DIR

SIBLINGS = PROJECT_ROOT.parent
STREETSCOPE = SIBLINGS / "streetscope"
STREETSIGHT = SIBLINGS / "streetsight"
SOUNDSCAPE = SIBLINGS / "soundscape"
STREETAQI = SIBLINGS / "streetaqi"

GOPRO_CITIES = ["mumbai", "navi_mumbai", "bangalore", "delhi"]
GOPRO_COLUMNS = [
    "task_id",
    "collection_day",
    "frame_datetime_ist",
    "frame_hour",
    "is_weekend",
    "gps_lat",
    "gps_lon",
    "gps_valid",
    "osm_highway",
    "itinerary_road_type",
    "itinerary_distance_m",
    "women_count",
    "women_count_topcoded",
    "men_count",
    "men_count_topcoded",
    "women_twowheeler",
    "men_twowheeler",
    "total_pedestrians",
    "footpath",
    "lane_markings",
    "potholes",
    "litter",
    "street_vendor",
]

# Each city's drawn sample was saved in whatever shape its sampler produced.
SAMPLE_FILES = {
    "mumbai": "mumbai/itineraries/itineraries-mumbai-city.csv",
    "navi_mumbai": "navi_mumbai/itineraries/itineraries.csv",
    "bangalore": "bangalore/itineraries/itineraries.csv",
    "delhi": "delhi_nn/itineraries/itineraries.csv",
}


def gopro_images():
    frames = []
    for city in GOPRO_CITIES:
        data = pd.read_parquet(STREETSCOPE / "data" / city / "analysis_data.parquet")
        frame = data[GOPRO_COLUMNS].copy()
        frame.insert(0, "image", data["image"].str.rsplit("/", n=1).str[-1])
        frame.insert(0, "city", city)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def gopro_sample_points():
    frames = []
    for city, relative in SAMPLE_FILES.items():
        data = pd.read_csv(STREETSCOPE / "sampling" / relative)
        if "start_lat" in data:
            # geo-sampling output: one row per sampled segment.
            points = pd.DataFrame(
                {
                    "point_id": range(len(data)),
                    "itinerary_id": data["itinerary_id"],
                    "lat": data["start_lat"],
                    "lon": data["start_long"],
                    "road_class": data["type"],
                    "osm_id": data["osm_id"],
                    "segment_length_m": data["LENGTH_M"],
                }
            )
        else:
            points = data.rename(columns={"highway": "road_class"})[
                ["point_id", "itinerary_id", "lat", "lon", "road_class"]
            ]
        points.insert(0, "city", city)
        frames.append(points)
    return pd.concat(frames, ignore_index=True)


def noise_readings():
    with open(SOUNDSCAPE / "output" / "rider" / "readings.json") as handle:
        flat = pd.json_normalize(json.load(handle)["readings"])
    logs = pd.read_csv(
        SOUNDSCAPE / "data" / "rider" / "export-2026-05-24" / "noise_logs.csv"
    )
    flags = flat[
        [
            "id",
            "metadata.stop_id",
            "metadata.is_traffic_stop",
            "metadata.is_traffic_jam",
            "metadata.road_type",
        ]
    ].rename(columns=lambda name: name.removeprefix("metadata."))
    columns = [
        "id",
        "day",
        "itinerary_id",
        "part",
        "captured_at",
        "min_db",
        "max_db",
        "latitude",
        "longitude",
        "note",
    ]
    return logs[columns].merge(flags, on="id", validate="one_to_one")


def air_readings():
    data = pd.read_parquet(
        STREETAQI / "src" / "streetaqi" / "data" / "delhi_readings.parquet"
    )
    columns = [
        "id",
        "day",
        "itinerary_id",
        "part",
        "captured_at",
        "pm25",
        "co2",
        "co2_qc_pass",
        "latitude",
        "longitude",
        "note",
    ]
    return data[columns]


def streetview_tables():
    outputs = STREETSIGHT / "notebooks" / "outputs" / "v2"
    views = pd.read_csv(outputs / "analysis_views.csv")
    views = views.drop(columns=["annotator_email", "image_path"])
    return {
        "streetview_views.csv": views,
        "streetview_locations.csv": pd.read_csv(outputs / "analysis_locations.csv"),
        "streetview_funnel.csv": pd.read_csv(outputs / "sampling_funnel.csv"),
        "streetview_selection.csv": pd.read_csv(outputs / "selection_diagnostics.csv"),
        "streetview_sample.csv": pd.read_csv(
            STREETSIGHT / "data" / "samples" / "all_cities.csv"
        ),
    }


def main():
    tables = {
        "gopro_images.csv": gopro_images(),
        "gopro_sample_points.csv": gopro_sample_points(),
        "noise_readings.csv": noise_readings(),
        "air_readings.csv": air_readings(),
        **streetview_tables(),
    }
    for name, table in tables.items():
        table.to_csv(RAW_DIR / name, index=False)
        print(f"{name}: {len(table):,} rows, {table.shape[1]} columns")


if __name__ == "__main__":
    main()
