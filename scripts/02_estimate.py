"""Estimate every quantity the paper reports and write them to tabs/."""

import pandas as pd
from geoestimate import Sample

from streetscan.config import TABLE_DIR
from streetscan.designs import (
    as_row,
    class_shares,
    clean_noise,
    cluster_bootstrap_difference,
    meters_to_nearest,
    post_stratified,
    road_class,
    shift_interval,
    with_speed_weight,
)
from streetscan.sources import read_raw

STREETSENSE_OUTCOMES = [
    "pothole",
    "crack",
    "litter",
    "paved_sidewalk",
    "markings_clear",
]
NOISE_THRESHOLDS = {"min_db": 55, "max_db": 100}
SPEED_FLOORS = [0.1, 1.0]
NEAR_M = 100
# Navi Mumbai drew 10,000 points, so almost every frame there is near one.
MIN_GROUP_FRAMES = 20
SEED = 20261112


def streetsense():
    """Point sample: Street View at sampled segments of major roads."""
    segments = read_raw("streetsense_segments.csv")
    rows, coverage = [], []
    for city, sampled in segments.groupby("city", sort=False):
        covered = sampled[sampled["covered"]]
        coverage.append(
            {"city": city, "sampled": len(sampled), "covered": len(covered)}
        )
        if city == "dhaka":
            continue
        shares = class_shares(sampled["osm_type"])
        for outcome in STREETSENSE_OUTCOMES:
            coded = covered.dropna(subset=[outcome])
            labels = {"application": "streetsense", "city": city, "outcome": outcome}
            rows.append(
                as_row(Sample(coded).mean(outcome), **labels, estimator="as coded")
            )
            adjusted, covered_share = post_stratified(coded, "osm_type", shares)
            rows.append(
                as_row(
                    adjusted.mean(outcome),
                    **labels,
                    estimator="road-class adjusted",
                    covered_share=covered_share,
                )
            )
    return rows, pd.DataFrame(coverage)


def streetview_women():
    """Point sample: women's share of pedestrians at sampled Street View locations."""
    locations = read_raw("streetview_locations.csv")
    sampled = read_raw("streetview_sample.csv")
    rows = []
    for city, coded in locations.groupby("city", sort=False):
        labels = {"application": "streetview", "city": city}
        ratio = ("women_count_num", "total_pedestrians")
        shares = class_shares(sampled.loc[sampled["city"] == city, "osm_type"])
        adjusted, covered_share = post_stratified(coded, "osm_type", shares)
        nonempty = coded[coded["total_pedestrians"] > 0]
        rows += [
            as_row(
                Sample(coded).ratio(*ratio),
                **labels,
                outcome="women_share",
                estimator="as coded",
            ),
            as_row(
                adjusted.ratio(*ratio),
                **labels,
                outcome="women_share",
                estimator="road-class adjusted",
                covered_share=covered_share,
            ),
            as_row(
                Sample(nonempty).mean_of_ratios(*ratio),
                **labels,
                outcome="women_share_location_mean",
                estimator="as coded",
            ),
        ]
    return rows


def gopro():
    """Route sample: frames cut from video at fixed time intervals.

    Every estimator uses the frames that have a GPS speed, so that differences
    between them come from the weighting and not from which frames are in.
    """
    frames = read_raw("gopro_images.csv")
    points = read_raw("gopro_sample_points.csv")
    frames["road_class"] = road_class(frames["osm_highway"])
    points["road_class"] = road_class(points["road_class"])
    ratio = ("women_count", "total_pedestrians")
    rows, mix = [], []
    for city, data in frames.groupby("city", sort=False):
        shares = class_shares(points.loc[points["city"] == city, "road_class"])
        moving = with_speed_weight(data)
        by_day = {"cluster": "collection_day"}
        weighted = {"cluster": "collection_day", "weights": "speed_weight"}
        samples = {
            "per minute of riding": (Sample(moving, **by_day), None),
            "per meter of route": (Sample(moving, **weighted), None),
            "road classes only": post_stratified(
                moving, "road_class", shares, **by_day
            ),
            "road network": post_stratified(moving, "road_class", shares, **weighted),
        }
        for floor in SPEED_FLOORS:
            refloored = with_speed_weight(data, floor)
            samples[f"road network, floor {floor}"] = post_stratified(
                refloored, "road_class", shares, **weighted
            )
        for estimator, (sample, share) in samples.items():
            labels = {"application": "gopro", "city": city, "estimator": estimator}
            extra = {} if share is None else {"covered_share": share}
            rows.append(
                as_row(sample.ratio(*ratio), **labels, outcome="women_share", **extra)
            )
            rows.append(
                as_row(
                    sample.mean("total_pedestrians"),
                    **labels,
                    outcome="pedestrians_per_frame",
                    **extra,
                )
            )
        for name, in_class in moving.groupby("road_class"):
            if in_class["collection_day"].nunique() < 2:
                continue
            rows.append(
                as_row(
                    Sample(in_class, **by_day).ratio(*ratio),
                    application="gopro",
                    city=city,
                    estimator=f"class: {name}",
                    outcome="women_share",
                )
            )
        rows.append(
            {
                "application": "gopro",
                "city": city,
                "estimator": "road network minus per minute",
                "outcome": "women_share",
                "n": len(moving),
                "n_clusters": moving["collection_day"].nunique(),
                **shift_interval(
                    moving, "road_class", shares, "collection_day", *ratio, seed=SEED
                ),
            }
        )
        nonempty = moving[moving["total_pedestrians"] > 0]
        rows.append(
            as_row(
                Sample(nonempty, **by_day).mean_of_ratios(*ratio),
                application="gopro",
                city=city,
                estimator="per minute of riding",
                outcome="women_share_location_mean",
            )
        )
        distance = moving.groupby("road_class")["speed_weight"].sum()
        for name in sorted(set(shares) | set(data["road_class"])):
            in_class = moving["road_class"] == name
            mix.append(
                {
                    "city": city,
                    "road_class": name,
                    "sample_share": shares.get(name, 0.0),
                    "frame_share": in_class.mean(),
                    "distance_share": distance.get(name, 0.0) / distance.sum(),
                    "median_kmh": 3.6 * moving.loc[in_class, "speed_mps"].median(),
                    "frames": int(in_class.sum()),
                    "pedestrians": int(moving.loc[in_class, ratio[1]].sum()),
                }
            )
    return rows, pd.DataFrame(mix)


