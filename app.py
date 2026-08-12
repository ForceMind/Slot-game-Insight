from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_utils import (
    DIMENSION_LABELS,
    dimension_summary,
    discover_data_files,
    filter_game_data,
    game_name_from_filename,
    player_summary,
    read_game_data,
)
from slot_metrics import (
    advanced_metrics,
    build_spin_table,
    cumulative_bet_tier_summary,
    filter_spin_data,
    game_summary,
    large_player_summary,
    streak_table,
    time_summary,
)
from table_utils import localized_grid


PROJECT_DIR = Path(__file__).resolve().parent
PLOT_CONFIG = {
    "displaylogo": False,
    "displayModeBar": False,
    "scrollZoom": True,
    "locale": "zh-CN",
}
GRANULARITY_PREFIX = {"小时": "每小时", "天": "每天", "周": "每周"}

st.set_page_config(
    page_title="SlotInsight 游戏数据面板",
    page_icon="🎰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container {padding-top: 1.25rem; padding-bottom: 2rem;}
    [data-testid="stSidebar"] {border-right: 1px solid #e5e7eb;}
    [data-testid="stMetric"] {
        border-top: 2px solid #2563eb;
        padding: 0.72rem 0.8rem 0.62rem;
        background: #f8fafc;
        min-width: 0;
    }
    [data-testid="stMetricLabel"] {font-weight: 600;}
    [data-testid="stMetricValue"] {
        font-size: 1.42rem;
        line-height: 1.2;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .source-note {color: #64748b; font-size: 0.86rem; margin-top: -0.45rem;}
    .stPlotlyChart {border-top: 1px solid #f1f5f9;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_local_bundle(path_text: str, modified_ns: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    del modified_ns
    events = read_game_data(Path(path_text))
    return events, build_spin_table(events)


@st.cache_data(show_spinner=False)
def load_uploaded_bundle(content: bytes, filename: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    del filename
    events = read_game_data(BytesIO(content))
    return events, build_spin_table(events)


@st.cache_data(show_spinner=False)
def load_cross_game_bundle(
    file_entries: tuple[tuple[str, str, int], ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spin_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    for game, path_text, modified_ns in file_entries:
        events, spins = load_local_bundle(path_text, modified_ns)
        events = events.assign(game=game)
        spins = spins.assign(game=game)
        spin_frames.append(spins)
        rows.append({"游戏": game, **game_summary(spins, events)})
    all_spins = pd.concat(spin_frames, ignore_index=True)
    profiles, per_game = large_player_summary(all_spins)
    return all_spins, pd.DataFrame(rows), profiles, per_game


def compact_number(value: float, digits: int = 2) -> str:
    value = float(value)
    absolute = abs(value)
    if absolute >= 100_000_000:
        return f"{value / 100_000_000:.{digits}f}亿"
    if absolute >= 10_000:
        return f"{value / 10_000:.{digits}f}万"
    if absolute >= 1_000:
        return f"{value:,.0f}"
    if absolute >= 100:
        return f"{value:,.1f}"
    return f"{value:,.2f}"


def metric(
    container: object,
    label: str,
    value: float,
    *,
    kind: str = "amount",
    help_text: str | None = None,
) -> None:
    if kind == "percent":
        shown = f"{value:.2f}%"
        full = f"{value:,.4f}%"
    elif kind == "multiple":
        shown = f"{value:.2f}x"
        full = f"{value:,.4f}x"
    elif kind == "count":
        shown = f"{value:,.0f}" if abs(value) < 10_000 else compact_number(value, 1)
        full = f"{value:,.0f}"
    elif kind == "decimal":
        shown = compact_number(value, 2)
        full = f"{value:,.4f}"
    else:
        shown = compact_number(value, 2)
        full = f"{value:,.2f}"
    container.metric(label, shown, help=help_text or f"完整值：{full}")


def time_axis_figure(figure: go.Figure) -> go.Figure:
    figure.update_xaxes(
        rangeslider_visible=True,
        tickformat="%m月%d日",
        hoverformat="%Y年%m月%d日 %H:%M",
    )
    figure.update_layout(dragmode="zoom")
    return figure


def compact_numeric_axis(
    figure: go.Figure,
    axis: str,
    values: object,
    *,
    include_zero: bool = True,
) -> go.Figure:
    numeric = pd.to_numeric(pd.Series(values).explode(), errors="coerce").dropna()
    if numeric.empty:
        return figure
    lower = float(numeric.min())
    upper = float(numeric.max())
    if include_zero:
        lower = min(lower, 0.0)
        upper = max(upper, 0.0)
    if lower == upper:
        lower = min(0.0, lower)
        upper = upper if upper else 1.0
    largest = max(abs(lower), abs(upper))
    updater = figure.update_xaxes if axis == "x" else figure.update_yaxes
    if largest < 10_000:
        updater(tickformat=",.0f", separatethousands=True)
        return figure
    tick_values = np.linspace(lower, upper, 5)
    updater(
        tickmode="array",
        tickvals=tick_values.tolist(),
        ticktext=[compact_number(value, 1) for value in tick_values],
    )
    return figure


def load_cross_game_data(
    file_map: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    file_entries = tuple(
        (game, str(path), path.stat().st_mtime_ns) for game, path in file_map.items()
    )
    with st.spinner("正在汇总全部游戏，首次加载需要一些时间…"):
        all_spins, comparison, _, _ = load_cross_game_bundle(file_entries)
    return all_spins, comparison


def render_cumulative_bet_pies(spins: pd.DataFrame, *, key_prefix: str) -> None:
    tiers = cumulative_bet_tier_summary(spins)
    players = tiers.rename(columns={"tier": "累计下注档位", "players": "玩家数"})
    turnover = tiers.rename(columns={"tier": "累计下注档位", "turnover": "流水"})
    left, right = st.columns(2)
    with left:
        figure = px.pie(
            players,
            names="累计下注档位",
            values="玩家数",
            title="各累计下注档位的玩家构成",
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        figure.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>玩家数：%{value:,.0f}<br>占比：%{percent}<extra></extra>",
        )
        figure.update_layout(legend_title_text="累计下注档位")
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG, key=f"{key_prefix}-players")
    with right:
        figure = px.pie(
            turnover,
            names="累计下注档位",
            values="流水",
            title="各累计下注档位的流水贡献",
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        figure.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>流水：%{value:,.2f}<br>占比：%{percent}<extra></extra>",
        )
        figure.update_layout(legend_title_text="累计下注档位")
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG, key=f"{key_prefix}-turnover")


def render_game_comparison(file_map: dict[str, Path]) -> None:
    st.title("全游戏经营总览")
    st.caption(
        f"横向比较数据文件夹中的 {len(file_map)} 款游戏；资金指标按原始事件计算，"
        "局次、中奖率和波动指标按可重建完整局次计算。"
    )

    all_spins, comparison = load_cross_game_data(file_map)
    totals = {
        "turnover": comparison["turnover"].sum(),
        "payout": comparison["payout"].sum(),
        "ggr": comparison["ggr"].sum(),
        "spins": comparison["spins"].sum(),
        "active_users": comparison["active_users"].sum(),
    }
    combined_rtp = totals["payout"] / totals["turnover"] * 100 if totals["turnover"] else 0
    cols = st.columns(6)
    metric(cols[0], "游戏数", len(comparison), kind="count")
    metric(cols[1], "合计流水", totals["turnover"])
    metric(cols[2], "合计派彩", totals["payout"])
    metric(cols[3], "合计 GGR", totals["ggr"])
    metric(cols[4], "加权 RTP", combined_rtp, kind="percent")
    metric(cols[5], "合计局数", totals["spins"], kind="count")

    left, right = st.columns([1.35, 1])
    with left:
        finance = comparison.melt(
            id_vars="游戏",
            value_vars=["turnover", "payout", "ggr"],
            var_name="指标",
            value_name="金币",
        )
        finance["指标"] = finance["指标"].map(
            {"turnover": "流水", "payout": "派彩", "ggr": "GGR"}
        )
        figure = px.bar(
            finance,
            x="游戏",
            y="金币",
            color="指标",
            barmode="group",
            title="各游戏资金规模",
            color_discrete_map={"流水": "#2563eb", "派彩": "#d97706", "GGR": "#059669"},
        )
        figure.update_layout(legend_title_text="")
        compact_numeric_axis(figure, "y", finance["金币"])
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)
    with right:
        rates = comparison.melt(
            id_vars="游戏",
            value_vars=["rtp", "hold", "hit_rate", "profitable_player_rate"],
            var_name="指标",
            value_name="百分比",
        )
        rates["指标"] = rates["指标"].map(
            {
                "rtp": "RTP",
                "hold": "Hold",
                "hit_rate": "中奖率",
                "profitable_player_rate": "玩家盈利率",
            }
        )
        figure = px.bar(
            rates,
            x="游戏",
            y="百分比",
            color="指标",
            barmode="group",
            title="返还与中奖横向比较",
        )
        figure.update_layout(legend_title_text="")
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)

    st.subheader("累计下注分层")
    st.caption("按玩家在全部游戏中的累计下注划分互斥档位，同一玩家只计入一个档位。")
    render_cumulative_bet_pies(all_spins, key_prefix="all-games-tier")

    st.subheader("Slot 游戏参数对比")
    st.caption(
        "每个参数单独使用自己的单位横向比较。Hold = GGR ÷ 总流水 × 100% = 100% - RTP；"
        "它表示游戏留存率，不等于扣除运营成本后的利润率。"
    )
    game_choices = st.multiselect(
        "参与对比的游戏",
        options=comparison["游戏"].tolist(),
        default=comparison["游戏"].tolist(),
        key="comparison-games",
    )
    metric_options = {key: label for key, label, _, _ in SLOT_METRIC_DEFINITIONS}
    selected_metrics = st.multiselect(
        "选择 3 至 6 个参数",
        options=list(metric_options),
        default=["rtp", "hold", "hit_rate", "return_volatility"],
        format_func=lambda key: metric_options[key],
        max_selections=6,
        key="comparison-metrics",
    )
    if len(selected_metrics) < 3:
        st.info("请至少选择 3 个参数进行对比。")
    elif not game_choices:
        st.info("请至少选择一款游戏。")
    else:
        selected_comparison = comparison.loc[comparison["游戏"].isin(game_choices)]
        for start in range(0, len(selected_metrics), 2):
            columns = st.columns(2)
            for column, key in zip(columns, selected_metrics[start : start + 2]):
                label, kind, help_text = SLOT_METRIC_META[key]
                chart_data = selected_comparison[["游戏", key]].rename(columns={key: label})
                with column:
                    figure = px.bar(
                        chart_data,
                        x="游戏",
                        y=label,
                        color="游戏",
                        title=f"{label}对比",
                        text_auto=".2f",
                    )
                    figure.update_layout(showlegend=False)
                    compact_numeric_axis(figure, "y", chart_data[label])
                    figure.update_traces(
                        hovertemplate=f"<b>%{{x}}</b><br>{label}：%{{y:,.4f}}<extra></extra>"
                    )
                    st.plotly_chart(
                        figure,
                        use_container_width=True,
                        config=PLOT_CONFIG,
                        key=f"comparison-{key}",
                    )
                    st.caption(help_text)

    left, right = st.columns(2)
    with left:
        scatter_data = comparison.rename(
            columns={
                "average_bet": "平均下注",
                "return_volatility": "返还倍率标准差",
                "spins": "局数",
                "rtp": "RTP",
                "hit_rate": "中奖率",
                "max_loss_streak": "最大连输",
            }
        )
        figure = px.scatter(
            scatter_data,
            x="平均下注",
            y="返还倍率标准差",
            size="局数",
            color="游戏",
            hover_data=["RTP", "中奖率", "最大连输"],
            title="平均下注与返还波动性",
        )
        compact_numeric_axis(figure, "x", scatter_data["平均下注"])
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)
    with right:
        activity_data = comparison.rename(
            columns={"active_users": "活跃玩家", "spins": "局数"}
        ).sort_values("活跃玩家")
        figure = px.bar(
            activity_data,
            x="活跃玩家",
            y="游戏",
            orientation="h",
            hover_data=["局数"],
            title="活跃玩家与局数",
            color_discrete_sequence=["#334155"],
        )
        compact_numeric_axis(figure, "x", activity_data["活跃玩家"])
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)

    metric_column_labels = {
        key: f"{label} (%)" if kind == "percent" else label
        for key, label, kind, _ in SLOT_METRIC_DEFINITIONS
    }
    display = comparison.rename(
        columns={
            **metric_column_labels,
            "active_users": "活跃玩家",
            "spins": "局数",
            "turnover": "流水",
            "payout": "派彩",
            "ggr": "GGR",
        }
    )
    percent_columns = tuple(
        f"{label} (%)"
        for _, label, kind, _ in SLOT_METRIC_DEFINITIONS
        if kind == "percent"
    )
    localized_grid(
        display,
        key="game-comparison-grid",
        height=350,
        page_size=10,
        percent_columns=percent_columns,
    )


def observed_next_day_retention(events: pd.DataFrame) -> float:
    dated = events.assign(date=events["create_date"].dt.normalize())
    users_by_date = dated.groupby("date")["user_id"].agg(lambda values: set(values))
    rates: list[float] = []
    for date, users in users_by_date.items():
        next_users = users_by_date.get(date + pd.Timedelta(days=1))
        if next_users is not None and users:
            rates.append(len(users.intersection(next_users)) / len(users) * 100)
    return float(np.mean(rates)) if rates else 0.0


def render_operating_overview(events: pd.DataFrame, full_events: pd.DataFrame, spins: pd.DataFrame) -> None:
    summary = game_summary(spins, events)
    cols = st.columns(6)
    metric(cols[0], "总流水", summary["turnover"])
    metric(cols[1], "总派彩", summary["payout"])
    metric(cols[2], "GGR", summary["ggr"])
    metric(cols[3], "RTP", summary["rtp"], kind="percent")
    metric(cols[4], "下注局数", summary["spins"], kind="count")
    metric(cols[5], "中奖率", summary["hit_rate"], kind="percent")

    daily = time_summary(spins, "天")
    total_users = events["user_id"].nunique()
    avg_dau = daily["active_users"].mean() if not daily.empty else 0
    first_seen = full_events.groupby("user_id")["create_date"].min()
    selected_users = pd.Index(events["user_id"].unique())
    selected_first_seen = first_seen.reindex(selected_users).dropna()
    new_users = int(
        selected_first_seen.dt.normalize()
        .between(events["create_date"].min().normalize(), events["create_date"].max().normalize())
        .sum()
    )

    st.subheader("运营健康度")
    cols = st.columns(5)
    metric(cols[0], "活跃玩家", total_users, kind="count")
    metric(cols[1], "平均日活", avg_dau, kind="count")
    metric(cols[2], "观察期新增", new_users, kind="count")
    metric(cols[3], "次日留存", observed_next_day_retention(events), kind="percent")
    metric(cols[4], "人均局数", summary["spins"] / total_users if total_users else 0, kind="decimal")

    left, right = st.columns([1.55, 1])
    with left:
        finance = daily.melt(
            id_vars="period",
            value_vars=["turnover", "payout", "ggr"],
            var_name="指标",
            value_name="金币",
        )
        finance["指标"] = finance["指标"].map(
            {"turnover": "流水", "payout": "派彩", "ggr": "GGR"}
        )
        figure = px.line(
            finance,
            x="period",
            y="金币",
            color="指标",
            markers=True,
            title="每日资金趋势",
            labels={"period": "日期"},
            color_discrete_map={"流水": "#2563eb", "派彩": "#d97706", "GGR": "#059669"},
        )
        figure.update_layout(legend_title_text="", hovermode="x unified")
        compact_numeric_axis(figure, "y", finance["金币"])
        st.plotly_chart(time_axis_figure(figure), use_container_width=True, config=PLOT_CONFIG)
    with right:
        figure = px.bar(
            daily,
            x="period",
            y="active_users",
            title="每日活跃玩家",
            labels={"period": "日期", "active_users": "活跃玩家"},
            color_discrete_sequence=["#334155"],
        )
        compact_numeric_axis(figure, "y", daily["active_users"])
        st.plotly_chart(time_axis_figure(figure), use_container_width=True, config=PLOT_CONFIG)

    st.subheader("累计下注分层")
    st.caption("各档位互不重叠，同一玩家只计入一个累计下注档位。")
    render_cumulative_bet_pies(spins, key_prefix="single-game-tier")


def render_audience(events: pd.DataFrame) -> None:
    st.subheader("人群结构")
    dimension = st.segmented_control(
        "分析维度",
        options=list(DIMENSION_LABELS),
        format_func=lambda value: DIMENSION_LABELS[value],
        default="region",
        selection_mode="single",
    ) or "region"
    summary = dimension_summary(events, dimension)
    top_summary = summary.head(20)

    left, right = st.columns([1.45, 1])
    with left:
        figure = px.bar(
            top_summary.sort_values("turnover"),
            x="turnover",
            y=dimension,
            orientation="h",
            color="rtp",
            color_continuous_scale="RdYlGn_r",
            title=f"{DIMENSION_LABELS[dimension]}流水前 20 名",
            labels={dimension: DIMENSION_LABELS[dimension], "turnover": "流水", "rtp": "RTP（%）"},
        )
        compact_numeric_axis(figure, "x", top_summary["turnover"])
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)
    with right:
        scatter_summary = top_summary.rename(
            columns={
                "active_users": "活跃玩家",
                "rtp": "RTP（%）",
                "turnover": "流水",
                "ggr": "GGR",
                "bets": "下注局数",
            }
        )
        figure = px.scatter(
            scatter_summary,
            x="活跃玩家",
            y="RTP（%）",
            size="流水",
            color=dimension,
            hover_data=["流水", "GGR", "下注局数"],
            title="规模与 RTP",
            labels={dimension: DIMENSION_LABELS[dimension]},
        )
        figure.update_layout(showlegend=False)
        compact_numeric_axis(figure, "x", scatter_summary["活跃玩家"])
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)

    display = summary.rename(
        columns={
            dimension: DIMENSION_LABELS[dimension],
            "active_users": "活跃玩家",
            "bets": "下注局数",
            "turnover": "流水",
            "payout": "派彩",
            "ggr": "GGR",
            "rtp": "RTP (%)",
        }
    )
    localized_grid(display, key=f"audience-{dimension}", percent_columns=("RTP (%)",))


SLOT_METRIC_DEFINITIONS = (
    ("rtp", "RTP", "percent", "派彩 / 流水"),
    (
        "hold",
        "Hold",
        "percent",
        "GGR ÷ 总流水 × 100% = 100% - RTP，表示游戏留存率，不是扣除运营成本后的利润率",
    ),
    ("hit_rate", "中奖局率", "percent", "存在中出的局次占比"),
    ("zero_win_rate", "空奖局率", "percent", "没有任何中出的局次占比"),
    ("average_bet", "平均下注", "amount", "单局平均下注额"),
    ("median_bet", "下注中位数", "amount", "单局下注金额中位数"),
    ("bet_cv", "下注变异系数", "decimal", "下注标准差 / 平均下注"),
    ("net_std", "净赢分标准差", "amount", "单局玩家净赢分的标准差"),
    ("return_volatility", "返还波动性", "decimal", "单局返还倍率标准差"),
    ("expected_ggr_per_spin", "每局期望 GGR", "amount", "总 GGR / 局数"),
    ("max_spin_win", "最大单局赢分", "amount", "玩家单局最大净赢分"),
    ("max_spin_loss", "最大单局亏损", "amount", "玩家单局最大净亏损"),
    ("p95_multiplier", "95 分位返还倍率", "multiple", "95% 局次不超过该返还倍率"),
    ("big_win_rate", "10 倍大奖率", "percent", "返还倍率不低于 10 倍的局次占比"),
    ("super_win_rate", "50 倍超级大奖率", "percent", "返还倍率不低于 50 倍的局次占比"),
    ("max_win_streak", "最大连赢", "count", "单玩家连续净盈利局次最大值"),
    ("max_loss_streak", "最大连输", "count", "单玩家连续净亏损局次最大值"),
    ("avg_win_streak", "平均连赢", "decimal", "所有连续盈利段的平均长度"),
    ("avg_loss_streak", "平均连输", "decimal", "所有连续亏损段的平均长度"),
    ("top_turnover_concentration", "前 1% 玩家流水占比", "percent", "头部 1% 玩家贡献的流水占比"),
    ("top_payout_concentration", "前 1% 玩家派彩占比", "percent", "头部 1% 玩家获得的派彩占比"),
    ("profitable_player_rate", "玩家盈利比例", "percent", "观察期净盈利玩家占比"),
    ("spins_per_player", "人均局数", "decimal", "总局数 / 活跃玩家"),
)
SLOT_METRIC_META = {
    key: (label, kind, help_text)
    for key, label, kind, help_text in SLOT_METRIC_DEFINITIONS
}


def render_spin_analysis(spins: pd.DataFrame) -> None:
    st.subheader("时间曲线")
    st.caption("局次口径：一次下注开启一局，下一次下注前同一玩家的中出归入该局；导出窗口开头无法归属的中出不纳入局次指标。")
    min_date = spins["spin_time"].min().date()
    max_date = spins["spin_time"].max().date()
    control_left, control_right = st.columns([1.4, 1])
    with control_left:
        curve_range = st.date_input(
            "曲线时间范围",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="spin-curve-range",
        )
    with control_right:
        granularity = st.segmented_control(
            "时间粒度",
            options=["小时", "天", "周"],
            default="天",
            selection_mode="single",
            key="spin-granularity",
        ) or "天"

    curve_spins = filter_spin_data(spins, curve_range)
    trend = time_summary(curve_spins, granularity)
    if trend.empty:
        st.warning("当前曲线时间范围没有局次数据。")
        return

    finance = trend.melt(
        id_vars="period",
        value_vars=["turnover", "payout", "ggr"],
        var_name="指标",
        value_name="金币",
    )
    finance["指标"] = finance["指标"].map(
        {"turnover": "流水", "payout": "派彩", "ggr": "GGR"}
    )
    time_prefix = GRANULARITY_PREFIX[granularity]
    figure = px.line(
        finance,
        x="period",
        y="金币",
        color="指标",
        markers=True,
        title=f"{time_prefix}资金曲线",
        labels={"period": "时间"},
        color_discrete_map={"流水": "#2563eb", "派彩": "#d97706", "GGR": "#059669"},
    )
    figure.update_layout(legend_title_text="", hovermode="x unified")
    compact_numeric_axis(figure, "y", finance["金币"])
    st.plotly_chart(time_axis_figure(figure), use_container_width=True, config=PLOT_CONFIG)

    left, right = st.columns(2)
    with left:
        rates = trend.melt(
            id_vars="period",
            value_vars=["rtp", "hit_rate"],
            var_name="指标",
            value_name="百分比",
        )
        rates["指标"] = rates["指标"].map({"rtp": "RTP", "hit_rate": "中奖率"})
        figure = px.line(
            rates,
            x="period",
            y="百分比",
            color="指标",
            markers=True,
            title=f"{time_prefix} RTP 与中奖率",
            labels={"period": "时间"},
        )
        figure.update_layout(legend_title_text="", hovermode="x unified")
        compact_numeric_axis(figure, "y", rates["百分比"])
        st.plotly_chart(time_axis_figure(figure), use_container_width=True, config=PLOT_CONFIG)
    with right:
        activity = trend.melt(
            id_vars="period",
            value_vars=["spins", "active_users"],
            var_name="指标",
            value_name="数量",
        )
        activity["指标"] = activity["指标"].map({"spins": "局数", "active_users": "活跃玩家"})
        figure = px.line(
            activity,
            x="period",
            y="数量",
            color="指标",
            markers=True,
            title=f"{time_prefix}活跃玩家与局数",
            labels={"period": "时间"},
        )
        figure.update_layout(legend_title_text="", hovermode="x unified")
        compact_numeric_axis(figure, "y", activity["数量"])
        st.plotly_chart(time_axis_figure(figure), use_container_width=True, config=PLOT_CONFIG)

    st.subheader("Slot 游戏参数")
    metrics = advanced_metrics(curve_spins)
    for start in range(0, len(SLOT_METRIC_DEFINITIONS), 5):
        definitions = SLOT_METRIC_DEFINITIONS[start : start + 5]
        cols = st.columns(len(definitions))
        for column, (key, label, kind, help_text) in zip(cols, definitions):
            metric(column, label, metrics[key], kind=kind, help_text=help_text)

    st.subheader("分布与连赢连输")
    left, right = st.columns(2)
    with left:
        capped = curve_spins.loc[
            curve_spins["return_multiple"].le(curve_spins["return_multiple"].quantile(0.99))
        ]
        figure = px.histogram(
            capped,
            x="return_multiple",
            nbins=60,
            title="返还倍率分布（截断最高 1%）",
            labels={"return_multiple": "返还倍率", "count": "局数"},
            color_discrete_sequence=["#2563eb"],
        )
        figure.update_yaxes(title_text="局数", tickformat=",.0f", separatethousands=True)
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)
    with right:
        runs = streak_table(curve_spins)
        runs = runs.loc[runs["outcome"].isin(["玩家赢", "玩家输"])]
        figure = px.histogram(
            runs,
            x="length",
            color="outcome",
            barmode="group",
            nbins=min(50, max(10, int(runs["length"].max()) if not runs.empty else 10)),
            title="连赢连输长度分布",
            labels={"length": "连续局数", "count": "连续段数量", "outcome": "结果"},
            color_discrete_map={"玩家赢": "#dc2626", "玩家输": "#059669"},
        )
        figure.update_yaxes(title_text="连续段数量", tickformat=",.0f", separatethousands=True)
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)

    left, right = st.columns(2)
    with left:
        bet_bands = pd.cut(
            curve_spins["turnover"],
            bins=[0, 100, 500, 1_000, 2_000, 5_000, 10_000, 50_000, np.inf],
            labels=["100 及以下", "101 至 500", "501 至 1000", "1001 至 2000", "2001 至 5000", "5001 至 1 万", "1 万至 5 万", "5 万以上"],
            include_lowest=True,
            right=True,
        ).value_counts(sort=False)
        figure = px.bar(
            x=bet_bands.index.astype(str),
            y=bet_bands.values,
            title="下注金额分布",
            labels={"x": "下注档位", "y": "局数"},
            color_discrete_sequence=["#334155"],
        )
        figure.update_yaxes(tickformat=",.0f", separatethousands=True)
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)
    with right:
        player_stats = curve_spins.groupby("user_id", observed=True).agg(
            turnover=("turnover", "sum"), net=("net", "sum"), spins=("spin_number", "size")
        ).reset_index()
        player_stats["结果"] = np.where(player_stats["net"].gt(0), "玩家盈利", "玩家亏损")
        player_stats = player_stats.rename(
            columns={
                "user_id": "用户编号",
                "turnover": "累计下注",
                "net": "玩家净盈亏",
                "spins": "局数",
            }
        )
        figure = px.scatter(
            player_stats,
            x="累计下注",
            y="玩家净盈亏",
            color="结果",
            size="局数",
            hover_data=["用户编号"],
            title="玩家累计下注与盈亏",
            color_discrete_map={"玩家盈利": "#dc2626", "玩家亏损": "#059669"},
        )
        figure.add_hline(y=0, line_dash="dot", line_color="#64748b")
        compact_numeric_axis(figure, "x", player_stats["累计下注"])
        compact_numeric_axis(figure, "y", player_stats["玩家净盈亏"], include_zero=False)
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)


