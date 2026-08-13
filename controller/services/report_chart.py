"""每日报告图表生成：堆叠柱状图（严重程度分布）+ 环形图（API 调用状态）。"""

import io
import os
import logging

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

# 严重程度排序与配色
SEVERITY_ORDER = ["CRITICAL", "ERROR", "WARNING", "INFO"]
SEVERITY_LABELS = {"CRITICAL": "严重", "ERROR": "错误", "WARNING": "警告", "INFO": "信息"}
SEVERITY_COLORS = {"CRITICAL": "#d32f2f", "ERROR": "#f57c00", "WARNING": "#fbc02d", "INFO": "#1976d2"}

_FONT_INIT = False


def _init_font():
    """注册 Noto Sans CJK 字体，使图表支持中文。"""
    global _FONT_INIT
    if _FONT_INIT:
        return

    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            font_manager.fontManager.addfont(fp)

    matplotlib.rcParams["font.family"] = "Noto Sans CJK SC"
    matplotlib.rcParams["axes.unicode_minus"] = False
    _FONT_INIT = True


def generate_charts(severity_counts_per_node, api_calls, success_calls, failed_calls):
    """生成图表，返回 {cid: bytes} 字典。

    Args:
        severity_counts_per_node: {node_id: {severity: count}} 严重程度统计
        api_calls: 总 API 调用数
        success_calls: 成功调用数
        failed_calls: 失败调用数

    Returns:
        dict: {chart_severity: png_bytes, chart_api: png_bytes}，可能为空
    """
    charts = {}

    if severity_counts_per_node:
        try:
            buf = _build_severity_chart(severity_counts_per_node)
            charts["chart_severity"] = buf.getvalue()
            buf.close()
        except Exception as e:
            logger.warning(f"[Chart] Failed to generate severity chart: {e}")

    if api_calls > 0:
        try:
            buf = _build_api_chart(success_calls, failed_calls)
            charts["chart_api"] = buf.getvalue()
            buf.close()
        except Exception as e:
            logger.warning(f"[Chart] Failed to generate API chart: {e}")

    return charts


def _build_severity_chart(severity_counts_per_node):
    """严重程度分布堆叠柱状图。"""
    _init_font()

    nodes = sorted(severity_counts_per_node.keys())
    # 构建每个严重级别的数据列
    data = {}
    for sev in SEVERITY_ORDER:
        data[sev] = [severity_counts_per_node[n].get(sev, 0) for n in nodes]

    fig = Figure(figsize=(max(6, len(nodes) * 1.2), 4.5), dpi=100)
    ax = fig.add_subplot(111)

    x = range(len(nodes))
    bottom = [0] * len(nodes)

    for sev in SEVERITY_ORDER:
        vals = data[sev]
        if any(vals):
            ax.bar(
                x, vals, bottom=bottom,
                color=SEVERITY_COLORS[sev],
                label=f"{SEVERITY_LABELS[sev]} ({sev})",
                width=0.6,
                edgecolor="white",
                linewidth=0.5,
            )
            bottom = [b + v for b, v in zip(bottom, vals)]

    ax.set_xticks(x)
    ax.set_xticklabels(nodes, fontsize=9)
    ax.set_ylabel("分析次数", fontsize=10)
    ax.set_title("日志分析严重程度分布", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="upper right")
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()

    buf = io.BytesIO()
    FigureCanvasAgg(fig).print_png(buf)
    return buf


def _build_api_chart(success_calls, failed_calls):
    """API 调用状态环形图。"""
    _init_font()

    labels = ["成功", "失败"]
    values = [success_calls, failed_calls]
    colors = ["#4caf50", "#f44336"]
    explode = (0, 0.05) if failed_calls > 0 else (0, 0)

    fig = Figure(figsize=(4.5, 3.5), dpi=100)
    ax = fig.add_subplot(111)

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        explode=explode,
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.75,
        wedgeprops={"width": 0.4, "edgecolor": "white", "linewidth": 1.5},
    )
    for t in autotexts:
        t.set_fontsize(9)
    for t in texts:
        t.set_fontsize(10)

    # 环中心显示总数
    total = sum(values)
    ax.text(
        0, 0, f"总计\n{total}次",
        ha="center", va="center",
        fontsize=10, fontweight="bold",
    )

    ax.set_title("API 调用状态", fontsize=12, fontweight="bold")
    fig.tight_layout()

    buf = io.BytesIO()
    FigureCanvasAgg(fig).print_png(buf)
    return buf