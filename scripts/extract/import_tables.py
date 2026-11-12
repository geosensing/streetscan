"""Copy per-unit tables from the application repositories into data/raw.

One-off: run from a checkout that has the sibling repositories beside this one.
The pipeline never runs this; it starts from the committed files in data/raw.

    uv run python scripts/extract/import_tables.py

Columns that identify people (annotator emails), that point at images (paths and
storage URLs), or that repeat coordinates as a street address are left behind.
"""

import json

import numpy as np
import pandas as pd

from streetscan.config import PROJECT_ROOT, RAW_DIR

SIBLINGS = PROJECT_ROOT.parent
STREETSCOPE = SIBLINGS / "streetscope"
STREETSIGHT = SIBLINGS / "streetsight"
SOUNDSCAPE = SIBLINGS / "soundscape"
STREETAQI = SIBLINGS / "streetaqi"
STREETSENSE = SIBLINGS / "streetsense"

# city: (sample file, coded file); Dhaka was sampled but never coded.
STREETSENSE_FILES = {
    "bangkok": ("bangkok-roads-s1k.csv", "bangkok_mturk_2018_06_02.csv"),
    "jakarta": ("jakarta-roads-s1k.csv", "jakarta_2_mturk_14_06_18.csv"),
    "lagos": ("lagos-roads-s1k.csv", "lagos_mturk_2018_06_08.csv"),
    "wayne": ("wayne2-roads-s5k.csv", "wayne_mturk_2018_06_11_18.csv"),
    "dhaka": ("dhaka-roads-s1k.csv", None),
}

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
    "bangalore": "bangalore/itineraries/itineraries.csv",
    "delhi": "delhi_nn/itineraries/itineraries.csv",
}


SPEED_HALF_WINDOW_SEC = 10
EARTH_RADIUS_M = 6371000
MAX_PLAUSIBLE_SPEED_MPS = 40


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * np.arcsin(np.sqrt(a))


def track_position(track, times, offset_sec):
    """Track fix nearest to each frame time plus an offset, within two seconds."""
    wanted = pd.DataFrame(
        {"row": np.arange(len(times)), "when": times + pd.Timedelta(seconds=offset_sec)}
    ).dropna()
    found = pd.merge_asof(
        wanted.sort_values("when"),
        track,
        left_on="when",
        right_on="gps_datetime",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=2),
    )
    return found.set_index("row").reindex(range(len(times)))


def frame_speed(city, data):
    """Rider speed at each frame, from the camera's GPS track around the frame.

    Frames are cut at fixed time intervals, so a stretch of road is photographed
    in proportion to the time spent on it. Speed is what converts between a
    per-minute and a per-metre sample.
    """
    track = pd.read_parquet(
        STREETSCOPE / "data" / city / "gps_index" / "gps_timeseries.parquet",
        columns=["video_id", "gps_datetime", "lat", "lon"],
    ).sort_values("gps_datetime")
    track["gps_datetime"] = track["gps_datetime"].astype("datetime64[us]")
    times = pd.to_datetime(data["frame_datetime"]).astype("datetime64[us]")
    times = times.reset_index(drop=True)
    before = track_position(track, times, -SPEED_HALF_WINDOW_SEC)
    at = track_position(track, times, 0)
    after = track_position(track, times, SPEED_HALF_WINDOW_SEC)
    # Near the start or end of a video only one side of the window exists.
    start = before.where(before["video_id"] == at["video_id"], at)
    end = after.where(after["video_id"] == at["video_id"], at)
    seconds = (end["gps_datetime"] - start["gps_datetime"]).dt.total_seconds()
    metres = haversine_m(start["lat"], start["lon"], end["lat"], end["lon"])
    speed = (metres / seconds).where(seconds >= SPEED_HALF_WINDOW_SEC)
    # A motorbike in city traffic does not exceed 144 km/h; faster is a GPS jump.
    speed = speed.where(speed <= MAX_PLAUSIBLE_SPEED_MPS)
    return speed.round(2).to_numpy()


def gopro_images():
    frames = []
    for city in GOPRO_CITIES:
        data = pd.read_parquet(STREETSCOPE / "data" / city / "analysis_data.parquet")
        frame = data[GOPRO_COLUMNS].copy()
        frame["speed_mps"] = frame_speed(city, data)
        frame.insert(0, "video", data["base_video_id"])
        frame.insert(1, "frame_number", data["frame_number"])
        frame.insert(0, "image", data["image"].str.rsplit("/", n=1).str[-1])
        frame.insert(0, "city", city)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def gopro_sample_points():
    frames = []
    for city, relative in SAMPLE_FILES.items():
        data = pd.read_csv(STREETSCOPE / "sampling" / relative)
        if "start_lat" in data:
            # geo-sampling output: one row per sampled segment. Its start_lat
            # column holds longitude and start_long latitude.
            points = pd.DataFrame(
                {
                    "point_id": range(len(data)),
                    "itinerary_id": data["itinerary_id"],
                    "lat": data["start_long"],
                    "lon": data["start_lat"],
                    "road_class": data["type"],
                }
            )
        else:
            points = data.rename(columns={"highway": "road_class"})[
                ["point_id", "itinerary_id", "lat", "lon", "road_class"]
            ]
        points.insert(0, "city", city)
        frames.append(points)
    frames.append(navi_mumbai_sample_points())
    return pd.concat(frames, ignore_index=True)