def render_players(events: pd.DataFrame, spins: pd.DataFrame) -> None:
    st.subheader("玩家洞察")
    summary = player_summary(events)
    winner_rate = (summary["net"] > 0).mean() * 100 if not summary.empty else 0
    cols = st.columns(4)
    metric(cols[0], "玩家数", len(summary), kind="count")
    metric(cols[1], "玩家盈利比例", winner_rate, kind="percent")
    metric(cols[2], "百万流水玩家", int((summary["turnover"] >= 1_000_000).sum()), kind="count")
    metric(cols[3], "最大单局赢分", max(spins["net"].max(), 0))

    options = summary["user_id"].tolist()
    selected_user = st.selectbox(
        "选择玩家",
        options=options,
        format_func=lambda user_id: (
            f"{user_id} · 流水 {compact_number(summary.loc[summary['user_id'].eq(user_id), 'turnover'].iloc[0])}"
        ),
    )
    selected = summary.loc[summary["user_id"].eq(selected_user)].iloc[0]
    user_spins = spins.loc[spins["user_id"].eq(selected_user)].sort_values("spin_time").copy()

    st.caption(
        f"{selected['region']} · {selected['device']} · {selected['gender']} · "
        f"{selected['language']} · 最近活跃 {selected['last_active']:%Y-%m-%d %H:%M}"
    )
    cols = st.columns(5)
    metric(cols[0], "累计下注", selected["turnover"])
    metric(cols[1], "累计派彩", selected["payout"])
    metric(cols[2], "玩家净盈亏", selected["net"])
    metric(cols[3], "RTP", selected["rtp"], kind="percent")
    metric(cols[4], "下注局数", selected["bets"], kind="count")

    user_spins["局次序号"] = np.arange(1, len(user_spins) + 1)
    user_spins["累计净盈亏"] = user_spins["net"].cumsum()
    user_spins = user_spins.rename(
        columns={
            "spin_time": "时间",
            "turnover": "下注",
            "payout": "派彩",
            "return_multiple": "返还倍率",
        }
    )
    chart_df = user_spins.iloc[np.linspace(0, len(user_spins) - 1, min(len(user_spins), 5_000), dtype=int)]
    figure = px.line(
        chart_df,
        x="局次序号",
        y="累计净盈亏",
        hover_data=["时间", "下注", "派彩", "返还倍率"],
        title="玩家累计盈亏轨迹",
        color_discrete_sequence=["#2563eb"],
    )
    figure.add_hline(y=0, line_dash="dot", line_color="#64748b")
    compact_numeric_axis(figure, "x", chart_df["局次序号"])
    compact_numeric_axis(figure, "y", chart_df["累计净盈亏"], include_zero=False)
    st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)

    display = summary.head(1_000).rename(
        columns={
            "user_id": "用户 ID",
            "region": "地区",
            "device": "设备",
            "gender": "性别",
            "language": "语言",
            "turnover": "流水",
            "payout": "派彩",
            "bets": "下注局数",
            "wins": "中出次数",
            "net": "玩家净盈亏",
            "rtp": "RTP (%)",
            "last_active": "最近活跃",
        }
    )
    localized_grid(display, key="player-grid", percent_columns=("RTP (%)",))


