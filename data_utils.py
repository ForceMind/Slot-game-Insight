from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd


DATA_DIR_NAME = "数据"
SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}

COLUMN_ALIASES = {
    "user_id": ("uid", "user_id", "用户id", "用户ID"),
    "region": ("地区", "region", "country"),
    "device": ("设备", "device", "platform"),
    "gender": ("性别", "gender"),
    "language": ("语言", "language", "locale"),
    "event": ("场景", "scene", "event", "type"),
    "amount": ("金币数量", "amount", "coin_amount"),
    "create_date": ("时间", "create_date", "datetime", "日期"),
}

REQUIRED_COLUMNS = {"user_id", "event", "amount", "create_date"}
DIMENSION_COLUMNS = ("region", "device", "gender", "language")
DIMENSION_LABELS = {
    "region": "地区",
    "device": "设备",
    "gender": "性别",
    "language": "语言",
}


def discover_data_files(project_dir: Path) -> list[Path]:
    data_dir = project_dir / DATA_DIR_NAME
    if not data_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in data_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
            and not path.name.startswith("~$")
        ),
        key=lambda path: path.name.casefold(),
    )


def game_name_from_filename(filename: str) -> str:
    name = Path(filename).stem.strip()
    name = re.sub(r"游戏用户明细.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"用户明细.*$", "", name, flags=re.IGNORECASE)
    return name.strip(" _-") or Path(filename).stem


def _canonical_column_map(columns: list[object]) -> dict[object, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            lookup[str(alias).strip().casefold()] = canonical

    result: dict[object, str] = {}
    claimed: set[str] = set()
    for column in columns:
        canonical = lookup.get(str(column).strip().casefold())
        if canonical and canonical not in claimed:
            result[column] = canonical
            claimed.add(canonical)
    return result


def normalize_game_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    rename_map = _canonical_column_map(list(raw_df.columns))
    df = raw_df.rename(columns=rename_map)
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        labels = "、".join(sorted(missing))
        raise ValueError(f"缺少必要字段：{labels}")

    for column in DIMENSION_COLUMNS:
        if column not in df.columns:
            df[column] = "未知"

    keep_columns = [
        "user_id",
        "region",
        "device",
        "gender",
        "language",
        "event",
        "amount",
        "create_date",
    ]
    df = df[keep_columns].copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["create_date"] = pd.to_datetime(df["create_date"], errors="coerce")
    df = df.dropna(subset=["user_id", "amount", "create_date"])

    for column in (*DIMENSION_COLUMNS, "event"):
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
            .fillna("未知")
            .astype("category")
        )

    event_text = df["event"].astype("string").str.casefold()
    explicit_bet = event_text.str.contains("下注|bet", regex=True, na=False)
    explicit_win = event_text.str.contains("中出|中奖|派彩|win|payout", regex=True, na=False)
    df["is_bet"] = explicit_bet | (~explicit_win & df["amount"].lt(0))
    df["is_win"] = explicit_win | (~explicit_bet & df["amount"].gt(0))
    df["turnover"] = np.where(df["is_bet"], df["amount"].abs(), 0)
    df["payout"] = np.where(df["is_win"], df["amount"].clip(lower=0), 0)
    df["event_label"] = np.select(
        [df["is_bet"], df["is_win"]], ["下注", "中出"], default="其他"
    )
    df["event_label"] = df["event_label"].astype("category")
    return df.sort_values("create_date", kind="stable").reset_index(drop=True)


def read_game_data(source: str | Path | BinaryIO) -> pd.DataFrame:
    raw_df = pd.read_excel(source, engine="openpyxl")
    return normalize_game_data(raw_df)


def filter_game_data(
    df: pd.DataFrame,
    date_range: object,
    regions: list[str],
    devices: list[str],
    genders: list[str],
    languages: list[str],
) -> pd.DataFrame:
    if isinstance(date_range, (tuple, list)):
        start_date = date_range[0]
        end_date = date_range[-1]
    else:
        start_date = end_date = date_range

    mask = df["create_date"].dt.date.between(start_date, end_date)
    for column, selected in (
        ("region", regions),
        ("device", devices),
        ("gender", genders),
        ("language", languages),
    ):
        if selected:
            mask &= df[column].isin(selected)
    return df.loc[mask].copy()


def dimension_summary(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if dimension not in DIMENSION_COLUMNS:
        raise ValueError(f"不支持的分析维度：{dimension}")

    summary = (
        df.groupby(dimension, observed=True)
        .agg(
            active_users=("user_id", "nunique"),
            bets=("is_bet", "sum"),
            turnover=("turnover", "sum"),
            payout=("payout", "sum"),
        )
        .reset_index()
    )
    summary["ggr"] = summary["turnover"] - summary["payout"]
    summary["rtp"] = np.where(
        summary["turnover"].gt(0),
        summary["payout"] / summary["turnover"] * 100,
        0,
    )
    return summary.sort_values("turnover", ascending=False).reset_index(drop=True)


def player_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("user_id", observed=True)
        .agg(
            region=("region", "last"),
            device=("device", "last"),
            gender=("gender", "last"),
            language=("language", "last"),
            turnover=("turnover", "sum"),
            payout=("payout", "sum"),
            bets=("is_bet", "sum"),
            wins=("is_win", "sum"),
            net=("amount", "sum"),
            last_active=("create_date", "max"),
        )
        .reset_index()
    )
    summary["rtp"] = np.where(
        summary["turnover"].gt(0),
        summary["payout"] / summary["turnover"] * 100,
        0,
    )
    return summary.sort_values("turnover", ascending=False).reset_index(drop=True)
