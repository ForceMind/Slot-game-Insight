from __future__ import annotations

import math

import numpy as np
import pandas as pd


TIME_FREQUENCIES = {"小时": "h", "天": "D", "周": "W-SUN"}

CUMULATIVE_BET_BINS = [
    0,
    10_000,
    100_000,
    200_000,
    500_000,
    1_000_000,
    2_000_000,
    np.inf,
]
CUMULATIVE_BET_LABELS = [
    "1 万以下",
    "1 万至 10 万",
    "10 万至 20 万",
    "20 万至 50 万",
    "50 万至 100 万",
    "100 万至 200 万",
    "200 万及以上",
]

BET_AMOUNT_BINS = [0, 100, 500, 1_000, 2_000, 5_000, 10_000, 50_000, np.inf]
BET_AMOUNT_LABELS = [
    "100 及以下",
    "101 至 500",
    "501 至 1000",
    "1001 至 2000",
    "2001 至 5000",
    "5001 至 1 万",
    "1 万至 5 万",
    "5 万以上",
]


def build_spin_table(events: pd.DataFrame) -> pd.DataFrame:
    """Attribute every payout to the preceding bet for the same player."""
    ordered = events.sort_values(["user_id", "create_date"], kind="stable").copy()
    ordered["spin_number"] = ordered.groupby("user_id", sort=False)["is_bet"].cumsum()
    ordered = ordered.loc[ordered["spin_number"].gt(0)]

    spins = (
        ordered.groupby(["user_id", "spin_number"], observed=True, sort=False)
        .agg(
            spin_time=("create_date", "min"),
            region=("region", "first"),
            device=("device", "first"),
            gender=("gender", "first"),
            language=("language", "first"),
            turnover=("turnover", "sum"),
            payout=("payout", "sum"),
        )
        .reset_index()
    )
    spins = spins.loc[spins["turnover"].gt(0)].copy()
    spins["net"] = spins["payout"] - spins["turnover"]
    spins["return_multiple"] = spins["payout"] / spins["turnover"]
    spins["is_hit"] = spins["payout"].gt(0)
    spins["outcome"] = np.select(
        [spins["net"].gt(0), spins["net"].lt(0)],
        ["玩家赢", "玩家输"],
        default="持平",
    )
    return spins.sort_values(["spin_time", "user_id"], kind="stable").reset_index(drop=True)


def filter_spin_data(
    spins: pd.DataFrame,
    date_range: object,
    regions: list[str] | None = None,
    devices: list[str] | None = None,
    genders: list[str] | None = None,
    languages: list[str] | None = None,
) -> pd.DataFrame:
    if isinstance(date_range, (tuple, list)):
        start_date = date_range[0]
        end_date = date_range[-1]
    else:
        start_date = end_date = date_range

    mask = spins["spin_time"].dt.date.between(start_date, end_date)
    for column, selected in (
        ("region", regions or []),
        ("device", devices or []),
        ("gender", genders or []),
        ("language", languages or []),
    ):
        if selected:
            mask &= spins[column].isin(selected)
    return spins.loc[mask].copy()


def streak_table(spins: pd.DataFrame) -> pd.DataFrame:
    if spins.empty:
        return pd.DataFrame(columns=["user_id", "outcome", "length"])

    ordered = spins.sort_values(["user_id", "spin_time"], kind="stable")
    changed = ordered["user_id"].ne(ordered["user_id"].shift()) | ordered[
        "outcome"
    ].ne(ordered["outcome"].shift())
    working = ordered[["user_id", "outcome"]].copy()
    working["run_id"] = changed.cumsum()
    return (
        working.groupby("run_id", sort=False)
        .agg(user_id=("user_id", "first"), outcome=("outcome", "first"), length=("outcome", "size"))
        .reset_index(drop=True)
    )


def time_summary(spins: pd.DataFrame, granularity: str) -> pd.DataFrame:
    if granularity not in TIME_FREQUENCIES:
        raise ValueError(f"不支持的时间粒度：{granularity}")
    if spins.empty:
        return pd.DataFrame()

    frequency = TIME_FREQUENCIES[granularity]
    working = spins.copy()
    if granularity == "周":
        working["period"] = working["spin_time"].dt.to_period(frequency).dt.start_time
    else:
        working["period"] = working["spin_time"].dt.floor(frequency)

    summary = (
        working.groupby("period", observed=True)
        .agg(
            active_users=("user_id", "nunique"),
            spins=("spin_number", "size"),
            hits=("is_hit", "sum"),
            turnover=("turnover", "sum"),
            payout=("payout", "sum"),
            net_std=("net", "std"),
            return_volatility=("return_multiple", "std"),
        )
        .reset_index()
    )
    summary["ggr"] = summary["turnover"] - summary["payout"]
    summary["rtp"] = np.where(
        summary["turnover"].gt(0), summary["payout"] / summary["turnover"] * 100, 0
    )
    summary["hit_rate"] = np.where(
        summary["spins"].gt(0), summary["hits"] / summary["spins"] * 100, 0
    )
    return summary.fillna({"net_std": 0, "return_volatility": 0})