def render_large_player_analysis(file_map: dict[str, Path]) -> None:
    st.title("大用户分析")
    st.caption("跨全部游戏汇总同一用户的累计下注，并按完整局次分析首次游戏、游戏偏好和下注档位偏好。")
    file_entries = tuple(
        (game, str(path), path.stat().st_mtime_ns) for game, path in file_map.items()
    )
    with st.spinner("正在建立跨游戏大用户画像，首次加载需要一些时间…"):
        all_spins, _, profiles, per_game = load_cross_game_bundle(file_entries)

    tier = st.segmented_control(
        "大用户范围",
        options=["累计下注 200 万及以上", "累计下注 100 万至 200 万", "累计下注 100 万及以上"],
        default="累计下注 200 万及以上",
        selection_mode="single",
        key="large-player-tier",
    ) or "累计下注 200 万及以上"
    if tier == "累计下注 200 万及以上":
        selected_profiles = profiles.loc[profiles["turnover"].ge(2_000_000)].copy()
    elif tier == "累计下注 100 万至 200 万":
        selected_profiles = profiles.loc[
            profiles["turnover"].ge(1_000_000) & profiles["turnover"].lt(2_000_000)
        ].copy()
    else:
        selected_profiles = profiles.loc[profiles["turnover"].ge(1_000_000)].copy()

    if selected_profiles.empty:
        st.warning("当前范围没有符合条件的用户。")
        return

    selected_ids = selected_profiles["user_id"]
    selected_spins = all_spins.loc[all_spins["user_id"].isin(selected_ids)].copy()
    selected_game_stats = per_game.loc[per_game["user_id"].isin(selected_ids)].copy()
    cols = st.columns(6)
    metric(cols[0], "大用户数", len(selected_profiles), kind="count")
    metric(cols[1], "累计流水", selected_profiles["turnover"].sum())
    metric(cols[2], "累计派彩", selected_profiles["payout"].sum())
    metric(cols[3], "大用户 GGR", -selected_profiles["net"].sum())
    metric(cols[4], "人均流水", selected_profiles["turnover"].mean())
    metric(cols[5], "平均活跃天数", selected_profiles["active_days"].mean(), kind="decimal")

    st.subheader("大用户群体偏好")
    chart_specs = (
        ("first_game", "首次游戏", "首次进入的游戏"),
        ("preferred_game_turnover", "偏好游戏", "按累计流水判断的偏好游戏"),
        ("preferred_game_spins", "偏好游戏", "按局数判断的偏好游戏"),
    )
    chart_columns = st.columns(3)
    for column, (source_column, display_column, title) in zip(chart_columns, chart_specs):
        distribution = (
            selected_profiles[source_column]
            .value_counts()
            .rename_axis(display_column)
            .rename("用户数")
            .reset_index()
        )
        with column:
            figure = px.pie(
                distribution,
                names=display_column,
                values="用户数",
                title=title,
                color_discrete_sequence=px.colors.qualitative.Safe,
            )
            figure.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>用户数：%{value:,.0f}<br>占比：%{percent}<extra></extra>",
            )
            figure.update_layout(legend_title_text=display_column)
            st.plotly_chart(
                figure,
                use_container_width=True,
                config=PLOT_CONFIG,
                key=f"large-{source_column}",
            )

    left, right = st.columns(2)
    with left:
        bet_preferences = (
            selected_profiles["preferred_bet_band"]
            .value_counts()
            .rename_axis("下注档位")
            .rename("用户数")
            .reset_index()
        )
        figure = px.bar(
            bet_preferences,
            x="下注档位",
            y="用户数",
            title="下注档位偏好",
            color="下注档位",
            text_auto=True,
        )
        figure.update_layout(showlegend=False)
        figure.update_yaxes(tickformat=",.0f", separatethousands=True)
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)
    with right:
        game_contribution = (
            selected_game_stats.groupby("game", observed=True)
            .agg(turnover=("turnover", "sum"), spins=("spins", "sum"))
            .reset_index()
            .rename(columns={"game": "游戏", "turnover": "流水", "spins": "局数"})
        )
        figure = px.bar(
            game_contribution,
            x="游戏",
            y="流水",
            hover_data=["局数"],
            title="大用户在各游戏的流水与局数",
            color_discrete_sequence=["#334155"],
        )
        compact_numeric_axis(figure, "y", game_contribution["流水"])
        st.plotly_chart(figure, use_container_width=True, config=PLOT_CONFIG)

    st.subheader("单个大用户下钻")
    selected_user = st.selectbox(
        "选择大用户",
        options=selected_profiles["user_id"].tolist(),
        format_func=lambda user_id: (
            f"{user_id} · 累计下注 "
            f"{compact_number(selected_profiles.loc[selected_profiles['user_id'].eq(user_id), 'turnover'].iloc[0])}"
        ),
        key="large-player-user",
    )
    selected = selected_profiles.loc[selected_profiles["user_id"].eq(selected_user)].iloc[0]
    cols = st.columns(6)
    metric(cols[0], "累计下注", selected["turnover"])
    metric(cols[1], "玩家净盈亏", selected["net"])
    metric(cols[2], "RTP", selected["rtp"], kind="percent")
    metric(cols[3], "活跃天数", selected["active_days"], kind="count")
    metric(cols[4], "参与游戏数", selected["games_played"], kind="count")
    metric(cols[5], "最大下注", selected["max_bet"])
    st.caption(
        f"首次游戏：{selected['first_game']} · 按流水偏好：{selected['preferred_game_turnover']} · "
        f"按局数偏好：{selected['preferred_game_spins']} · 下注档位偏好：{selected['preferred_bet_band']}"
    )

    user_spins = selected_spins.loc[selected_spins["user_id"].eq(selected_user)].sort_values(
        "spin_time", kind="stable"
    ).copy()
    user_spins["累计净盈亏"] = user_spins["net"].cumsum()
    curve = user_spins.rename(
        columns={
            "spin_time": "时间",
            "game": "游戏",
            "turnover": "下注",
            "payout": "派彩",
            "return_multiple": "返还倍率",
        }
    )
    if len(curve) > 10_000:
        positions = np.linspace(0, len(curve) - 1, 10_000, dtype=int)
        curve = curve.iloc[positions]
    figure = px.line(
        curve,
        x="时间",
        y="累计净盈亏",
        color="游戏",
        hover_data=["下注", "派彩", "返还倍率"],
        title="大用户累计盈亏轨迹",
    )
    figure.add_hline(y=0, line_dash="dot", line_color="#64748b")
    figure.update_layout(hovermode="x unified")
    compact_numeric_axis(figure, "y", curve["累计净盈亏"], include_zero=False)
    st.plotly_chart(time_axis_figure(figure), use_container_width=True, config=PLOT_CONFIG)

    user_games = selected_game_stats.loc[selected_game_stats["user_id"].eq(selected_user)].rename(
        columns={
            "user_id": "用户 ID",
            "game": "游戏",
            "first_play": "首次游玩",
            "last_play": "最近游玩",
            "active_days": "活跃天数",
            "turnover": "流水",
            "payout": "派彩",
            "spins": "局数",
            "hits": "中奖局数",
            "average_bet": "平均下注",
            "max_bet": "最大下注",
            "net": "玩家净盈亏",
            "rtp": "RTP (%)",
        }
    )
    localized_grid(user_games, key="large-player-games", height=300, percent_columns=("RTP (%)",))

    st.subheader("大用户清单")
    display = selected_profiles.rename(
        columns={
            "user_id": "用户 ID",
            "first_play_time": "首次游玩时间",
            "last_active": "最近活跃时间",
            "active_days": "活跃天数",
            "games_played": "参与游戏数",
            "turnover": "累计下注",
            "payout": "累计派彩",
            "spins": "局数",
            "hits": "中奖局数",
            "average_bet": "平均下注",
            "max_bet": "最大下注",
            "net": "玩家净盈亏",
            "rtp": "RTP (%)",
            "hit_rate": "中奖率 (%)",
            "first_game": "首次游戏",
            "preferred_game_turnover": "流水偏好游戏",
            "preferred_game_spins": "局数偏好游戏",
            "preferred_bet_band": "下注档位偏好",
        }
    )
    localized_grid(
        display,
        key="large-player-list",
        height=500,
        page_size=25,
        percent_columns=("RTP (%)", "中奖率 (%)"),
    )


