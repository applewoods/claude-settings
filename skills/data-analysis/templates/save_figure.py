"""논문용 그림 저장: PDF(벡터, 글꼴 임베드) + PNG(300 dpi). 색 외에 선 모양·마커로도 구분."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Okabe–Ito 색맹 안전 팔레트 + 선 모양·마커를 같이 순환
OKABE_ITO = ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]
LINESTYLES = ["-", "--", ":", "-."]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]

plt.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42,  # 글꼴을 Type 42로 임베드(Type 3 회피)
    "font.size": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.spines.top": False, "axes.spines.right": False,
})


def style(i: int) -> dict:
    """i번째 계열의 color·linestyle·marker. ax.plot(x, y, **style(i))"""
    return {"color": OKABE_ITO[i % 8], "linestyle": LINESTYLES[i % 4], "marker": MARKERS[i % 8]}


def save_figure(fig, path_stem: str) -> None:
    """path_stem='results/run/figures/fig1' → fig1.pdf, fig1.png"""
    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    import numpy as np
    fig, ax = plt.subplots(figsize=(3.3, 2.4))  # 1단 칼럼 폭 약 3.3인치
    x = np.arange(1, 11)
    for i, name in enumerate(["baseline", "proposed"]):
        mean = 0.6 + 0.02 * x * (i + 1) ** 0.5
        ax.plot(x, mean, label=name, **style(i))
        ax.fill_between(x, mean - 0.02, mean + 0.02, color=OKABE_ITO[i], alpha=0.2)  # 데모용 임의 폭(실제로는 계산한 CI)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Validation F1")
    ax.legend(title="Demo (band is illustrative)")
    save_figure(fig, "figures/demo")
    print("saved figures/demo.pdf, figures/demo.png")
