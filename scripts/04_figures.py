"""Draw the paper's figures from the tables in tabs/."""

import matplotlib.pyplot as plt
import pandas as pd

from streetscan.config import TABLE_DIR
from streetscan.paper import save_evidence
from streetscan.style import (
    ACCENT,
    CITY_LABELS,
    CITY_ORDER,
    INK,
    MUTED,
    ROAD_CLASS_LABELS,
    ROAD_CLASS_ORDER,
    use_paper_style,
)

use_paper_style()

estimates = pd.read_csv(TABLE_DIR / "estimates.csv")
road_mix = pd.read_csv(TABLE_DIR / "gopro_road_mix.csv")

WOMEN_ROWS = [
    ("gopro", "per minute of riding", "Video, per minute of riding"),
    ("gopro", "per metre of route", "Video, per metre of route"),
    ("gopro", "road network", "Video, reweighted to the road network"),
    ("streetview", "road-class adjusted", "Street View, sampled locations"),
]


def women_share_figure():
    women = estimates[estimates["outcome"] == "women_share"].copy()
    women["city"] = women["city"].str.lower().str.replace(" ", "_")
    figure, axes = plt.subplots(
        len(CITY_ORDER),
        1,
        figsize=(6.5, 5.4),
        sharex=True,
        constrained_layout=True,
        gridspec_kw={"height_ratios": [4, 4, 4, 3]},
    )
    for axis, city in zip(axes, CITY_ORDER):
        labels = []
        for application, estimator, label in WOMEN_ROWS:
            row = women[
                (women["city"] == city)
                & (women["application"] == application)
                & (women["estimator"] == estimator)
            ]
            if row.empty:
                continue
            row = row.iloc[0]
            position = len(labels)
            labels.append(label)
            colour = ACCENT if estimator == "road network" else INK
            axis.plot(
                [100 * row["conf_low"], 100 * row["conf_high"]],
                [position, position],
                color=colour,
                linewidth=1.2,
            )
            axis.plot(100 * row["estimate"], position, "o", color=colour, markersize=4)
        axis.set_yticks(range(len(labels)), labels)
        axis.set_ylim(len(labels) - 0.5, -0.5)
        axis.set_title(CITY_LABELS[city])
    axes[-1].set_xlabel("Women's share of pedestrians (%)")
    axes[-1].set_xlim(10, 35)
    return figure


def road_mix_figure():
    figure, axes = plt.subplots(
        1, len(CITY_ORDER), figsize=(6.5, 2.5), sharex=True, sharey=True
    )
    for axis, city in zip(axes, CITY_ORDER):
        mix = road_mix[road_mix["city"] == city].set_index("road_class")
        mix = mix.reindex(ROAD_CLASS_ORDER).fillna(0)
        positions = range(len(mix))
        axis.hlines(
            positions,
            100 * mix["sample_share"],
            100 * mix["frame_share"],
            color=MUTED,
            linewidth=0.8,
        )
        axis.plot(100 * mix["sample_share"], positions, "o", color=ACCENT, markersize=4)
        axis.plot(100 * mix["frame_share"], positions, "o", color=INK, markersize=4)
        axis.set_title(CITY_LABELS[city])
        axis.set_xlim(-5, 100)
        axis.set_xticks([0, 50, 100])
    axes[0].set_yticks(
        range(len(ROAD_CLASS_ORDER)), [ROAD_CLASS_LABELS[c] for c in ROAD_CLASS_ORDER]
    )
    axes[0].set_ylim(len(ROAD_CLASS_ORDER) - 0.5, -0.5)
    # Label the two series once, where they sit furthest apart.
    labelled = "delhi"
    delhi = road_mix[road_mix["city"] == labelled].set_index("road_class")
    axis = axes[CITY_ORDER.index(labelled)]
    for column, text, colour in [
        ("sample_share", "drawn\nsample", ACCENT),
        ("frame_share", "video\nframes", INK),
    ]:
        axis.annotate(
            text,
            (100 * delhi.loc["residential", column], 0),
            xytext=(0, -7),
            textcoords="offset points",
            color=colour,
            fontsize=7,
            ha="center",
            va="top",
        )
    figure.supxlabel("Share of road class (%)", fontsize=9)
    figure.tight_layout()
    return figure


save_evidence(women_share_figure(), "women")
save_evidence(road_mix_figure(), "roadmix")