def render_details(events: pd.DataFrame) -> None:
    st.subheader("数据明细")
    limit = st.select_slider("显示最近记录", options=[500, 1_000, 2_000, 5_000], value=1_000)
    display = (
        events.sort_values("create_date", ascending=False)
        .head(limit)[
            ["create_date", "user_id", "region", "device", "gender", "language", "event_label", "amount"]
        ]
        .rename(
            columns={
                "create_date": "时间",
                "user_id": "用户 ID",
                "region": "地区",
                "device": "设备",
                "gender": "性别",
                "language": "语言",
                "event_label": "场景",
                "amount": "金币数量",
            }
        )
    )
    st.caption(f"筛选后共 {len(events):,} 条，当前显示最近 {len(display):,} 条。")
    localized_grid(display, key="detail-grid", height=560, page_size=25)


st.sidebar.title("SlotInsight")
local_files = discover_data_files(PROJECT_DIR)
file_map = {game_name_from_filename(path.name): path for path in local_files}

view_options = ["全游戏总览", "大用户分析", "单游戏分析"] if local_files else ["单游戏分析"]
view_mode = st.sidebar.radio("面板", view_options, horizontal=True)

if view_mode == "全游戏总览":
    render_game_comparison(file_map)
    st.stop()
if view_mode == "大用户分析":
    render_large_player_analysis(file_map)
    st.stop()

