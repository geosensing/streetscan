"""Check the estimators against a city where the truth is known.

The city is invented. Road classes differ in women's share, in crowding, and
in speed; within a class, crowded segments are slower. A point sample observes
drawn segments. A route sample rides mostly big roads and cuts a frame every
fixed interval, so it sees slow, crowded stretches of big roads too often.
The question is which estimator recovers the city's share and whether its
interval covers the truth as often as it claims.
"""

import numpy as np
import pandas as pd
from geoestimate import Sample

from streetscan.config import TABLE_DIR
from streetscan.designs import MIN_SPEED_MPS

SEED = 20261112
REPLICATIONS = 1000
N_SEGMENTS = 20000
SEGMENT_M = 500
FRAME_INTERVAL_SEC = 60
N_DAYS = 12
SEGMENTS_PER_DAY = 150
POINT_SAMPLE_SIZE = 600
# The applications learn the city's road-class mix from a drawn sample of
# this size, not from the frame itself.
SHARE_SAMPLE_SIZE = 1000

CLASSES = pd.DataFrame(
    {
        "road_class": ["residential", "tertiary", "major"],
        "frame_share": [0.80, 0.12, 0.08],
        "route_share": [0.25, 0.25, 0.50],
        "women_share": [0.26, 0.20, 0.14],
        "pedestrians": [1.6, 1.4, 0.9],
        "speed_mps": [2.5, 5.0, 7.5],
    }
).set_index("road_class")


def build_city(rng):
    road_class = rng.choice(CLASSES.index, size=N_SEGMENTS, p=CLASSES["frame_share"])
    base = CLASSES.loc[road_class]
    crowding = rng.lognormal(sigma=0.6, size=N_SEGMENTS)
    crowding /= np.exp(0.6**2 / 2)
    # Crowded segments are slower, so a time-based camera sees them more.
    speed = base["speed_mps"].to_numpy() * crowding**-0.5
    speed *= rng.lognormal(sigma=0.2, size=N_SEGMENTS)
    return pd.DataFrame(
        {
            "road_class": road_class,
            "pedestrians": base["pedestrians"].to_numpy() * crowding,
            "women_share": base["women_share"].to_numpy(),
            "speed_mps": speed,
        }
    )


def observe(segments, rng, day_shift=0.0):
    """One camera frame per row: counts of pedestrians and of women."""
    pedestrians = rng.poisson(segments["pedestrians"])
    logit = np.log(segments["women_share"] / (1 - segments["women_share"]))
    share = 1 / (1 + np.exp(-(logit + day_shift)))
    women = rng.binomial(pedestrians, share)
    return segments.assign(pedestrians=pedestrians, women=women)


def point_sample(city, rng):
    drawn = city.sample(POINT_SAMPLE_SIZE, random_state=rng)
    return Sample(observe(drawn, rng)).ratio("women", "pedestrians")


def route_sample(city, rng):
    by_class = {name: rows for name, rows in city.groupby("road_class")}
    days = []
    for day in range(N_DAYS):
        classes = rng.choice(
            CLASSES.index, size=SEGMENTS_PER_DAY, p=CLASSES["route_share"]
        )
        ridden = pd.concat(
            by_class[name].sample((classes == name).sum(), random_state=rng)
            for name in CLASSES.index
        )
        seconds = SEGMENT_M / ridden["speed_mps"]
        n_frames = rng.poisson(seconds / FRAME_INTERVAL_SEC)
        frames = ridden.loc[ridden.index.repeat(n_frames)]
        day_shift = rng.normal(scale=0.15)
        days.append(observe(frames, rng, day_shift).assign(day=day))
    frames = pd.concat(days, ignore_index=True)
    frames["speed_weight"] = frames["speed_mps"].clip(lower=MIN_SPEED_MPS)
    ratio = ("women", "pedestrians")
    drawn = city["road_class"].sample(SHARE_SAMPLE_SIZE, random_state=rng)
    shares = drawn.value_counts(normalize=True).to_dict()
    unweighted = Sample(frames, cluster="day")
    weighted = Sample(frames, cluster="day", weights="speed_weight")
    return {
        "route, per minute": unweighted.ratio(*ratio),
        "route, per meter": weighted.ratio(*ratio),
        "route, road classes only": unweighted.post_stratify(
            "road_class", shares
        ).ratio(*ratio),
        "route, road network": weighted.post_stratify("road_class", shares).ratio(
            *ratio
        ),
    }


rng = np.random.default_rng(SEED)
city = build_city(rng)
truth = (city["pedestrians"] * city["women_share"]).sum() / city["pedestrians"].sum()

draws = []
for replication in range(REPLICATIONS):
    estimates = {"point sample": point_sample(city, rng), **route_sample(city, rng)}
    for design, estimate in estimates.items():
        low, high = estimate.confidence_interval
        draws.append(
            {
                "design": design,
                "estimate": estimate.estimate,
                "standard_error": estimate.standard_error,
                "covers": low <= truth <= high,
            }
        )

draws = pd.DataFrame(draws)
summary = draws.groupby("design", sort=False).agg(
    mean_estimate=("estimate", "mean"),
    sd_estimate=("estimate", "std"),
    mean_standard_error=("standard_error", "mean"),
    coverage=("covers", "mean"),
)
summary.insert(0, "truth", truth)
summary["bias"] = summary["mean_estimate"] - truth
summary.to_csv(TABLE_DIR / "simulation.csv", float_format="%.10g")