def within_class():
    """Do streets ridden between sampled points resemble the sampled streets?

    Reweighting by road class assumes they do. Frames within NEAR_M of a
    sampled point are on or beside a sampled street; the rest are on the way.
    """
    frames = read_raw("gopro_images.csv").query("gps_valid")
    points = read_raw("gopro_sample_points.csv")
    frames["road_class"] = road_class(frames["osm_highway"])
    frames["people"] = frames["total_pedestrians"]
    frames["one"] = 1
    rows = []
    for city, data in frames.groupby("city", sort=False):
        drawn = points[points["city"] == city]
        data = data.assign(
            near=meters_to_nearest(
                data["gps_lat"], data["gps_lon"], drawn["lat"], drawn["lon"]
            )
            <= NEAR_M
        )
        for name, in_class in data.groupby("road_class"):
            near, far = in_class[in_class["near"]], in_class[~in_class["near"]]
            if name == "other" or min(len(near), len(far)) < MIN_GROUP_FRAMES:
                continue
            for outcome, numerator, denominator in [
                ("women_share", "women_count", "people"),
                ("pedestrians_per_frame", "people", "one"),
            ]:
                rows.append(
                    {
                        "city": city,
                        "road_class": name,
                        "outcome": outcome,
                        "near": near[numerator].sum() / near[denominator].sum(),
                        "far": far[numerator].sum() / far[denominator].sum(),
                        "near_frames": len(near),
                        "far_frames": len(far),
                        **cluster_bootstrap_difference(
                            in_class,
                            "near",
                            "collection_day",
                            numerator,
                            denominator,
                            SEED,
                        ),
                    }
                )
    return pd.DataFrame(rows)


def streetview_by_class():
    """Women's share by road class at sampled Street View locations."""
    locations = read_raw("streetview_locations.csv")
    locations["road_class"] = road_class(locations["osm_type"])
    rows = []
    for (city, name), coded in locations.groupby(["city", "road_class"]):
        if len(coded) < 2 or coded["total_pedestrians"].sum() == 0:
            continue
        rows.append(
            as_row(
                Sample(coded).ratio("women_count_num", "total_pedestrians"),
                application="streetview",
                city=city,
                estimator=f"class: {name}",
                outcome="women_share",
            )
        )
    return rows


def delhi_sensor_rows(readings, shares, application, outcomes, thresholds):
    # A day shares a rider, weather and part of the city across its itineraries.
    by_route = {"cluster": "day"}
    network, covered_share = (
        post_stratified(readings, "road_class", shares, **by_route)
        if shares is not None
        else (None, None)
    )
    samples = {"as read": (Sample(readings, **by_route), None)}
    if network is not None:
        samples["road network"] = (network, covered_share)
    rows = []
    for estimator, (sample, share) in samples.items():
        labels = {"application": application, "city": "delhi", "estimator": estimator}
        extra = {} if share is None else {"covered_share": share}
        for outcome in outcomes:
            rows.append(
                as_row(sample.mean(outcome), **labels, outcome=outcome, **extra)
            )
        for outcome, threshold in thresholds.items():
            rows.append(
                as_row(
                    sample.share_at_least(outcome, threshold),
                    **labels,
                    outcome=f"{outcome}_at_least_{threshold}",
                    **extra,
                )
            )
    return rows


def noise():
    """Route sample: sound-meter readings at stops along Delhi itineraries."""
    readings = clean_noise(read_raw("noise_readings.csv"))
    points = read_raw("gopro_sample_points.csv").query("city == 'delhi'")
    shares = class_shares(road_class(points["road_class"]))
    planned = readings[~readings["is_traffic_stop"]]
    traffic = readings[readings["is_traffic_stop"]]
    outcomes = ["min_db", "max_db"]
    rows = delhi_sensor_rows(planned, shares, "noise", outcomes, NOISE_THRESHOLDS)
    rows += delhi_sensor_rows(
        traffic, None, "noise at traffic stops", outcomes, NOISE_THRESHOLDS
    )
    return rows


def air():
    """Route sample: PM2.5 and CO2 readings on the same Delhi itineraries."""
    readings = read_raw("air_readings.csv")
    rows = delhi_sensor_rows(readings, None, "air", ["pm25"], {})
    rows += delhi_sensor_rows(
        readings[readings["co2_qc_pass"]], None, "air", ["co2"], {}
    )
    return rows


streetsense_rows, coverage = streetsense()
gopro_rows, road_mix = gopro()
estimates = pd.DataFrame(
    streetsense_rows
    + streetview_women()
    + streetview_by_class()
    + gopro_rows
    + noise()
    + air()
)
# Ten significant digits, so the file is identical across platforms.
estimates.to_csv(TABLE_DIR / "estimates.csv", index=False, float_format="%.10g")
coverage.to_csv(TABLE_DIR / "streetsense_coverage.csv", index=False)
road_mix.to_csv(TABLE_DIR / "gopro_road_mix.csv", index=False, float_format="%.10g")
within_class().to_csv(TABLE_DIR / "within_class.csv", index=False, float_format="%.10g")