source_options = ["本地数据"] if local_files else []
source_options.append("上传文件")
source_mode = st.sidebar.radio("数据来源", source_options, horizontal=True)

selected_name = ""
try:
    if source_mode == "本地数据":
        selected_name = st.sidebar.selectbox("游戏", options=list(file_map))
        selected_path = file_map[selected_name]
        st.sidebar.markdown(
            f'<p class="source-note">{selected_path.name}<br>{selected_path.stat().st_size / 1024 / 1024:.1f} MB</p>',
            unsafe_allow_html=True,
        )
        with st.spinner(f"正在读取并重建 {selected_name} 局次，首次加载需要一些时间…"):
            events, spins = load_local_bundle(str(selected_path), selected_path.stat().st_mtime_ns)
    else:
        uploaded = st.sidebar.file_uploader("选择 Excel 文件", type=["xlsx", "xlsm"])
        if uploaded is None:
            st.title("SlotInsight 游戏数据面板")
            st.info("请选择一个 Excel 数据文件。")
            st.stop()
        selected_name = game_name_from_filename(uploaded.name)
        with st.spinner(f"正在读取并重建 {selected_name} 局次…"):
            events, spins = load_uploaded_bundle(uploaded.getvalue(), uploaded.name)
except Exception as exc:
    st.error(f"数据读取失败：{exc}")
    st.stop()

