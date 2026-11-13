import numpy as np
import pandas as pd
import pytest

from streetscan.designs import (
    MIN_SPEED_MPS,
    class_shares,
    clean_noise,
    post_stratified,
    road_class,
    with_speed_weight,
)


def test_road_class_collapses_links_and_unknowns():
    types = pd.Series(["living_street", "primary_link", "tertiary", "footway", None])
    assert road_class(types).tolist() == [
        "residential",
        "major",
        "tertiary",
        "other",
        "other",
    ]


def test_speed_weight_recovers_a_per_meter_share():
    """A camera on a timer sees a slow road in proportion to the time on it."""
    slow = pd.DataFrame({"speed_mps": 2.0, "women": 1, "people": 2}, index=range(50))
    fast = pd.DataFrame({"speed_mps": 10.0, "women": 0, "people": 2}, index=range(10))
    # Equal lengths of each road: 100 s and 20 s at one frame every 2 s.
    frames = with_speed_weight(pd.concat([slow, fast], ignore_index=True))
    weight = frames["speed_weight"]
    per_minute = frames["women"].sum() / frames["people"].sum()
    per_meter = (weight * frames["women"]).sum() / (weight * frames["people"]).sum()
    assert per_minute == pytest.approx(50 / 120)
    assert per_meter == pytest.approx(0.25)


def test_speed_weight_drops_missing_and_floors_stationary_frames():
    frames = with_speed_weight(pd.DataFrame({"speed_mps": [0.0, np.nan, 4.0]}))
    assert frames["speed_weight"].tolist() == [MIN_SPEED_MPS, 4.0]


def test_post_stratified_matches_reweighting_by_hand():
    data = pd.DataFrame(
        {
            "road_class": ["residential"] * 2 + ["major"] * 6 + ["off_frame"] * 2,
            "y": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0],
        }
    )
    shares = {"residential": 0.8, "major": 0.1, "tertiary": 0.1}
    sample, covered_share = post_stratified(data, "road_class", shares)
    # Tertiary roads have no rows, so the estimate speaks for 90% of the frame.
    assert covered_share == pytest.approx(0.9)
    expected = (0.8 * 0.5 + 0.1 * (1 / 6)) / 0.9
    assert sample.mean("y").estimate == pytest.approx(expected)
    assert sample.n_observations == 8


def test_class_shares_sum_to_one():
    shares = class_shares(pd.Series(["a", "a", "b", "c"]))
    assert shares == {"a": 0.5, "b": 0.25, "c": 0.25}


def test_clean_noise_orders_values_and_drops_duplicates():
    row = {"day": 1, "itinerary_id": 11, "latitude": 28.6, "longitude": 77.1}
    noise = pd.DataFrame(
        [
            {**row, "min_db": 84.1, "max_db": 60.7, "road_type": "residential"},
            {**row, "min_db": 84.1, "max_db": 60.7, "road_type": "residential"},
            {**row, "min_db": np.nan, "max_db": np.nan, "road_type": None},
        ]
    )
    cleaned = clean_noise(noise)
    assert len(cleaned) == 1
    assert cleaned[["min_db", "max_db"]].iloc[0].tolist() == [60.7, 84.1]
