"""R5 场景骨架测试：load_scenario 校验 / 未知 key raise / build_world 三目标
/ 图幅与建筑 / 回退 demo / list_scenarios。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScenarioLoad(unittest.TestCase):

    def test_load_bagration_field(self):
        from sovs.app.scenario import load_scenario
        doc = load_scenario("bagration_field")
        self.assertEqual(doc["scenario_key"], "bagration_field")
        self.assertEqual(doc["map_key"], "bagration_field")
        self.assertEqual(doc["name"], "巴格拉季昂 · 克伦基村")
        self.assertEqual(len(doc["objectives"]), 3)
        by_id = {o["id"]: o for o in doc["objectives"]}
        self.assertEqual(by_id[1]["pos_cm"], [108000, 64000])   # R6 §1-2 挪位
        self.assertEqual(by_id[1]["radius_cm"], 6500)
        self.assertEqual(by_id[2]["pos_cm"], [100000, 42000])
        self.assertEqual(by_id[3]["pos_cm"], [56000, 72000])
        self.assertEqual(len(doc["briefing"]), 3)
        self.assertIn("decor", doc)                 # R6 视觉专用（sim 不读）
        self.assertEqual(doc["spawn"]["lane_y_cm"], 20000)

    def test_objectives_pairwise_disjoint(self):
        """R6 §1-2：任意两目标中心距 > 半径和（旗帜/标签零重叠的几何锁）。"""
        from sovs.app.scenario import load_scenario
        objs = load_scenario("bagration_field")["objectives"]
        for i in range(len(objs)):
            for j in range(i + 1, len(objs)):
                a, b = objs[i], objs[j]
                d = abs(a["pos_cm"][0] - b["pos_cm"][0]) \
                    + abs(a["pos_cm"][1] - b["pos_cm"][1])
                self.assertGreater(d, a["radius_cm"] + b["radius_cm"],
                                   "%s×%s 中心距 %d ≤ 半径和 %d"
                                   % (a["name"], b["name"], d,
                                      a["radius_cm"] + b["radius_cm"]))

    def test_unknown_key_raises(self):
        from sovs.app.scenario import ScenarioError, load_scenario
        with self.assertRaises(ScenarioError):
            load_scenario("__nope__")

    def test_list_scenarios_contains_bagration(self):
        from sovs.app.scenario import list_scenarios
        self.assertIn("bagration_field", list_scenarios())


class TestBuildWorldScenario(unittest.TestCase):

    def test_build_world_three_objectives(self):
        from sovs.app.session import build_world
        w = build_world(42, "su_min")
        self.assertEqual(len(w.objectives), 3)
        self.assertEqual(w.map_extent, (200000, 100000))
        self.assertEqual(len(w.buildings), 8)       # V1×4＋V2×3＋V3×1
        self.assertTrue(w.forest_tiles)             # 森林旁挂非空
        self.assertTrue(w.terrain.tiles)            # 道路/废墟瓦片非空
        ids = [o.id for o in w.objectives]
        self.assertEqual(ids, [1, 2, 3])            # scenario 声明序

    def test_build_world_fallback_demo(self):
        from sovs.app.session import build_world
        w = build_world(42, "su_min", scenario_key="__missing__")
        self.assertEqual(len(w.objectives), 1)      # 回退单中央占点
        self.assertEqual(w.objectives[0].pos, (100000, 50000))
        self.assertEqual(w.map_extent, (200000, 100000))

    def test_session_scenario_key_passthrough(self):
        from sovs.app.session import SkirmishSession
        s = SkirmishSession(seed=7, scenario_key="bagration_field")
        self.assertEqual(len(s.world.objectives), 3)
        info = s.scenario_info()
        self.assertIsNotNone(info)
        self.assertIn("克伦基", info["name"])
        labels = s.objective_labels()
        self.assertEqual(labels[2], "十字路口")
        s2 = SkirmishSession(seed=7, scenario_key="__missing__")
        self.assertIsNone(s2.scenario_info())       # 回退=无场景摘要
        self.assertEqual(s2.objective_labels(), {})


if __name__ == "__main__":
    unittest.main()