def advanced_metrics(spins: pd.DataFrame) -> dict[str, float]:
    if spins.empty:
        return {key: 0.0 for key in _METRIC_KEYS}

    turnover = float(spins["turnover"].sum())
    payout = float(spins["payout"].sum())
    spin_count = len(spins)
    player_count = spins["user_id"].nunique()
    player_totals = spins.groupby("user_id", observed=True).agg(
        turnover=("turnover", "sum"), payout=("payout", "sum"), net=("net", "sum")
    )
    top_count = max(1, math.ceil(player_count * 0.01))
    runs = streak_table(spins)
    win_runs = runs.loc[runs["outcome"].eq("玩家赢"), "length"]
    loss_runs = runs.loc[runs["outcome"].eq("玩家输"), "length"]
    average_bet = float(spins["turnover"].mean())
    bet_std = float(spins["turnover"].std(ddof=0))

    return {
        "rtp": payout / turnover * 100 if turnover else 0.0,
        "hold": (turnover - payout) / turnover * 100 if turnover else 0.0,
        "hit_rate": float(spins["is_hit"].mean() * 100),
        "zero_win_rate": float(spins["payout"].eq(0).mean() * 100),
        "average_bet": average_bet,
        "median_bet": float(spins["turnover"].median()),
        "bet_cv": bet_std / average_bet if average_bet else 0.0,
        "net_std": float(spins["net"].std(ddof=0)),
        "return_volatility": float(spins["return_multiple"].std(ddof=0)),
        "expected_ggr_per_spin": (turnover - payout) / spin_count,
        "max_spin_win": float(spins["net"].max()),
        "max_spin_loss": abs(float(min(spins["net"].min(), 0))),
        "p95_multiplier": float(spins["return_multiple"].quantile(0.95)),
        "big_win_rate": float(spins["return_multiple"].ge(10).mean() * 100),
        "super_win_rate": float(spins["return_multiple"].ge(50).mean() * 100),
        "max_win_streak": float(win_runs.max()) if not win_runs.empty else 0.0,
        "max_loss_streak": float(loss_runs.max()) if not loss_runs.empty else 0.0,
        "avg_win_streak": float(win_runs.mean()) if not win_runs.empty else 0.0,
        "avg_loss_streak": float(loss_runs.mean()) if not loss_runs.empty else 0.0,
        "top_turnover_concentration": (
            float(player_totals.nlargest(top_count, "turnover")["turnover"].sum())
            / turnover
            * 100
            if turnover
            else 0.0
        ),
        "top_payout_concentration": (
            float(player_totals.nlargest(top_count, "payout")["payout"].sum())
            / payout
            * 100
            if payout
            else 0.0
        ),
        "profitable_player_rate": float(player_totals["net"].gt(0).mean() * 100),
        "spins_per_player": spin_count / player_count if player_count else 0.0,
    }


def cumulative_bet_tier_summary(spins: pd.DataFrame) -> pd.DataFrame:
    """Return mutually exclusive player tiers using cross-game cumulative turnover."""
    player_bets = (
        spins.groupby("user_id", observed=True)["turnover"]
        .sum()
        .rename("turnover")
        .reset_index()
    )
    player_bets["tier"] = pd.cut(
        player_bets["turnover"],
        bins=CUMULATIVE_BET_BINS,
        labels=CUMULATIVE_BET_LABELS,
        include_lowest=True,
        right=False,
    )
    summary = (
        player_bets.groupby("tier", observed=False)
        .agg(players=("user_id", "nunique"), turnover=("turnover", "sum"))
        .reset_index()
    )
    summary["tier"] = summary["tier"].astype("string")
    return summary


