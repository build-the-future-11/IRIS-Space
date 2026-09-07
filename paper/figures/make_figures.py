"""Reproduce manuscript figures from the I SPY operations record.

The script parses the productive-run table in PIPELINE_OPERATIONS_RECORD.md.  It
does not read live services or infer unrecorded candidate outcomes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RECORD = ROOT / "PIPELINE_OPERATIONS_RECORD.md"

NAVY = "#17324D"
BLUE = "#2F6690"
TEAL = "#2A7F62"
AMBER = "#C47A20"
RED = "#B4463A"
VIOLET = "#7562A8"
INK = "#25313C"
MUTED = "#5C6873"
PAPER = "#FCFCFA"
PALE_BLUE = "#EEF4F8"
PALE_TEAL = "#EEF7F3"
PALE_AMBER = "#FBF4E8"
PALE_RED = "#FAEFED"


def _arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = MUTED,
    style: str = "-",
    width: float = 1.35,
    scale: float = 11,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=scale,
            linewidth=width,
            linestyle=style,
            color=color,
            shrinkA=3,
            shrinkB=3,
            zorder=4,
        )
    )


def _rounded_node(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    *,
    edge: str = BLUE,
    fill: str = PAPER,
    fontsize: float = 8.5,
    weight: str = "normal",
    text_color: str = INK,
    linewidth: float = 1.35,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.035,rounding_size=0.08",
            linewidth=linewidth,
            edgecolor=edge,
            facecolor=fill,
            zorder=3,
        )
    )
    ax.text(
        x + width / 2,
        y + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight=weight,
        color=text_color,
        zorder=5,
    )


@dataclass(frozen=True)
class Run:
    run_id: str
    time: datetime
    duplicate: bool
    objects: int
    detections: int
    clean: int
    sources: int
    ranked: int
    early_veto: int | None
    shortlist: int | None


def _number(value: str) -> int | None:
    value = value.strip().replace(",", "")
    return None if value in {"---", "--", "-", "—"} else int(value)


def load_runs() -> list[Run]:
    runs: list[Run] = []
    for line in RECORD.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| run_2026"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        duplicate = "†" in cells[0]
        run_id = cells[0].replace("run_", "").replace("†", "").strip()
        time = datetime.strptime(run_id, "%Y%m%dT%H%M%SZ")
        values = [_number(cell) for cell in cells[1:]]
        if any(value is None for value in values[:5]):
            raise ValueError(f"Incomplete core run row: {line}")
        runs.append(
            Run(
                run_id=run_id,
                time=time,
                duplicate=duplicate,
                objects=int(values[0]),
                detections=int(values[1]),
                clean=int(values[2]),
                sources=int(values[3]),
                ranked=int(values[4]),
                early_veto=values[5],
                shortlist=values[6],
            )
        )
    if len(runs) != 24:
        raise ValueError(f"Expected 24 productive runs, found {len(runs)}")
    return runs


def _save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / name, dpi=320, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_claim_boundary() -> None:
    """Map evidence sources to successive triage decisions."""

    fig, ax = plt.subplots(figsize=(10.8, 3.25))
    ax.set_xlim(0, 10.8)
    ax.set_ylim(0, 3.25)
    ax.axis("off")

    cards = [
        ("1  Priority", "Broker score\n+ light-curve features", "transient-like"),
        ("2  Image validation", "Multi-epoch\nimage stamps", "credible residual"),
        ("3  External checks", "Fresh registry\n+ catalog checks", "no recorded veto"),
        (
            "4  Reporting decision",
            "Complete gates\n+ independent review",
            "report preparation allowed",
        ),
        (
            "5  Classification",
            "Spectroscopy or\nclass-specific evidence",
            "physical class supported",
        ),
    ]
    x_positions = [0.18, 2.32, 4.46, 6.60, 8.74]
    width = 1.87
    for x, (heading, evidence, claim) in zip(x_positions, cards, strict=True):
        ax.add_patch(
            FancyBboxPatch(
                (x, 0.52),
                width,
                2.18,
                boxstyle="round,pad=0.03,rounding_size=0.06",
                edgecolor="#697984",
                facecolor="#F7F8F8",
                linewidth=1.0,
                zorder=2,
            )
        )
        ax.text(
            x + width / 2,
            2.35,
            heading,
            ha="center",
            va="center",
            fontsize=8.0,
            fontweight="bold",
            color=NAVY,
        )
        ax.text(
            x + width / 2,
            1.62,
            evidence,
            ha="center",
            va="center",
            fontsize=7.4,
            color=INK,
            linespacing=1.25,
        )
        ax.plot(
            [x + 0.22, x + width - 0.22],
            [1.15, 1.15],
            color="#B6C0C7",
            linewidth=0.8,
        )
        ax.text(
            x + width / 2,
            0.82,
            claim,
            ha="center",
            va="center",
            fontsize=7.0,
            color=MUTED,
        )
    for left, right in zip(x_positions, x_positions[1:], strict=False):
        _arrow(
            ax,
            (left + width + 0.03, 1.60),
            (right - 0.03, 1.60),
            color="#7A8790",
            width=0.9,
            scale=8,
        )
    ax.text(
        0.18,
        3.03,
        "evidence and decision sequence",
        ha="left",
        va="center",
        fontsize=8.2,
        color=MUTED,
    )
    _save(fig, "claim_boundary.png")


def make_flowchart() -> None:
    fig, ax = plt.subplots(figsize=(8.0, 9.2))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 9.2)
    ax.axis("off")

    blue = "#204a87"
    teal = "#147d75"
    amber = "#ad6500"
    red = "#9c2f2f"
    gray = "#4f5964"
    pale = "#f4f7fa"

    def node(
        x: float,
        y: float,
        w: float,
        h: float,
        text: str,
        edge: str = blue,
        fontsize: float = 10.2,
    ) -> None:
        box = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.035,rounding_size=0.08",
            linewidth=1.55,
            edgecolor=edge,
            facecolor=pale,
        )
        ax.add_patch(box)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize)

    def arrow(
        x1: float, y1: float, x2: float, y2: float, color: str = gray, style: str = "-"
    ) -> None:
        ax.add_patch(
            FancyArrowPatch(
                (x1, y1),
                (x2, y2),
                arrowstyle="-|>",
                mutation_scale=11,
                linewidth=1.25,
                linestyle=style,
                color=color,
                shrinkA=2,
                shrinkB=2,
            )
        )

    main_x, main_w, main_h = 2.15, 3.70, 0.72
    stages = [
        (7.90, "Public ZTF alerts + ALeRCE\nobject aggregation", blue),
        (6.95, "Photometric cleaning +\nper-object history", blue),
        (6.00, "Features, priority score +\nearly veto", amber),
        (5.05, "Fresh TNS + SkyBoT verification", teal),
        (4.10, "SIMBAD + VSX association", teal),
        (3.15, "Multi-epoch difference-stamp\nreview", teal),
        (2.20, "Claim wording + independent review", teal),
        (1.25, "TNS packet, submission +\noutcome closure", teal),
    ]
    for y, text, edge in stages:
        node(main_x, y, main_w, main_h, text, edge=edge)
    for (upper_y, _, _), (lower_y, _, _) in zip(stages, stages[1:], strict=False):
        arrow(4.00, upper_y, 4.00, lower_y + main_h)

    node(
        0.10,
        4.92,
        1.65,
        0.90,
        "BLOCKED /\nUNKNOWN\nrequired evidence\nabsent",
        edge=amber,
        fontsize=7.8,
    )
    node(6.25, 3.55, 1.65, 0.90, "REJECTED\npositive veto\nevidence", edge=red, fontsize=8.6)
    node(
        6.25,
        1.18,
        1.65,
        0.78,
        "DESIGNATED\nregistry outcome;\nphysical class open",
        edge=teal,
        fontsize=8.0,
    )

    arrow(main_x, 5.37, 1.75, 5.37, color=amber, style="--")
    arrow(main_x + main_w, 6.32, 6.25, 4.10, color=red, style="--")
    arrow(main_x + main_w, 4.42, 6.25, 4.00, color=red, style="--")
    arrow(main_x + main_w, 3.47, 6.25, 4.00, color=red, style="--")
    arrow(main_x + main_w, 1.57, 6.25, 1.57, color=teal, style="--")

    _save(fig, "pipeline_flow.png")


def make_iris_architecture() -> None:
    """Render IRIS as three coupled planes with one fail-closed reporting gate."""

    fig, ax = plt.subplots(figsize=(11.0, 7.8))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 7.8)
    ax.axis("off")

    lanes = [
        (5.25, 1.55, "SCIENTIFIC DATA PLANE", BLUE, PALE_BLUE),
        (3.32, 1.55, "EXTERNAL EVIDENCE PLANE", TEAL, PALE_TEAL),
        (1.08, 1.75, "REVIEW + DECISION PLANE", AMBER, PALE_AMBER),
    ]
    for y, height, label, color, fill in lanes:
        ax.add_patch(
            FancyBboxPatch(
                (0.17, y),
                10.66,
                height,
                boxstyle="round,pad=0.02,rounding_size=0.08",
                edgecolor=color,
                facecolor=fill,
                linewidth=0.9,
                alpha=0.76,
                zorder=0,
            )
        )
        ax.text(
            0.38,
            y + height - 0.22,
            label,
            ha="left",
            va="center",
            fontsize=7.6,
            fontweight="bold",
            color=color,
        )

    data_y = 5.60
    data_nodes = [
        (0.55, "Broker snapshot\nor local table"),
        (3.12, "Canonical schema\n+ dataset digest"),
        (5.69, "Band-aware\nfeature map"),
        (8.26, "Immutable candidate\nversion $V_i$"),
    ]
    for x, label in data_nodes:
        _rounded_node(ax, x, data_y, 2.05, 0.70, label, edge=BLUE, fill=PAPER, fontsize=8.3)
    for (x_left, _), (x_right, _) in zip(data_nodes, data_nodes[1:], strict=False):
        _arrow(ax, (x_left + 2.05, data_y + 0.35), (x_right, data_y + 0.35), color=BLUE)

    evidence_y = 3.66
    evidence_nodes = [
        (0.55, "TNS · SkyBoT\nSIMBAD · VSX"),
        (3.12, "Bind identity, position,\nepoch, radius + TTL"),
        (5.69, "Digest-preserving\nevidence bundle"),
    ]
    for x, label in evidence_nodes:
        _rounded_node(ax, x, evidence_y, 2.05, 0.70, label, edge=TEAL, fill=PAPER, fontsize=8.1)
    for (x_left, _), (x_right, _) in zip(evidence_nodes, evidence_nodes[1:], strict=False):
        _arrow(ax, (x_left + 2.05, evidence_y + 0.35), (x_right, evidence_y + 0.35), color=TEAL)
    _rounded_node(
        ax,
        8.26,
        evidence_y,
        2.05,
        0.70,
        "BLOCK / REJECT\nveto or invalid evidence",
        edge=RED,
        fill=PALE_RED,
        fontsize=7.8,
        weight="bold",
        text_color=RED,
    )
    _arrow(ax, (7.74, evidence_y + 0.35), (8.26, evidence_y + 0.35), color=RED, style="--")

    decision_y = 1.47
    decision_nodes = [
        (0.34, "Inspectable\npriority $q_i$"),
        (2.48, "Finite review\nqueue $\mathcal{Q}_K$"),
        (4.62, "Portable dossier +\nindependent review"),
        (6.76, "Preflight gate\n$\mathcal{P}_i=1$"),
        (8.90, "Human review +\nreport preparation"),
    ]
    for index, (x, label) in enumerate(decision_nodes):
        edge = RED if index == 3 else (TEAL if index == 4 else AMBER)
        fill = PALE_RED if index == 3 else (PALE_TEAL if index == 4 else PAPER)
        _rounded_node(ax, x, decision_y, 1.78, 0.74, label, edge=edge, fill=fill, fontsize=7.8)
    for (x_left, _), (x_right, _) in zip(decision_nodes, decision_nodes[1:], strict=False):
        _arrow(ax, (x_left + 1.78, decision_y + 0.37), (x_right, decision_y + 0.37), color=INK)

    ax.text(
        1.23,
        2.36,
        "feature inputs",
        ha="center",
        va="center",
        fontsize=7.1,
        color=BLUE,
    )
    _arrow(ax, (1.23, 2.29), (1.23, decision_y + 0.74), color=BLUE)
    ax.text(
        5.51,
        2.36,
        "candidate version",
        ha="center",
        va="center",
        fontsize=7.1,
        color=BLUE,
    )
    _arrow(ax, (5.51, 2.29), (5.51, decision_y + 0.74), color=BLUE)
    _arrow(ax, (6.72, evidence_y), (7.65, decision_y + 0.74), color=TEAL)

    _rounded_node(
        ax,
        2.17,
        1.13,
        3.40,
        0.25,
        "SHADOW ONLY · anomaly score $a_i$ · rank influence only",
        edge=VIOLET,
        fill="#F2EFF8",
        fontsize=7.0,
        text_color=VIOLET,
    )
    _arrow(ax, (3.88, 1.38), (3.37, decision_y), color=VIOLET, style="--")

    _save(fig, "iris_architecture.png")


def make_operational_heatmap(runs: list[Run]) -> None:
    metrics = []
    for run in runs:
        metrics.append(
            [
                run.clean / run.detections,
                run.sources / run.objects,
                run.ranked / run.sources,
                np.nan if run.early_veto is None else run.early_veto / run.objects,
                np.nan if run.shortlist is None else run.shortlist / run.objects,
            ]
        )
    data = np.asarray(metrics, dtype=float)

    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#e6e8eb")
    fig, ax = plt.subplots(figsize=(8.7, 9.5))
    im = ax.imshow(np.ma.masked_invalid(data), aspect="auto", cmap=cmap, vmin=0, vmax=1)
    labels = [run.time.strftime("%m-%d %H:%M") + (" †" if run.duplicate else "") for run in runs]
    ax.set_yticks(np.arange(len(runs)), labels=labels, fontsize=7.4)
    ax.set_xticks(
        np.arange(5),
        labels=[
            "clean /\ndetections",
            "sources /\nobjects",
            "ranked /\nsources",
            "early veto /\nobjects",
            "shortlist /\nobjects",
        ],
        fontsize=8.3,
    )
    ax.tick_params(length=0)
    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            value = data[row, col]
            text = "NA" if np.isnan(value) else f"{value:.2f}"
            color = (
                "#59636e"
                if np.isnan(value)
                else ("white" if value < 0.28 or value > 0.78 else "black")
            )
            ax.text(col, row, text, ha="center", va="center", fontsize=6.4, color=color)
    transition = next(i for i, run in enumerate(runs) if run.run_id == "20260705T161401Z")
    ax.axhline(transition - 0.5, color=RED, linewidth=2.0)
    ax.add_patch(
        Rectangle((4.56, -0.48), 0.16, transition - 0.02, facecolor=BLUE, edgecolor="none")
    )
    ax.add_patch(
        Rectangle(
            (4.56, transition - 0.48),
            0.16,
            len(runs) - transition - 0.04,
            facecolor=AMBER,
            edgecolor="none",
        )
    )
    ax.text(4.84, (transition - 1) / 2, "earlier policy", rotation=90, va="center", color=BLUE)
    ax.text(
        4.84,
        (transition + len(runs) - 1) / 2,
        "retuned policy",
        rotation=90,
        va="center",
        color=AMBER,
    )
    ax.set_xlim(-0.5, 5.13)
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.025)
    cbar.set_label("within-run fraction", fontsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    _save(fig, "run_diagnostic_heatmap.png")


def make_campaign_dynamics(runs: list[Run]) -> dict[str, float | int]:
    idx = np.arange(len(runs))
    labels = [run.time.strftime("%m-%d") for run in runs]
    detections = np.asarray([run.detections for run in runs], dtype=float)
    clean = np.asarray([run.clean for run in runs], dtype=float)
    early = np.asarray(
        [np.nan if run.early_veto is None else run.early_veto / run.objects for run in runs]
    )
    shortlist = np.asarray(
        [np.nan if run.shortlist is None else run.shortlist / run.objects for run in runs]
    )
    transition = next(i for i, run in enumerate(runs) if run.run_id == "20260705T161401Z")

    fig, axes = plt.subplots(2, 1, figsize=(10.0, 6.6), sharex=True, gridspec_kw={"hspace": 0.10})
    ax = axes[0]
    ax.plot(
        idx,
        detections,
        "o-",
        color=BLUE,
        linewidth=1.5,
        markersize=4.2,
        label="detection rows",
    )
    ax.plot(idx, clean, "s-", color=TEAL, linewidth=1.5, markersize=3.8, label="clean rows")
    ax.set_yscale("log")
    ax.set_ylabel("rows per run (log scale)")
    ax.legend(frameon=False, ncol=2, loc="upper left")
    ax.grid(axis="y", alpha=0.22)

    ax = axes[1]
    ax.plot(
        idx,
        early,
        "o-",
        color=RED,
        linewidth=1.7,
        markersize=4.2,
        label="early-veto fraction",
    )
    ax.plot(
        idx,
        shortlist,
        "o-",
        color=TEAL,
        linewidth=1.7,
        markersize=4.2,
        label="shortlist fraction",
    )
    ax.set_ylim(-0.025, 1.05)
    ax.set_ylabel("fraction of query objects")
    ax.legend(frameon=False, ncol=2, loc="upper left")
    ax.grid(axis="y", alpha=0.22)
    for current in axes:
        current.axvspan(-0.5, transition - 0.5, color=BLUE, alpha=0.055, linewidth=0)
        current.axvspan(transition - 0.5, len(runs) - 0.5, color=AMBER, alpha=0.075, linewidth=0)
        current.axvline(transition - 0.5, color=RED, linestyle="--", linewidth=1.25)
        current.spines[["top", "right"]].set_visible(False)
    axes[0].text(
        transition - 0.35,
        axes[0].get_ylim()[1] / 1.12,
        "recorded regime change",
        color=RED,
        fontsize=8.5,
        ha="left",
        va="top",
    )
    axes[1].set_xticks(idx, labels=labels, rotation=65, ha="right", fontsize=7.2)
    axes[1].set_xlabel("productive run (UTC)")
    _save(fig, "campaign_dynamics.png")

    unique = [run for run in runs if not run.duplicate]
    observed = [run for run in unique if run.early_veto is not None and run.shortlist is not None]
    pre = [run for run in observed if run.run_id <= "20260705T050105Z"]
    post = [run for run in observed if run.run_id >= "20260705T161401Z"]

    def total(group: list[Run], field: str) -> int:
        return sum(int(getattr(run, field) or 0) for run in group)

    metrics: dict[str, float | int] = {
        "productive_runs": len(runs),
        "nonduplicate_pulls": len(unique),
        "unique_pull_detection_rows": total(unique, "detections"),
        "unique_pull_clean_rows": total(unique, "clean"),
        "unique_pull_clean_fraction": total(unique, "clean") / total(unique, "detections"),
        "pre_runs": len(pre),
        "pre_objects": total(pre, "objects"),
        "pre_early_veto_fraction": total(pre, "early_veto") / total(pre, "objects"),
        "pre_shortlist_fraction": total(pre, "shortlist") / total(pre, "objects"),
        "post_runs": len(post),
        "post_objects": total(post, "objects"),
        "post_early_veto_fraction": total(post, "early_veto") / total(post, "objects"),
        "post_shortlist_fraction": total(post, "shortlist") / total(post, "objects"),
    }
    return metrics


def make_regime_bootstrap(runs: list[Run]) -> dict[str, float | int]:
    """Cluster-bootstrap regime ratios with productive runs as the sampling unit."""

    observed = [
        run
        for run in runs
        if not run.duplicate and run.early_veto is not None and run.shortlist is not None
    ]
    pre = [run for run in observed if run.run_id <= "20260705T050105Z"]
    post = [run for run in observed if run.run_id >= "20260705T161401Z"]
    rng = np.random.default_rng(20260906)
    draws = 50000

    def bootstrap(group: list[Run], field: str) -> tuple[float, np.ndarray]:
        objects = np.asarray([run.objects for run in group], dtype=float)
        outcomes = np.asarray([float(getattr(run, field) or 0) for run in group])
        sample = rng.integers(0, len(group), size=(draws, len(group)))
        ratio = outcomes[sample].sum(axis=1) / objects[sample].sum(axis=1)
        return outcomes.sum() / objects.sum(), ratio

    panels: list[tuple[str, str, str]] = [
        ("Early-veto fraction", "early_veto", RED),
        ("Shortlist fraction", "shortlist", TEAL),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.7), sharey=False)
    metrics: dict[str, float | int] = {"cluster_bootstrap_draws": draws}

    for ax, (title, field, color) in zip(axes, panels, strict=True):
        pre_point, pre_draws = bootstrap(pre, field)
        post_point, post_draws = bootstrap(post, field)
        difference = post_draws - pre_draws
        pre_ci = np.quantile(pre_draws, [0.025, 0.975])
        post_ci = np.quantile(post_draws, [0.025, 0.975])
        diff_ci = np.quantile(difference, [0.025, 0.975])
        points = np.asarray([pre_point, post_point])
        lower = points - np.asarray([pre_ci[0], post_ci[0]])
        upper = np.asarray([pre_ci[1], post_ci[1]]) - points
        violin = ax.violinplot(
            [pre_draws, post_draws],
            positions=[0, 1],
            widths=0.72,
            showmeans=False,
            showmedians=False,
            showextrema=False,
            points=240,
        )
        for index, body in enumerate(violin["bodies"]):
            body.set_facecolor("#AAB4BE" if index == 0 else color)
            body.set_edgecolor("none")
            body.set_alpha(0.58)
        ax.errorbar(
            [0, 1],
            points,
            yerr=np.vstack([lower, upper]),
            fmt="o",
            color=INK,
            ecolor=INK,
            markerfacecolor="white",
            markeredgewidth=1.2,
            markersize=5.4,
            elinewidth=1.5,
            capsize=5,
            zorder=5,
        )
        ax.set_xticks([0, 1], ["Earlier policy", "Retuned policy"])
        ax.set_title(title, loc="left", fontweight="bold", color=NAVY)
        ax.set_ylabel("pooled fraction")
        ax.grid(axis="y", alpha=0.20)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylim(0, max(0.18, float(post_ci[1]) * 1.35, float(pre_ci[1]) * 1.20))
        ax.text(
            0.04,
            0.96,
            f"$\\Delta$ = {post_point - pre_point:+.3f}\n"
            f"95% interval [{diff_ci[0]:+.3f}, {diff_ci[1]:+.3f}]",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8.5,
            color=INK,
            bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": "#D8DDE2", "alpha": 0.9},
        )

        metrics.update(
            {
                f"pre_{field}_cluster_ci_low": float(pre_ci[0]),
                f"pre_{field}_cluster_ci_high": float(pre_ci[1]),
                f"post_{field}_cluster_ci_low": float(post_ci[0]),
                f"post_{field}_cluster_ci_high": float(post_ci[1]),
                f"delta_{field}": float(post_point - pre_point),
                f"delta_{field}_cluster_ci_low": float(diff_ci[0]),
                f"delta_{field}_cluster_ci_high": float(diff_ci[1]),
            }
        )

    _save(fig, "regime_bootstrap.png")
    return metrics


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9.5,
            "axes.titlesize": 12,
            "axes.labelsize": 9.5,
            "figure.dpi": 130,
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "axes.edgecolor": "#BFC7CE",
            "axes.labelcolor": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
        }
    )
    runs = load_runs()
    make_claim_boundary()
    make_flowchart()
    make_iris_architecture()
    make_operational_heatmap(runs)
    metrics = make_campaign_dynamics(runs)
    metrics.update(make_regime_bootstrap(runs))
    (OUT / "derived_run_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
