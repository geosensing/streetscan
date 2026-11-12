"""Write the paper's tables and every number its text cites."""

import numpy as np
import pandas as pd

from streetscan.config import TABLE_DIR
from streetscan.designs import MIN_SPEED_MPS, clean_noise, road_class
from streetscan.paper import count, write_macros, write_table
from streetscan.sources import read_raw
from streetscan.style import CITY_LABELS, CITY_ORDER

SOURCE = "scripts/05_tables.py"
estimates = pd.read_csv(TABLE_DIR / "estimates.csv")
estimates["city_key"] = estimates["city"].str.lower().str.replace(" ", "_")
road_mix = pd.read_csv(TABLE_DIR / "gopro_road_mix.csv")
simulation = pd.read_csv(TABLE_DIR / "simulation.csv")
coverage = pd.read_csv(TABLE_DIR / "streetsense_coverage.csv").set_index("city")
frames = read_raw("gopro_images.csv")
points = read_raw("gopro_sample_points.csv")
noise = clean_noise(read_raw("noise_readings.csv"))
funnel = read_raw("streetview_funnel.csv").set_index("city")


def pick(application, city, outcome, estimator):
    match = estimates[
        (estimates["application"] == application)
        & (estimates["city_key"] == city)
        & (estimates["outcome"] == outcome)
        & (estimates["estimator"] == estimator)
    ]
    if len(match) != 1:
        raise ValueError(f"{len(match)} rows for {application} {city} {outcome}")
    return match.iloc[0]


def percent(x, digits=1):
    return f"{100 * x:.{digits}f}"


def with_interval(row, scale=100, digits=1):
    if row["standard_error"] == 0:
        # Every unit gave the same answer, so the sample carries no interval.
        return f"{scale * row['estimate']:.{digits}f}"
    values = [scale * row[name] for name in ("estimate", "conf_low", "conf_high")]
    point, low, high = (f"{value:.{digits}f}" for value in values)
    return f"{point} [{low}, {high}]"


def signed(x, digits=1):
    """A signed number for a LaTeX table, with a true minus sign."""
    text = f"{abs(x):.{digits}f}"
    if float(text) == 0:
        return text
    return f"${'-' if x < 0 else '+'}${text}"


def macro_key(city):
    return CITY_LABELS[city].replace(" ", "")


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def nearest_point_m(readings, sampled):
    distances = haversine_m(
        readings["latitude"].to_numpy()[:, None],
        readings["longitude"].to_numpy()[:, None],
        sampled["lat"].to_numpy()[None, :],
        sampled["lon"].to_numpy()[None, :],
    )
    return distances.min(axis=1)


macros = {}

# Women's share of pedestrians: video under three weightings, and Street View.
VIDEO = ["per minute of riding", "per metre of route", "road network"]
women_rows = []
location_gaps, floor_gaps = [], []
for city in CITY_ORDER:
    cells = [CITY_LABELS[city]]
    for estimator in VIDEO:
        row = pick("gopro", city, "women_share", estimator)
        cells.append(with_interval(row))
        macros[f"video {macro_key(city)} {estimator}"] = percent(row["estimate"])
    if city == "bangalore":
        cells.append("--")
    else:
        row = pick("streetview", city, "women_share", "road-class adjusted")
        cells.append(with_interval(row))
        macros[f"streetview {macro_key(city)}"] = percent(row["estimate"])
        raw = pick("streetview", city, "women_share", "as coded")
        macros[f"streetview raw {macro_key(city)}"] = percent(raw["estimate"])
    women_rows.append(cells)
    city_frames = frames[frames["city"] == city]
    key = macro_key(city)
    macros[f"frames {key}"] = count(len(city_frames))
    macros[f"days {key}"] = str(city_frames["collection_day"].nunique())
    macros[f"nearest {key}"] = count(
        int(round(city_frames["itinerary_distance_m"].median()))
    )
    mix = road_mix[road_mix["city"] == city].set_index("road_class")
    for name in ("residential", "major"):
        macros[f"sample {name} {key}"] = percent(mix.loc[name, "sample_share"], 0)
        macros[f"frame {name} {key}"] = percent(mix.loc[name, "frame_share"], 0)
        macros[f"kmh {name} {key}"] = f"{mix.loc[name, 'median_kmh']:.0f}"
    stopped = (city_frames["speed_mps"] < MIN_SPEED_MPS).sum()
    macros[f"stopped {key}"] = percent(
        stopped / city_frames["speed_mps"].notna().sum(), 0
    )
    location_mean = pick(
        "gopro", city, "women_share_location_mean", "per minute of riding"
    )
    macros[f"video location mean {key}"] = percent(location_mean["estimate"])
    per_minute = pick("gopro", city, "women_share", "per minute of riding")
    location_gaps.append(abs(location_mean["estimate"] - per_minute["estimate"]))
    macros[f"speed frames {key}"] = count(int(per_minute["n"]))
    macros[f"speed days {key}"] = str(int(per_minute["n_clusters"]))
    shift = pick("gopro", city, "women_share", "road network minus per minute")
    macros[f"shift {key}"] = percent(shift["estimate"])
    macros[f"shift low {key}"] = percent(shift["conf_low"])
    macros[f"shift high {key}"] = percent(shift["conf_high"])
    classes_only = pick("gopro", city, "women_share", "road classes only")
    macros[f"classes only {key}"] = percent(classes_only["estimate"])
    for name in ("residential", "major"):
        in_class = pick("gopro", city, "women_share", f"class: {name}")
        macros[f"class {name} {key}"] = percent(in_class["estimate"])
        macros[f"class frames {name} {key}"] = count(int(mix.loc[name, "frames"]))
    macros[f"points {key}"] = count(int((points["city"] == city).sum()))
    macros[f"pedestrians counted {key}"] = count(
        int(city_frames["total_pedestrians"].sum())
    )
    macros[f"topcoded men {key}"] = percent(city_frames["men_count_topcoded"].mean())
    when = pd.to_datetime(city_frames["frame_datetime_ist"])
    gaps = when.groupby(city_frames["video"]).apply(
        lambda times: times.sort_values().diff().dt.total_seconds()
    )
    macros[f"frame gap {key}"] = f"{gaps.median():.0f}"
    floors = [
        pick("gopro", city, "women_share", f"road network, floor {floor}")["estimate"]
        for floor in (0.1, 1.0)
    ]
    network = pick("gopro", city, "women_share", "road network")["estimate"]
    floor_gaps.append(max(abs(value - network) for value in floors))
