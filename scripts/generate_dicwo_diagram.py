"""Generate a clean, publication-quality DiCWO architecture diagram."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.2,
})

# ── Minimal palette ───────────────────────────────────────────────────────────
BLUE     = "#3B6B9E"
BLUE_L   = "#E8F0F8"
GRAY     = "#F5F6F8"
GRAY_D   = "#555555"
GRAY_M   = "#999999"
BLACK    = "#222222"
WHITE    = "#FFFFFF"
GREEN    = "#3A8E6A"
AMBER    = "#D4953A"
RED_SOFT = "#C0504D"
TEAL     = "#2A7B88"


def _box(ax, x, y, w, h, title, subtitle=None, fc=WHITE, ec=BLUE,
         lw=1.4, fontsize=9, title_weight="bold", radius=0.08):
    """Clean rounded box with title and optional subtitle."""
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle=f"round,pad={radius}",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=3,
    )
    ax.add_patch(box)
    if subtitle:
        ax.text(x, y + 0.12, title, ha="center", va="center",
                fontsize=fontsize, fontweight=title_weight, color=BLACK, zorder=4)
        ax.text(x, y - 0.14, subtitle, ha="center", va="center",
                fontsize=fontsize - 1.5, color=GRAY_D, zorder=4)
    else:
        ax.text(x, y, title, ha="center", va="center",
                fontsize=fontsize, fontweight=title_weight, color=BLACK, zorder=4)


def _arrow(ax, x1, y1, x2, y2, color=GRAY_D, lw=1.2,
           style="-|>", connstyle="arc3,rad=0", zorder=2):
    a = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, color=color,
        connectionstyle=connstyle,
        linewidth=lw, zorder=zorder, mutation_scale=13,
    )
    ax.add_patch(a)


def _varrow(ax, x, y_top, y_bot, **kw):
    """Vertical downward arrow."""
    _arrow(ax, x, y_top, x, y_bot, **kw)


def _side_label(ax, x, y, text, color=GRAY_D, fontsize=7.5, ha="center"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=fontsize,
            color=color, fontstyle="italic", zorder=5)


def main():
    fig, ax = plt.subplots(figsize=(10, 13))
    ax.set_xlim(-1, 11)
    ax.set_ylim(-0.3, 14)
    ax.set_aspect("equal")
    ax.axis("off")

    # Column centers
    CX = 3.5       # main flow
    GX = 8.2       # gateway panel

    bw = 3.2       # box width
    bh = 0.6       # box height
    gap = 0.35     # arrow gap between boxes

    # ══════════════════════════════════════════════════════════════════════
    #  TITLE
    # ══════════════════════════════════════════════════════════════════════
    ax.text(5.0, 13.7,
            "DiCWO — Distributed Calibration-Weighted Orchestration",
            fontsize=13, fontweight="bold", color=BLACK, ha="center")
    ax.text(5.0, 13.35,
            "Iteration-level orchestration loop",
            fontsize=9.5, color=GRAY_D, ha="center")

    # ══════════════════════════════════════════════════════════════════════
    #  PHASE 0: INITIALIZATION  (above loop)
    # ══════════════════════════════════════════════════════════════════════
    y = 12.7
    _box(ax, CX, y, bw + 0.4, bh + 0.05,
         "Initialization", "5 agents  |  Consensus task decomposition (Borda count)",
         fc=BLUE_L, ec=BLUE, fontsize=10)

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.05)

    # ══════════════════════════════════════════════════════════════════════
    #  MAIN LOOP background
    # ══════════════════════════════════════════════════════════════════════
    loop_top = 12.05
    loop_bot = 1.65
    loop_bg = FancyBboxPatch(
        (CX - bw / 2 - 0.6, loop_bot - 0.15),
        bw + 1.2, loop_top - loop_bot + 0.3,
        boxstyle="round,pad=0.12",
        facecolor=GRAY, edgecolor=GRAY_M,
        linewidth=1.0, linestyle=(0, (5, 3)), alpha=0.6, zorder=0,
    )
    ax.add_patch(loop_bg)
    ax.text(CX - bw / 2 - 0.3, loop_top + 0.05,
            "for  t = 1 ... T_max",
            fontsize=8, color=GRAY_D, fontstyle="italic")

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 1: BEACON BROADCASTING
    # ══════════════════════════════════════════════════════════════════════
    y = 11.7
    _box(ax, CX, y, bw, bh,
         "Beacon Broadcasting",
         "Capabilities, calibration score, evidence")
    _side_label(ax, CX + bw / 2 + 0.15, y,
                "B_i(t)", ha="left", fontsize=8, color=BLUE)

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.05)

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 2: BIDDING
    # ══════════════════════════════════════════════════════════════════════
    y = 10.7
    _box(ax, CX, y, bw, bh,
         "Calibration-Weighted Bidding",
         "bid = a*fit - b*cal_pen - g*cost + d*div")

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.05)

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 3: COALITION + CONSENSUS
    # ══════════════════════════════════════════════════════════════════════
    y = 9.7
    _box(ax, CX, y, bw, bh,
         "Coalition Formation + Consensus",
         "Vote on (team A, topology G, protocol p)")

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.05)

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 4: ESCALATION FLOOR
    # ══════════════════════════════════════════════════════════════════════
    y = 8.7
    _box(ax, CX, y, bw, bh,
         "Escalation Floor Enforcement",
         "p = max( consensus, floor_k )",
         ec=TEAL)
    _side_label(ax, CX + bw / 2 + 0.15, y,
                "solo < audit\n< debate\n< tool_verified",
                ha="left", fontsize=7, color=TEAL)

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.05)

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 5: EXECUTION
    # ══════════════════════════════════════════════════════════════════════
    y = 7.7
    _box(ax, CX, y, bw, bh,
         "Protocol Execution",
         "solo  |  audit  |  debate  |  parallel",
         ec=BLUE)

    # Arrow to confidence gateway
    _arrow(ax, CX + bw / 2 + 0.05, y, GX - 1.55, y,
           color=BLUE, lw=1.0)
    _side_label(ax, (CX + bw / 2 + GX - 1.55) / 2, y + 0.2,
                "each call gated", color=BLUE, fontsize=7.5)

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.05)

    # ══════════════════════════════════════════════════════════════════════
    #  CONFIDENCE GATEWAY (right panel)
    # ══════════════════════════════════════════════════════════════════════
    gw_top = 8.85
    gw_bot = 5.55
    gw_w = 3.0
    gw_bg = FancyBboxPatch(
        (GX - gw_w / 2 - 0.15, gw_bot - 0.15),
        gw_w + 0.3, gw_top - gw_bot + 0.3,
        boxstyle="round,pad=0.1",
        facecolor="#FAFBFC", edgecolor=GRAY_M,
        linewidth=1.0, linestyle=(0, (4, 3)), alpha=0.7, zorder=0,
    )
    ax.add_patch(gw_bg)
    ax.text(GX, gw_top + 0.05, "Confidence Gateway",
            fontsize=9, fontweight="bold", color=GRAY_D, ha="center")

    # Self-assessment
    gy = 8.5
    _box(ax, GX, gy, 2.6, 0.45,
         "Self-Assessment", "confidence score 0-100",
         fc=WHITE, ec=GRAY_D, lw=1.0, fontsize=8.5)
    _varrow(ax, GX, gy - 0.25, gy - 0.55, color=GRAY_D, lw=1.0)

    # Three tiers
    gy = 7.7
    _box(ax, GX, gy, 2.6, 0.4,
         ">= 85 %:  PROCEED", None,
         fc="#E6F4EA", ec=GREEN, lw=1.0, fontsize=8, title_weight="normal")

    _varrow(ax, GX, gy - 0.23, gy - 0.5, color=GRAY_D, lw=0.8)

    gy = 7.0
    _box(ax, GX, gy, 2.6, 0.4,
         "50-84 %:  REFLECT", None,
         fc="#FEF3E2", ec=AMBER, lw=1.0, fontsize=8, title_weight="normal")
    # Reflexion loop
    _arrow(ax, GX + 1.35, 7.0, GX + 1.35, 8.35,
           color=AMBER, lw=0.9, connstyle="arc3,rad=-0.6")
    _side_label(ax, GX + 1.75, 7.7, "retry\n(max 2)", color=AMBER, fontsize=6.5)

    _varrow(ax, GX, gy - 0.23, gy - 0.5, color=GRAY_D, lw=0.8)

    gy = 6.3
    _box(ax, GX, gy, 2.6, 0.4,
         "< 50 %:  INTERVENE", None,
         fc="#FDE8E8", ec=RED_SOFT, lw=1.0, fontsize=8, title_weight="normal")
    _side_label(ax, GX, 5.95, "structured RFI, no blind retry",
                color=RED_SOFT, fontsize=7)

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 6: CHECKPOINT
    # ══════════════════════════════════════════════════════════════════════
    y = 6.7
    _box(ax, CX, y, bw, bh,
         "Checkpoint Evaluation",
         "disagreement, uncertainty, verifiability, risk",
         ec=BLUE)

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.15)

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 7: POLICY DECISION (diamond)
    # ══════════════════════════════════════════════════════════════════════
    dy = 5.55
    dw, dh = 1.1, 0.6
    diamond = plt.Polygon([
        (CX, dy + dh), (CX + dw, dy), (CX, dy - dh), (CX - dw, dy),
    ], closed=True, facecolor=WHITE, edgecolor=BLUE, linewidth=1.4, zorder=3)
    ax.add_patch(diamond)
    ax.text(CX, dy + 0.05, "Policy", ha="center", va="center",
            fontsize=9, fontweight="bold", color=BLACK, zorder=4)
    ax.text(CX, dy - 0.18, "pi(Gamma_t)", ha="center", va="center",
            fontsize=7.5, color=GRAY_D, zorder=4)

    # ── CONTINUE (left, loops back up) ────────────────────────────────────
    cont_x = CX - dw - 0.15
    _arrow(ax, CX - dw, dy, cont_x, dy, color=BLUE, lw=1.3)

    # Vertical line up
    ax.plot([cont_x, cont_x], [dy, loop_top - 0.1],
            color=BLUE, lw=1.3, zorder=2)
    # Arrow into top of loop
    _arrow(ax, cont_x, loop_top - 0.15, CX - bw / 2 + 0.1, 11.7,
           color=BLUE, lw=1.3, connstyle="arc3,rad=0.15")

    ax.text(cont_x - 0.15, (dy + loop_top) / 2, "CONTINUE",
            fontsize=8, fontweight="bold", color=BLUE,
            rotation=90, ha="center", va="center")

    # ── REWIRE (right) ────────────────────────────────────────────────────
    rew_x = CX + dw + 0.15
    _arrow(ax, CX + dw, dy, rew_x + 0.3, dy, color=RED_SOFT, lw=1.3)

    _box(ax, rew_x + 1.8, dy, 2.0, 0.5,
         "REWIRE", "escalate floor, re-enter",
         fc=WHITE, ec=RED_SOFT, lw=1.2, fontsize=8.5)

    # Arrow from REWIRE up to escalation floor step
    _arrow(ax, rew_x + 2.8, dy + 0.25, rew_x + 2.8, 8.7,
           color=RED_SOFT, lw=1.0, connstyle="arc3,rad=0")
    _arrow(ax, rew_x + 2.8, 8.7, CX + bw / 2 + 0.05, 8.7,
           color=RED_SOFT, lw=1.0)

    # ── STOP (down) ───────────────────────────────────────────────────────
    _varrow(ax, CX, dy - dh - 0.05, dy - dh - gap - 0.3, color=BLACK, lw=1.5)
    ax.text(CX + 0.3, dy - dh - 0.2, "STOP",
            fontsize=8, fontweight="bold", color=BLACK, ha="left")

    # ══════════════════════════════════════════════════════════════════════
    #  STEP 8: CALIBRATION UPDATE (small side note)
    # ══════════════════════════════════════════════════════════════════════
    _side_label(ax, CX + bw / 2 + 0.15, 6.2,
                "Update calibration,\nreputation, synergy",
                ha="left", fontsize=7, color=GRAY_M)

    # ══════════════════════════════════════════════════════════════════════
    #  AGENT SPAWNING (side note near checkpoint)
    # ══════════════════════════════════════════════════════════════════════
    _side_label(ax, CX - bw / 2 - 0.15, 6.7,
                "Coverage gap or\nfailure >= 2  -->  Spawn",
                ha="right", fontsize=7, color=GRAY_M)

    # ══════════════════════════════════════════════════════════════════════
    #  OUTPUT (below loop)
    # ══════════════════════════════════════════════════════════════════════
    y = 4.35
    _box(ax, CX, y, bw, bh,
         "Integration + Final Report", "SharedState artifacts",
         fc=BLUE_L, ec=BLUE, fontsize=9.5)

    _varrow(ax, CX, y - bh / 2 - 0.05, y - bh / 2 - gap - 0.05)

    y = 3.4
    _box(ax, CX, y, bw, bh,
         "LLM Judge Evaluation", "5 rubrics, per-criterion 1-5 scoring",
         fc=WHITE, ec=GRAY_D, lw=1.0, fontsize=9)

    # ══════════════════════════════════════════════════════════════════════
    #  ESCALATION LADDER (bottom-right, compact)
    # ══════════════════════════════════════════════════════════════════════
    lx = GX
    ly_top = 5.15
    ax.text(lx, ly_top + 0.25, "Protocol Escalation Ladder",
            fontsize=8, fontweight="bold", color=TEAL, ha="center")

    protocols = ["L0  solo", "L1  audit", "L2  debate", "L3  tool_verified"]
    shades = ["#D4EDDA", "#B8D8C7", "#8CBFAC", "#5EA690"]
    for i, (label, shade) in enumerate(zip(protocols, shades)):
        py = ly_top - i * 0.35
        rect = FancyBboxPatch(
            (lx - 1.1, py - 0.12), 2.2, 0.28,
            boxstyle="round,pad=0.04",
            facecolor=shade, edgecolor=TEAL, linewidth=0.6, zorder=3, alpha=0.85,
        )
        ax.add_patch(rect)
        tc = BLACK if i < 3 else WHITE
        ax.text(lx, py + 0.02, label, ha="center", va="center",
                fontsize=7.5, color=tc, zorder=4)

    # Arrow indicating direction
    _arrow(ax, lx + 1.25, ly_top, lx + 1.25, ly_top - 1.05,
           color=TEAL, lw=0.9, style="-|>")
    ax.text(lx + 1.45, ly_top - 0.5, "rigor",
            fontsize=7, color=TEAL, ha="left", va="center")

    # ══════════════════════════════════════════════════════════════════════
    #  AGENT POOL (bottom-right below ladder)
    # ══════════════════════════════════════════════════════════════════════
    ay = 3.4
    ax.text(lx, ay + 0.35, "Agent Pool", fontsize=8, fontweight="bold",
            color=GRAY_D, ha="center")
    agents = [
        "Market Analyst", "Frequency Expert",
        "Payload Expert", "Mission Analyst",
        "Study Manager",
    ]
    for i, name in enumerate(agents):
        col = i % 3
        row = i // 3
        px = lx - 1.2 + col * 1.2
        py = ay - row * 0.3
        rect = FancyBboxPatch(
            (px - 0.55, py - 0.1), 1.1, 0.24,
            boxstyle="round,pad=0.03",
            facecolor=BLUE_L, edgecolor=BLUE, linewidth=0.5, zorder=3,
        )
        ax.add_patch(rect)
        ax.text(px, py + 0.02, name, ha="center", va="center",
                fontsize=6, color=BLACK, zorder=4)

    # Spawned agent slots
    for i in range(2):
        px = lx - 0.6 + i * 1.2
        py = ay - 0.6
        rect = FancyBboxPatch(
            (px - 0.55, py - 0.1), 1.1, 0.24,
            boxstyle="round,pad=0.03",
            facecolor=WHITE, edgecolor=GRAY_M, linewidth=0.5,
            linestyle=(0, (3, 2)), zorder=3,
        )
        ax.add_patch(rect)
        ax.text(px, py + 0.02, f"Spawned {i+1}",
                ha="center", va="center",
                fontsize=6, color=GRAY_M, zorder=4, fontstyle="italic")
    ax.text(lx + 0.95, ay - 0.6, "(TTL, credentialed)",
            fontsize=5.5, color=GRAY_M, ha="left", va="center")

    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(f"figures/dicwo_architecture.{ext}")
    plt.close(fig)
    print("Saved figures/dicwo_architecture.png and .pdf")


if __name__ == "__main__":
    main()
