import unittest
from pathlib import Path

import pandas as pd

from data_utils import (
    dimension_summary,
    discover_data_files,
    filter_game_data,
    game_name_from_filename,
    normalize_game_data,
    player_summary,
)
from slot_metrics import (
    advanced_metrics,
    build_spin_table,
    cumulative_bet_tier_summary,
    game_summary,
    large_player_summary,
    streak_table,
    time_summary,
)


class DataUtilsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = pd.DataFrame(
            {
                "uid": [1, 1, 2, 2],
                "地区": ["菲律宾", "菲律宾", "美国", "美国"],
                "设备": ["ios", "ios", "android", "android"],
                "性别": ["女", "女", "男", "男"],
                "语言": ["英语", "英语", "英语", "英语"],
                "场景": ["下注", "中出", "下注", "中出"],
                "金币数量": [-100, 80, -200, 250],
                "时间": pd.to_datetime(
                    [
                        "2026-08-10 01:00",
                        "2026-08-10 01:01",
                        "2026-08-11 01:00",
                        "2026-08-11 01:01",
                    ]
                ),
            }
        )

    def test_normalizes_new_export_columns(self) -> None:
        frame = normalize_game_data(self.raw)

        self.assertEqual(frame["turnover"].sum(), 300)
        self.assertEqual(frame["payout"].sum(), 330)
        self.assertEqual(frame["is_bet"].sum(), 2)
        self.assertEqual(frame["is_win"].sum(), 2)

    def test_filters_and_aggregates(self) -> None:
        frame = normalize_game_data(self.raw)
        filtered = filter_game_data(
            frame,
            (pd.Timestamp("2026-08-10").date(), pd.Timestamp("2026-08-10").date()),
            ["菲律宾"],
            [],
            [],
            [],
        )

        self.assertEqual(len(filtered), 2)
        self.assertEqual(len(player_summary(frame)), 2)
        self.assertEqual(len(dimension_summary(frame, "region")), 2)

    def test_discovers_supported_local_files(self) -> None:
        files = discover_data_files(Path.cwd())

        self.assertTrue(files)
        self.assertTrue(all(path.suffix == ".xlsx" for path in files))
        self.assertEqual(
            game_name_from_filename("Tigerslot游戏用户明细_0811.xlsx"),
            "Tigerslot",
        )

    def test_reconstructs_spins_and_advanced_metrics(self) -> None:
        frame = normalize_game_data(self.raw)
        spins = build_spin_table(frame)
        metrics = advanced_metrics(spins)

        self.assertEqual(len(spins), 2)
        self.assertEqual(spins["turnover"].sum(), 300)
        self.assertEqual(spins["payout"].sum(), 330)
        self.assertAlmostEqual(metrics["rtp"], 110.0)
        self.assertEqual(metrics["max_win_streak"], 1)
        self.assertEqual(metrics["max_loss_streak"], 1)
        self.assertEqual(len(streak_table(spins)), 2)
        self.assertEqual(len(time_summary(spins, "天")), 2)
        weekly = time_summary(spins, "周")
        self.assertTrue((weekly["period"].dt.dayofweek == 0).all())
        self.assertEqual(game_summary(spins, frame)["payout"], 330)

    def test_cumulative_bet_tiers_are_mutually_exclusive(self) -> None:
        spins = pd.DataFrame(
            {
                "user_id": [1, 1, 2, 3],
                "turnover": [4_000, 6_000, 1_000_000, 2_000_000],
            }
        )
        tiers = cumulative_bet_tier_summary(spins).set_index("tier")

        self.assertEqual(tiers["players"].sum(), 3)
        self.assertEqual(tiers.loc["1 万至 10 万", "players"], 1)
        self.assertEqual(tiers.loc["100 万至 200 万", "players"], 1)
        self.assertEqual(tiers.loc["200 万及以上", "players"], 1)

    def test_large_player_profile_uses_cross_game_history(self) -> None:
        spins = pd.DataFrame(
            {
                "user_id": [1, 1, 1, 2],
                "game": ["游戏甲", "游戏甲", "游戏乙", "游戏甲"],
                "spin_time": pd.to_datetime(
                    [
                        "2026-08-10 01:00",
                        "2026-08-10 01:30",
                        "2026-08-11 01:00",
                        "2026-08-10 02:00",
                    ]
                ),
                "turnover": [100, 100, 300, 2_000_000],
                "payout": [0, 100, 600, 1_000_000],
                "spin_number": [1, 2, 3, 1],
                "is_hit": [False, True, True, True],
            }
        )
        profiles, per_game = large_player_summary(spins)
        user = profiles.loc[profiles["user_id"].eq(1)].iloc[0]

        self.assertEqual(user["first_game"], "游戏甲")
        self.assertEqual(user["preferred_game_turnover"], "游戏乙")
        self.assertEqual(user["preferred_game_spins"], "游戏甲")
        self.assertEqual(user["preferred_bet_band"], "100 及以下")
        self.assertEqual(len(per_game.loc[per_game["user_id"].eq(1)]), 2)


if __name__ == "__main__":
    unittest.main()