write_table(
    women_rows,
    TABLE_DIR / "women.tex",
    "lcccc",
    [
        "",
        "Per minute of riding",
        "Per metre of route",
        "Road network",
        "Street View",
    ],
)
for estimator in VIDEO:
    row = pick("gopro", "delhi", "pedestrians_per_frame", estimator)
    macros[f"pedestrians Delhi {estimator}"] = f"{row['estimate']:.2f}"
macros["frames total"] = count(len(frames))
macros["location gap max"] = percent(max(location_gaps))
macros["floor gap max"] = percent(max(floor_gaps))
# Video names end in itinerary.leg, which says which itineraries were ridden.
for city in ("delhi", "bangalore"):
    names = frames.loc[frames["city"] == city, "video"]
    ridden = names.str.extract(r"(\d+)\.\d+$")[0].nunique()
    planned = points.loc[points["city"] == city, "itinerary_id"].nunique()
    macros[f"ridden {macro_key(city)}"] = str(ridden)
    macros[f"planned {macro_key(city)}"] = str(planned)

video_ratio = estimates[
    (estimates["application"] == "gopro")
    & (estimates["outcome"] == "women_share")
    & estimates["estimator"].isin(VIDEO)
]
se_ratio = video_ratio["standard_error"] / video_ratio["naive_standard_error"]
macros["video se ratio min"] = f"{se_ratio.min():.1f}"
macros["video se ratio max"] = f"{se_ratio.max():.1f}"

for city, row in funnel.iterrows():
    key = city.replace(" ", "")
    macros[f"streetview sampled {key}"] = count(int(row["selected_locations"]))
    macros[f"streetview covered {key}"] = percent(row["coverage_rate"], 0)
    macros[f"streetview coded {key}"] = count(int(row["annotated_locations"]))
    macros[f"streetview drawn {key}"] = count(int(row["initial_sample_locations"]))

# Road condition from Street View at sampled segments.
OUTCOMES = {
    "pothole": "Potholes",
    "crack": "Cracks",
    "litter": "Litter",
    "paved_sidewalk": "Paved sidewalk",
    "markings_clear": "Clear markings",
}
condition_rows = []
for city in ["bangkok", "jakarta", "lagos", "wayne"]:
    cells = [
        CITY_LABELS[city].replace(", MI", ""),
        count(int(coverage.loc[city, "sampled"])),
        percent(coverage.loc[city, "covered"] / coverage.loc[city, "sampled"], 0),
    ]
    for outcome in OUTCOMES:
        row = pick("streetsense", city, outcome, "road-class adjusted")
        cells.append(percent(row["estimate"], 0))
        raw = pick("streetsense", city, outcome, "as coded")
        macros[f"condition {city} {outcome}"] = percent(row["estimate"], 0)
        macros[f"condition se {city} {outcome}"] = percent(row["standard_error"])
        gap = abs(row["estimate"] - raw["estimate"])
        macros["condition max adjustment"] = percent(
            max(gap, float(macros.get("condition max adjustment", 0)) / 100)
        )
    condition_rows.append(cells)
