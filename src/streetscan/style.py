"""One look for every figure."""

import matplotlib

INK = "#222222"
MUTED = "#8a8a8a"
ACCENT = "#08519C"
CITY_LABELS = {
    "mumbai": "Mumbai",
    "navi_mumbai": "Navi Mumbai",
    "bangalore": "Bangalore",
    "delhi": "Delhi",
    "Mumbai": "Mumbai",
    "Navi Mumbai": "Navi Mumbai",
    "Delhi": "Delhi",
    "bangkok": "Bangkok",
    "jakarta": "Jakarta",
    "lagos": "Lagos",
    "wayne": "Wayne County, MI",
    "dhaka": "Dhaka",
}
CITY_ORDER = ["mumbai", "navi_mumbai", "delhi", "bangalore"]
ROAD_CLASS_ORDER = ["residential", "tertiary", "major", "other"]
ROAD_CLASS_LABELS = {
    "residential": "Residential",
    "tertiary": "Tertiary",
    "major": "Secondary and above",
    "other": "Other",
}


def use_paper_style():
    matplotlib.use("Agg")
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 9,
            "axes.titlesize": 9,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.edgecolor": MUTED,
            "axes.grid": True,
            "axes.grid.axis": "x",
            "grid.color": "#e6e6e6",
            "grid.linewidth": 0.6,
            "xtick.color": INK,
            "ytick.color": INK,
            "ytick.left": False,
            "legend.frameon": False,
            "savefig.bbox": "tight",
        }
    )
