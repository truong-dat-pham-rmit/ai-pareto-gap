"""Plot the monthly staircase/log-linear sensitivity comparison.

Requires matplotlib (``python -m pip install matplotlib``).
From the repository root: ``python scripts/plot_slopes.py``.
The input is computed by analyze_slopes.py; this script only plots its results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
INK = "#172B3A"
MUTED = "#586773"
BLUE = "#007FA3"
ORANGE = "#BC642D"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "reports/monthly-comparison.json")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "outputs/slope-gap-march-october-2026",
        help="Output path stem; PNG and SVG are both written.",
    )
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    scenarios = {
        int(s["floor"]): s for s in data["scenarios"]
        if s["score_policy"] == "measured"
        and s["budget_min"] == 0.01 and s["budget_max"] == 10
        and s["floor"] in (20, 30, 40)
    }
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "svg.fonttype": "none", "savefig.facecolor": "white",
    })
    fig, axes = plt.subplots(3, 1, figsize=(11.6, 9.4), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.105, right=0.81, top=0.785, bottom=0.18, hspace=0.31)
    fig.text(0.065, 0.96, "How interpolation changes the US–China cost-aware gap",
             fontsize=19, weight="bold", va="top")
    fig.text(0.065, 0.912, r"March–October 2026  ·  Budget range: \$0.01–\$10 per benchmark task",
             fontsize=12.2, color=MUTED)
    fig.text(0.065, 0.88,
             "G = US area − China area, averaged over log budget and measured above each capability floor.",
             fontsize=11.2, color=MUTED)
    handles = [
        Line2D([], [], color=ORANGE, marker="o", markersize=5.5, linewidth=2,
               label="Observed configurations (staircase)"),
        Line2D([], [], color=BLUE, marker="D", markersize=5, linewidth=2,
               linestyle=(0, (4, 2.5)), label="Log-linear interpolation (assumption)"),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.058, 0.855),
               ncol=2, frameon=False, handlelength=3, columnspacing=2, fontsize=10.5)
    x = list(range(8))
    for ax, floor in zip(axes, (20, 30, 40)):
        rows = [r for r in scenarios[floor]["series"]
                if "2026-03" <= r["month"] <= "2026-10"]
        if len(rows) != 8:
            raise ValueError(f"Expected eight monthly observations for floor {floor}.")
        staircase = [r["staircase_G"] for r in rows]
        slope = [r["slope_G"] for r in rows]
        ax.set_facecolor("#FCFDFE")
        ax.axhspan(-1.1, 0, color="#F3F5F7", zorder=0)
        ax.axhline(0, color="#7A8790", linewidth=1.05, zorder=2)
        ax.grid(axis="y", color="#E3E8EC", linewidth=0.75)
        ax.plot(x, staircase, color=ORANGE, marker="o", linewidth=2,
                markersize=5.5, markeredgecolor="white", markeredgewidth=0.8,
                zorder=4)
        ax.plot(x, slope, color=BLUE, marker="D", linewidth=2,
                linestyle=(0, (4, 2.5)), markersize=5,
                markeredgecolor="white", markeredgewidth=0.8, zorder=5)
        ax.set_ylim(-1.1, 7.3)
        ax.set_xlim(-0.15, 7.25)
        ax.set_yticks([0, 2, 4, 6])
        ax.tick_params(axis="both", length=0, pad=8, labelsize=10)
        ax.set_title(f"Capability floor {floor}", loc="left", fontsize=11.5,
                     weight="bold", pad=7)
        for edge in ("top", "right", "left", "bottom"):
            ax.spines[edge].set_visible(False)
        ax.text(1.055, 0.91, "OCT 7 GAP", transform=ax.transAxes,
                color=MUTED, fontsize=9, weight="bold", va="top")
        ax.text(1.055, 0.70, f"{slope[-1]:.2f}", transform=ax.transAxes,
                color=BLUE, fontsize=22, weight="bold", va="top")
        ax.text(1.055, 0.41, f"vs {staircase[-1]:.2f} observed", transform=ax.transAxes,
                color=ORANGE, fontsize=10, va="top")
        ax.text(1.055, 0.16, f"Change: {slope[-1] - staircase[-1]:+.2f}",
                transform=ax.transAxes, color=MUTED, fontsize=10, va="top")
    axes[-1].set_xticks(x, ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct 7*"])
    fig.text(0.021, 0.50, "Average above-floor index-point gap  ·  positive: US lead; negative: China lead",
             rotation=90, ha="center", va="center", fontsize=10.8, color=MUTED)
    fig.text(0.065, 0.113,
             "Source: Artificial Analysis v4.3.2, 7 Oct 2026 snapshot. Only non-estimated scores with positive cost data.",
             fontsize=9.6, color=MUTED)
    fig.text(0.065, 0.088,
             "Release cohorts use fixed snapshot scores and prices; these are not historical-price comparisons.",
             fontsize=9.6, color=MUTED)
    fig.text(0.065, 0.063,
             "Interpolation joins adjacent observed frontier points in log cost. Equal weight is assigned to each budget doubling.",
             fontsize=9.6, color=MUTED)
    fig.text(0.065, 0.038,
             "Lines between monthly samples only guide the eye. *October is partial, ending on 7 October 2026.",
             fontsize=9.6, color=MUTED)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".png", ".svg"):
        target = args.output.with_suffix(suffix)
        fig.savefig(target, dpi=180)
        if suffix == ".svg":
            # Matplotlib emits path whitespace that Git flags in generated SVG.
            target.write_text("\n".join(line.rstrip() for line in target.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8", newline="\n")
        print(target)
    plt.close(fig)


if __name__ == "__main__":
    main()