write_table(
    condition_rows,
    TABLE_DIR / "condition.tex",
    "lrrrrrrr",
    ["", "Sampled", "Covered (\\%)", *OUTCOMES.values()],
)
macros["dhaka covered"] = percent(
    coverage.loc["dhaka", "covered"] / coverage.loc["dhaka", "sampled"]
)
macros["lagos covered"] = percent(
    coverage.loc["lagos", "covered"] / coverage.loc["lagos", "sampled"], 0
)

# Noise in Delhi.
NOISE_ROWS = {
    "min_db": ("Mean minimum (dB)", 1, 1),
    "max_db": ("Mean maximum (dB)", 1, 1),
    "min_db_at_least_55": ("Minimum at or above 55 dB (\\%)", 100, 1),
    "max_db_at_least_100": ("Maximum at or above 100 dB (\\%)", 100, 1),
}
noise_rows = []
for outcome, (label, scale, digits) in NOISE_ROWS.items():
    cells = [label]
    for application, estimator in [
        ("noise", "as read"),
        ("noise", "road network"),
        ("noise at traffic stops", "as read"),
    ]:
        row = pick(application, "delhi", outcome, estimator)
        cells.append(with_interval(row, scale, digits))
        name = f"{application} {estimator} {outcome}".replace("_db", "")
        macros[name] = f"{scale * row['estimate']:.{digits}f}"
    noise_rows.append(cells)
write_table(
    noise_rows,
    TABLE_DIR / "noise.tex",
    "lccc",
    ["", "As read", "Road network", "Traffic stops"],
)
planned = noise[~noise["is_traffic_stop"]]
delhi_points = points[points["city"] == "delhi"]
distance = nearest_point_m(planned, delhi_points)
macros["noise readings"] = count(len(noise))
macros["noise planned"] = count(len(planned))
macros["noise traffic"] = count(int(noise["is_traffic_stop"].sum()))
macros["noise itineraries"] = str(noise["itinerary_id"].nunique())
macros["delhi itineraries"] = str(delhi_points["itinerary_id"].nunique())
macros["noise days"] = str(noise["day"].nunique())
macros["noise nearest"] = count(int(round(np.median(distance))))
macros["noise within hundred"] = percent((distance <= 100).mean(), 0)
macros["noise residential"] = percent(
    (planned["road_class"] == "residential").mean(), 0
)
macros["delhi sample residential"] = percent(
    (road_class(delhi_points["road_class"]) == "residential").mean(), 0
)
noise_main = estimates[estimates["application"] == "noise"]
noise_se_ratio = noise_main["standard_error"] / noise_main["naive_standard_error"]
macros["noise se ratio min"] = f"{noise_se_ratio.min():.1f}"
macros["noise se ratio max"] = f"{noise_se_ratio.max():.1f}"

# Air in Delhi.
pm25 = pick("air", "delhi", "pm25", "as read")
macros["air readings"] = str(int(pm25["n"]))
macros["air days"] = str(int(pm25["n_clusters"]))
macros["air pm"] = f"{pm25['estimate']:.0f}"
macros["air pm low"] = f"{pm25['conf_low']:.0f}"
macros["air pm high"] = f"{pm25['conf_high']:.0f}"

# Simulation.
SIMULATED = {
    "point sample": "Point sample",
    "route, per minute": "Route sample, per minute",
    "route, per metre": "Route sample, per metre",
    "route, road classes only": "Route sample, road classes only",
    "route, road network": "Route sample, road network",
}
simulation_rows = []
for design, label in SIMULATED.items():
    row = simulation[simulation["design"] == design].iloc[0]
    simulation_rows.append(
        [
            label,
            percent(row["mean_estimate"]),
            signed(100 * row["bias"]),
            percent(row["sd_estimate"]),
            percent(row["mean_standard_error"]),
            percent(row["coverage"], 0),
        ]
    )
    macros[f"sim coverage {design}"] = percent(row["coverage"], 0)
    macros[f"sim bias {design}"] = f"{abs(100 * row['bias']):.1f}"
macros["sim truth"] = percent(simulation["truth"].iloc[0])
write_table(
    simulation_rows,
    TABLE_DIR / "simulation.tex",
    "lrrrrr",
    [
        "",
        "Mean (\\%)",
        "Bias (pp)",
        "SD (pp)",
        "SE (pp)",
        "Coverage (\\%)",
    ],
)

write_macros(macros, TABLE_DIR / "macros.tex", SOURCE)