def navi_mumbai_sample_points():
    """Navi Mumbai drew 10,000 points and routed 8,126 of them.

    navi_mumbai/itineraries/itineraries.csv is not this sample: it is a Delhi
    draw saved in the wrong folder.
    """
    folder = STREETSCOPE / "sampling" / "navi_mumbai"
    with open(folder / "sampled_points" / "sampled_points.geojson") as handle:
        features = json.load(handle)["features"]
    points = pd.DataFrame(
        {
            "point_id": [f["properties"]["point_id"] for f in features],
            "lat": [f["geometry"]["coordinates"][1] for f in features],
            "lon": [f["geometry"]["coordinates"][0] for f in features],
            "road_class": [f["properties"]["highway_type"] for f in features],
        }
    )
    # A way tagged with two classes is stored as a list; keep the first.
    points["road_class"] = points["road_class"].map(
        lambda value: value[0] if isinstance(value, list) else value
    )
    routed = pd.read_csv(folder / "itineraries" / "detailed_itineraries.csv")
    routed = routed.rename(columns={"route_id": "itinerary_id"})
    points = points.merge(
        routed[["point_id", "itinerary_id"]], on="point_id", how="left", validate="1:1"
    )
    points["itinerary_id"] = points["itinerary_id"].astype("Int64")
    points.insert(0, "city", "navi_mumbai")
    return points[["city", "point_id", "itinerary_id", "lat", "lon", "road_class"]]


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


def streetsense_segments():
    """One row per sampled segment, with codes where Street View had an image."""
    frames = []
    for city, (sample_file, coded_file) in STREETSENSE_FILES.items():
        sample = pd.read_csv(STREETSENSE / "data" / "geo_sample_out" / sample_file)
        sample = sample[["segment_id", "osm_type", "start_lat", "start_long"]]
        sample.insert(0, "city", city)
        if coded_file is None:
            covered = pd.read_csv(
                STREETSENSE / "data" / "google_street_view_metadata" / f"{city}.csv"
            )
            sample["covered"] = sample["segment_id"].isin(covered["segment_id"])
            frames.append(sample)
            continue
        coded = pd.read_csv(STREETSENSE / "data" / "mturk" / coded_file)
        seen = coded["Answer.Do you see any of the following?"].fillna("")
        road = coded["Answer.Does the road have any...?"].fillna("")
        markings = coded["Answer.If there are any road markings are they clear?"]
        codes = pd.DataFrame(
            {
                "segment_id": coded["Input.segment_id"],
                "capture_date": coded["Input.date"],
                "pothole": road.str.contains("Potholes").astype(int),
                "crack": road.str.contains("Cracks").astype(int),
                "litter": seen.str.contains("Litter").astype(int),
                "paved_sidewalk": seen.str.contains("paved sidewalk").astype(int),
                "markings_clear": markings.map({"Yes": 1, "No": 0}),
            }
        )
        merged = sample.merge(codes, on="segment_id", how="left", validate="1:1")
        merged["covered"] = merged["pothole"].notna()
        frames.append(merged)
    return pd.concat(frames, ignore_index=True)


# city: folder of frames saved from its videos, as listed when the images were
# moved to external storage. Bangalore and Delhi frames were all annotated.
SAVED_FRAME_MANIFESTS = {
    "mumbai": "streetscope__data__annotation_task__annotation_frames.json",
    "navi_mumbai": "streetscope__data__annotation_task__annotation_frames_new.json",
}


def gopro_extracted_frames(images):
    """Per video, how many frames were saved and how many of those were annotated."""
    frames = []
    for city, manifest in SAVED_FRAME_MANIFESTS.items():
        with open(SIBLINGS / "storage-migration-2026-11-10" / manifest) as handle:
            files = [entry["path"] for entry in json.load(handle)["files"]]
        saved = pd.Series([name for name in files if name.endswith(".jpg")])
        annotated = set(images.loc[images["city"] == city, "image"])
        table = pd.DataFrame(
            {
                "video": saved.str.replace(r"_frame\d+\.jpg$", "", regex=True),
                "index": saved.str.extract(r"_frame(\d+)\.jpg$")[0].astype(int),
                "annotated": saved.isin(annotated),
            }
        )
        # Whether a frame falls in the first half of its video's saved frames,
        # to check that annotation did not favour the start or end of a ride.
        table["early"] = table.groupby("video")["index"].rank(pct=True) <= 0.5
        counts = table.groupby("video").agg(
            saved=("annotated", "size"),
            annotated=("annotated", "sum"),
            saved_early=("early", "sum"),
            annotated_early=(
                "annotated",
                lambda a: (a & table.loc[a.index, "early"]).sum(),
            ),
        )
        counts.insert(0, "city", city)
        frames.append(counts.reset_index())
    return pd.concat(frames, ignore_index=True)


def main():
    tables = {
        "gopro_images.csv": gopro_images(),
        "gopro_sample_points.csv": gopro_sample_points(),
        "noise_readings.csv": noise_readings(),
        "air_readings.csv": air_readings(),
        "streetsense_segments.csv": streetsense_segments(),
        **streetview_tables(),
    }
    tables["gopro_extracted_frames.csv"] = gopro_extracted_frames(
        tables["gopro_images.csv"]
    )
    for name, table in tables.items():
        table.to_csv(RAW_DIR / name, index=False)
        print(f"{name}: {len(table):,} rows, {table.shape[1]} columns")


if __name__ == "__main__":
    main()
