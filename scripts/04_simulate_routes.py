"""Check that a route sample is a probability sample with a computable design.

A city is a grid of streets. Points are drawn at random, a routing rule turns
them into a ride, and a camera saves frames on a timer. The claim to check is
that a stretch of road is photographed at a rate proportional to m / v, where
m is how often the routing rule sends the rider along it, averaged over draws,
and v is the speed there. If so, weighting a frame by v / m recovers the
network without any model. m is found by rerunning the draw and the routing.

The outcome is built as a stress test: within each road class, the streets the
routing rule favours are busier and more male. Reweighting by road class
cannot see that, so it should stay biased; weighting by v / m should not.
"""

import networkx as nx
import numpy as np
import pandas as pd

from streetscan.config import TABLE_DIR

SEED = 20261113
GRID = 12
ARTERIAL_EVERY = 4
SEGMENT_M = 500
# Arterials are twice as fast. At three times as fast, the routing rule's taste
# for arterials and the timer's taste for slow streets happen to cancel here.
SPEED_MPS = {"major": 6.0, "residential": 3.0}
FRAME_INTERVAL_SEC = 60
SAMPLE_SIZE = 30
DESIGN_DRAWS = 4000
REPLICATIONS = 2000


def build_city():
    graph = nx.grid_2d_graph(GRID, GRID)
    rows = []
    for a, b in graph.edges:
        along_row = a[0] == b[0]
        line = a[0] if along_row else a[1]
        road_class = "major" if line % ARTERIAL_EVERY == 0 else "residential"
        rows.append(
            {
                "a": a,
                "b": b,
                "road_class": road_class,
                "speed_mps": SPEED_MPS[road_class],
            }
        )
    edges = pd.DataFrame(rows)
    edges["seconds"] = SEGMENT_M / edges["speed_mps"]
    for index, row in edges.iterrows():
        graph.edges[row["a"], row["b"]].update(seconds=row["seconds"], index=index)
    return graph, edges


def route_traversals(graph, paths, times, edges, drawn):
    """How many times the ride crosses each street, for one draw of points.

    The rider goes to the nearest unvisited sampled street by travel time,
    rides along it, and repeats.
    """
    counts = np.zeros(len(edges))
    remaining = list(drawn)
    first = remaining.pop(0)
    counts[first] += 1
    here = edges.at[first, "b"]
    while remaining:
        best = None
        for position, edge in enumerate(remaining):
            for near, far in (("a", "b"), ("b", "a")):
                seconds = times[here][edges.at[edge, near]]
                if best is None or seconds < best[0]:
                    best = (
                        seconds,
                        position,
                        edges.at[edge, near],
                        edges.at[edge, far],
                    )
        assert best is not None
        _, position, entry, exit_node = best
        path = paths[here][entry]
        for u, v in zip(path[:-1], path[1:]):
            counts[graph.edges[u, v]["index"]] += 1
        counts[remaining.pop(position)] += 1
        here = exit_node
    return counts


def ratio(frames, weight):
    return (weight * frames["women"]).sum() / (weight * frames["people"]).sum()


rng = np.random.default_rng(SEED)
graph, edges = build_city()
times = dict(nx.all_pairs_dijkstra_path_length(graph, weight="seconds"))
paths = dict(nx.all_pairs_dijkstra_path(graph, weight="seconds"))


def draw_traversals():
    drawn = rng.choice(len(edges), size=SAMPLE_SIZE, replace=False)
    return route_traversals(graph, paths, times, edges, drawn)


# The design's traversal intensity: rerun the draw and the routing rule.
intensity = np.mean([draw_traversals() for _ in range(DESIGN_DRAWS)], axis=0)
edges["intensity"] = intensity

favoured = edges.groupby("road_class")["intensity"].transform(
    lambda x: (np.log(x) - np.log(x).mean()) / np.log(x).std()
)
base = edges["road_class"].map({"major": 0.15, "residential": 0.26})
edges["women_share"] = (base - 0.05 * favoured).clip(0.02, 0.6)
edges["pedestrians"] = np.exp(0.4 * favoured) * edges["road_class"].map(
    {"major": 0.9, "residential": 1.6}
)

truth = (edges["pedestrians"] * edges["women_share"]).sum() / edges["pedestrians"].sum()
class_share = edges["road_class"].value_counts(normalize=True)

frame_counts = np.zeros(len(edges))
draws = []
for _ in range(REPLICATIONS):
    passes = draw_traversals()
    # A timer with a random start fires, on average, once per interval.
    n_frames = rng.poisson(passes * edges["seconds"] / FRAME_INTERVAL_SEC)
    frame_counts += n_frames
    frames = edges.loc[edges.index.repeat(n_frames)].copy()
    frames["people"] = rng.poisson(frames["pedestrians"])
    frames["women"] = rng.binomial(frames["people"], frames["women_share"])
    speed = frames["speed_mps"]
    class_weight = speed.groupby(frames["road_class"]).transform("sum")
    by_class = speed * frames["road_class"].map(class_share) / class_weight
    draws.append(
        {
            "per minute": ratio(frames, pd.Series(1.0, index=frames.index)),
            "per metre": ratio(frames, speed),
            "road network": ratio(frames, by_class),
            "design weights": ratio(frames, speed / frames["intensity"]),
        }
    )

draws = pd.DataFrame(draws)
summary = pd.DataFrame(
    {
        "truth": truth,
        "mean_estimate": draws.mean(),
        "bias": draws.mean() - truth,
        "sd_estimate": draws.std(),
    }
)
summary.index.name = "estimator"
summary.to_csv(TABLE_DIR / "route_simulation.csv", float_format="%.10g")

predicted = intensity * edges["seconds"] / FRAME_INTERVAL_SEC
observed = frame_counts / REPLICATIONS
by_class = edges.groupby("road_class")["intensity"].mean()
check = pd.DataFrame(
    {
        "quantity": [
            "frames_observed_over_predicted",
            "frames_correlation",
            "intensity_major_over_residential",
            "intensity_min",
            "intensity_max_over_min",
            "streets",
        ],
        "value": [
            observed.sum() / predicted.sum(),
            np.corrcoef(observed, predicted)[0, 1],
            by_class["major"] / by_class["residential"],
            intensity.min(),
            intensity.max() / intensity.min(),
            len(edges),
        ],
    }
)
check.to_csv(
    TABLE_DIR / "route_simulation_check.csv", index=False, float_format="%.10g"
)
