"""What each application's sample is, and how its estimates are computed.

Two designs appear in the paper.

Point samples: the unit observed is the unit drawn. A Street View image is
requested at a sampled segment's start, so the draw's inclusion probabilities
are the observation's. What goes wrong is coverage: some sampled units have no
image, or were not coded.

Route samples: the drawn points only fix a route. A camera cut every few
seconds, or a meter read at stops along the way, observes the roads ridden. Two
things then separate the observations from the road network. A frame every t
seconds photographs a stretch in proportion to the time spent on it, so slow
stretches are over-represented; weighting a frame by speed undoes that. And
routes between points run on bigger roads than the points sit on;
post-stratifying to the drawn sample's road-class mix undoes that, as far as
road class captures it.
"""

import numpy as np
import pandas as pd
from geoestimate import Sample

ROAD_CLASSES = {
    "residential": "residential",
    "living_street": "residential",
    "tertiary": "tertiary",
    "tertiary_link": "tertiary",
    "secondary": "major",
    "secondary_link": "major",
    "primary": "major",
    "primary_link": "major",
    "trunk": "major",
    "trunk_link": "major",
    "motorway": "major",
    "motorway_link": "major",
}

# A frame's weight is its speed, so a stationary frame would get none. It still
# shows a place on the route; half a metre per second is walking pace in a jam.
MIN_SPEED_MPS = 0.5


def road_class(osm_type):
    """Collapse OpenStreetMap highway types into classes with enough data each."""
    return osm_type.map(ROAD_CLASSES).fillna("other")


def class_shares(sample_classes):
    """Road-class mix of a drawn sample, which estimates the frame's mix."""
    return sample_classes.value_counts(normalize=True).to_dict()


def post_stratified(data, by, shares, **design):
    """Post-stratify to target shares over the cells the data can speak for.

    Rows in a cell the frame does not contain are off-frame and dropped. A frame
    cell with no rows cannot be represented, so the remaining shares are
    rescaled to sum to one; ``covered_share`` reports how much of the frame they
    are.
    """
    present = set(data[by]) & {cell for cell, share in shares.items() if share > 0}
    covered_share = sum(shares[cell] for cell in present)
    kept = data[data[by].isin(present)]
    targets = {cell: shares[cell] / covered_share for cell in present}
    return Sample(kept, **design).post_stratify(by, targets), covered_share


def as_row(estimate, **labels):
    low, high = estimate.confidence_interval
    return {
        **labels,
        "estimate": estimate.estimate,
        "standard_error": estimate.standard_error,
        "conf_low": low,
        "conf_high": high,
        "n": estimate.n_observations,
        "n_clusters": estimate.n_clusters,
        "naive_standard_error": estimate.diagnostics.iid_standard_error,
    }


def clean_noise(noise):
    """One row per reading, with the lower value as the minimum.

    One reading was entered twice with minimum and maximum reversed, and two
    rows the rider marked "Duplicate" carry no values.
    """
    noise = (
        noise.dropna(subset=["min_db", "max_db"])
        .drop_duplicates(
            ["day", "itinerary_id", "latitude", "longitude", "min_db", "max_db"]
        )
        .copy()
    )
    low = np.minimum(noise["min_db"], noise["max_db"])
    high = np.maximum(noise["min_db"], noise["max_db"])
    noise["min_db"], noise["max_db"] = low, high
    noise["road_class"] = road_class(noise["road_type"])
    return noise


def with_speed_weight(frames, min_speed=MIN_SPEED_MPS):
    """Frames with a usable GPS speed, weighted to represent distance."""
    frames = frames.dropna(subset=["speed_mps"]).copy()
    frames["speed_weight"] = frames["speed_mps"].clip(lower=min_speed)
    return frames


def weighted_ratio(data, numerator, denominator, weight):
    return (weight * data[numerator]).sum() / (weight * data[denominator]).sum()


def network_weight(data, by, shares, weight):
    """Post-stratified weights as plain numbers, for resampling."""
    cell_weight = weight.groupby(data[by]).sum()
    covered = sum(shares.get(cell, 0.0) for cell in cell_weight.index)
    target = data[by].map(lambda cell: shares.get(cell, 0.0) / covered)
    return weight * target / data[by].map(cell_weight)


def shift_interval(data, by, shares, cluster, numerator, denominator, seed, reps=2000):
    """How far reweighting to the road network moves a ratio, with an interval.

    The two estimates share frames, so their difference is far less variable
    than either. Clusters are resampled whole and both are recomputed.
    """
    on_frame = data[data[by].map(lambda cell: shares.get(cell, 0.0) > 0)]
    groups = [rows for _, rows in on_frame.groupby(cluster)]

    def shift(rows):
        ones = pd.Series(1.0, index=rows.index)
        adjusted = network_weight(rows, by, shares, rows["speed_weight"])
        return weighted_ratio(rows, numerator, denominator, adjusted) - (
            weighted_ratio(rows, numerator, denominator, ones)
        )

    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        picked = rng.integers(0, len(groups), size=len(groups))
        draws.append(shift(pd.concat([groups[i] for i in picked], ignore_index=True)))
    low, high = np.quantile(draws, [0.025, 0.975])
    return {"estimate": shift(on_frame), "conf_low": low, "conf_high": high}
