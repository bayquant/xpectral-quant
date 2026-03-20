"""Script to generate the xpectral decomposition banner GIF."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec

# --- Config ---
N_FRAMES = 90
FPS = 18
OUT_PATH = "assets/xpectral_banner.gif"

BG      = "#FFFFFF"
BLUE    = "#4285F4"
RED     = "#EA4335"
YELLOW  = "#F9A825"
WHITE   = "#1A1A2E"
DIM     = "#D0D7DE"

# Signal components
X = np.linspace(0, 4 * np.pi, 400)
COMPONENTS = [
    {"freq": 1.0,  "amp": 0.45, "phase": 0.0,         "color": BLUE},
    {"freq": 2.3,  "amp": 0.28, "phase": np.pi / 3,   "color": RED},
    {"freq": 4.1,  "amp": 0.15, "phase": np.pi * 0.8, "color": YELLOW},
]

def signal(t, x):
    return sum(
        c["amp"] * np.sin(c["freq"] * x - t * c["freq"] * 0.9 + c["phase"])
        for c in COMPONENTS
    )

def component(c, t, x):
    return c["amp"] * np.sin(c["freq"] * x - t * c["freq"] * 0.9 + c["phase"])

# --- Layout ---
fig = plt.figure(figsize=(10, 4), facecolor=BG)
gs = GridSpec(
    4, 1, figure=fig,
    hspace=0.08,
    top=0.92, bottom=0.06, left=0.03, right=0.97,
    height_ratios=[2.2, 1, 1, 1],
)

axes = [fig.add_subplot(gs[i]) for i in range(4)]
for ax in axes:
    ax.set_facecolor(BG)
    ax.set_xlim(X[0], X[-1])
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.axhline(0, color=DIM, linewidth=0.6, zorder=0)

axes[0].set_ylim(-1.1, 1.1)
for ax, c in zip(axes[1:], COMPONENTS):
    ax.set_ylim(-0.55, 0.55)

# Initial lines
t0 = 0.0
line_combined, = axes[0].plot(X, signal(t0, X), color=WHITE, linewidth=1.6, zorder=2)

# Gradient fill under combined signal
fill_combined = axes[0].fill_between(
    X, signal(t0, X), 0,
    where=signal(t0, X) >= 0, color=WHITE, alpha=0.06, zorder=1
)

comp_lines = []
comp_fills = []
for ax, c in zip(axes[1:], COMPONENTS):
    y = component(c, t0, X)
    line, = ax.plot(X, y, color=c["color"], linewidth=1.4, zorder=2)
    fill = ax.fill_between(X, y, 0, where=y >= 0, color=c["color"], alpha=0.15, zorder=1)
    comp_lines.append(line)
    comp_fills.append(fill)

# Divider lines between panels
for ax in axes[:-1]:
    ax.axhline(ax.get_ylim()[0], color=DIM, linewidth=0.5)

def animate(frame):
    t = frame / FPS

    # Combined
    y_combined = signal(t, X)
    line_combined.set_ydata(y_combined)

    # Remove and redraw fills (fill_between can't be updated in-place)
    for col in list(axes[0].collections):
        col.remove()
    axes[0].fill_between(X, y_combined, 0, where=y_combined >= 0,
                         color=WHITE, alpha=0.06, zorder=1)
    axes[0].axhline(0, color=DIM, linewidth=0.6, zorder=0)

    for i, (ax, c, line) in enumerate(zip(axes[1:], COMPONENTS, comp_lines)):
        y = component(c, t, X)
        line.set_ydata(y)
        for col in list(ax.collections):
            col.remove()
        ax.fill_between(X, y, 0, where=y >= 0, color=c["color"], alpha=0.15, zorder=1)
        ax.axhline(0, color=DIM, linewidth=0.6, zorder=0)

    return [line_combined] + comp_lines

ani = animation.FuncAnimation(
    fig, animate, frames=N_FRAMES, interval=1000 / FPS, blit=False
)

ani.save(OUT_PATH, writer="pillow", fps=FPS, dpi=110)
print(f"Saved {OUT_PATH}")