def large_player_summary(spins: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build cross-game user profiles and the supporting per-game aggregates."""
    if "game" not in spins.columns:
        raise ValueError("大用户分析需要游戏字段")
    if spins.empty:
        return pd.DataFrame(), pd.DataFrame()

    ordered = spins.sort_values(["spin_time", "game"], kind="stable").copy()
    ordered["bet_band"] = pd.cut(
        ordered["turnover"],
        bins=BET_AMOUNT_BINS,
        labels=BET_AMOUNT_LABELS,
        include_lowest=True,
        right=True,
    )
    per_game = (
        ordered.groupby(["user_id", "game"], observed=True)
        .agg(
            first_play=("spin_time", "min"),
            last_play=("spin_time", "max"),
            active_days=("spin_time", lambda values: values.dt.normalize().nunique()),
            turnover=("turnover", "sum"),
            payout=("payout", "sum"),
            spins=("spin_number", "size"),
            hits=("is_hit", "sum"),
            average_bet=("turnover", "mean"),
            max_bet=("turnover", "max"),
        )
        .reset_index()
    )
    per_game["net"] = per_game["payout"] - per_game["turnover"]
    per_game["rtp"] = np.where(
        per_game["turnover"].gt(0),
        per_game["payout"] / per_game["turnover"] * 100,
        0,
    )

    totals = (
        ordered.groupby("user_id", observed=True)
        .agg(
            first_play_time=("spin_time", "min"),
            last_active=("spin_time", "max"),
            active_days=("spin_time", lambda values: values.dt.normalize().nunique()),
            games_played=("game", "nunique"),
            turnover=("turnover", "sum"),
            payout=("payout", "sum"),
            spins=("spin_number", "size"),
            hits=("is_hit", "sum"),
            average_bet=("turnover", "mean"),
            max_bet=("turnover", "max"),
        )
        .reset_index()
    )
    totals["net"] = totals["payout"] - totals["turnover"]
    totals["rtp"] = np.where(
        totals["turnover"].gt(0), totals["payout"] / totals["turnover"] * 100, 0
    )
    totals["hit_rate"] = np.where(
        totals["spins"].gt(0), totals["hits"] / totals["spins"] * 100, 0
    )

    first_games = (
        ordered.drop_duplicates("user_id", keep="first")
        .set_index("user_id")["game"]
        .rename("first_game")
    )
    turnover_preferences = (
        per_game.sort_values(
            ["user_id", "turnover", "game"],
            ascending=[True, False, True],
            kind="stable",
        )
        .drop_duplicates("user_id")
        .set_index("user_id")["game"]
        .rename("preferred_game_turnover")
    )
    spin_preferences = (
        per_game.sort_values(
            ["user_id", "spins", "game"],
            ascending=[True, False, True],
            kind="stable",
        )
        .drop_duplicates("user_id")
        .set_index("user_id")["game"]
        .rename("preferred_game_spins")
    )
    band_preferences = (
        ordered.groupby(["user_id", "bet_band"], observed=True)
        .size()
        .rename("count")
        .reset_index()
        .sort_values(
            ["user_id", "count", "bet_band"],
            ascending=[True, False, True],
            kind="stable",
        )
        .drop_duplicates("user_id")
        .set_index("user_id")["bet_band"]
        .astype("string")
        .rename("preferred_bet_band")
    )
    profiles = totals.set_index("user_id").join(
        [first_games, turnover_preferences, spin_preferences, band_preferences],
    ).reset_index()
    return profiles.sort_values("turnover", ascending=False).reset_index(drop=True), per_game


def game_summary(spins: pd.DataFrame, events: pd.DataFrame | None = None) -> dict[str, float]:
    metrics = advanced_metrics(spins)
    financial_source = events if events is not None else spins
    turnover = float(financial_source["turnover"].sum())
    payout = float(financial_source["payout"].sum())
    rtp = payout / turnover * 100 if turnover else 0.0
    hold = (turnover - payout) / turnover * 100 if turnover else 0.0
    return {
        **metrics,
        "active_users": float(financial_source["user_id"].nunique()),
        "spins": float(len(spins)),
        "turnover": turnover,
        "payout": payout,
        "ggr": turnover - payout,
        "rtp": rtp,
        "hold": hold,
    }


_METRIC_KEYS = (
    "rtp",
    "hold",
    "hit_rate",
    "zero_win_rate",
    "average_bet",
    "median_bet",
    "bet_cv",
    "net_std",
    "return_volatility",
    "expected_ggr_per_spin",
    "max_spin_win",
    "max_spin_loss",
    "p95_multiplier",
    "big_win_rate",
    "super_win_rate",
    "max_win_streak",
    "max_loss_streak",
    "avg_win_streak",
    "avg_loss_streak",
    "top_turnover_concentration",
    "top_payout_concentration",
    "profitable_player_rate",
    "spins_per_player",
)

ADVANCED_METRIC_KEYS = _METRIC_KEYS