st.sidebar.divider()
st.sidebar.subheader("全局筛选")
min_date = events["create_date"].min().date()
max_date = events["create_date"].max().date()
date_range = st.sidebar.date_input(
    "日期范围", value=(min_date, max_date), min_value=min_date, max_value=max_date
)

filter_values: dict[str, list[str]] = {}
for column, label in DIMENSION_LABELS.items():
    options = sorted(events[column].astype("string").unique().tolist())
    filter_values[column] = st.sidebar.multiselect(label, options=options, placeholder=f"全部{label}")

filtered_events = filter_game_data(
    events,
    date_range,
    filter_values["region"],
    filter_values["device"],
    filter_values["gender"],
    filter_values["language"],
)
filtered_spins = filter_spin_data(
    spins,
    date_range,
    filter_values["region"],
    filter_values["device"],
    filter_values["gender"],
    filter_values["language"],
)

st.title(f"{selected_name} 数据面板")
st.caption(
    f"{min_date:%Y-%m-%d} 至 {max_date:%Y-%m-%d} · 原始事件 {len(events):,} 条 · "
    f"筛选后 {len(filtered_events):,} 条 · 重建局次 {len(filtered_spins):,} 局"
)

if filtered_events.empty or filtered_spins.empty:
    st.warning("当前筛选条件下没有完整局次数据。")
    st.stop()

tab_overview, tab_audience, tab_spins, tab_players, tab_details = st.tabs(
    ["经营概览", "人群分析", "局次分析", "玩家分析", "数据明细"]
)
with tab_overview:
    render_operating_overview(filtered_events, events, filtered_spins)
with tab_audience:
    render_audience(filtered_events)
with tab_spins:
    render_spin_analysis(filtered_spins)
with tab_players:
    render_players(filtered_events, filtered_spins)
with tab_details:
    render_details(filtered_events)
