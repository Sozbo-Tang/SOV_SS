"""FE-05 F3 单位详细档测试：session.unit_detail 己方全量/敌方 5 键/未知
None/帧不含详细字段（按需查询纪律——state_frame 不导出 elements 等档）。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_FULL_KEYS = {"name", "category", "team", "hp", "hp_max", "armor_ke",
              "armor_he", "optics_ground_cm", "optics_air_cm", "speed_tier",
              "stealth_base", "morale", "stance", "mode", "elements"}
_WEAPON_KEYS = {"name", "ammo_left", "ammo_base", "max_range_cm", "pen_min",
                "pen_max", "damage_type", "reload_ticks"}


def _session_to_battle():
    """seed42 遭遇到实战接触窗（红蓝单位同帧——screenshot 同款推进）。"""
    from sovs.app.scripts import ScriptedPilot
    from sovs.app.session import SkirmishSession
    session = SkirmishSession(seed=42)
    pilot = ScriptedPilot(session)
    while session.world.tick < 2165:
        pilot.step()
        session.advance(1)
    return session


class TestUnitDetail(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.session = _session_to_battle()

    def test_own_unit_full_fields(self):
        own = next(u for u in self.session.world.units
                   if u.team == 0 and u.alive)
        d = self.session.unit_detail(own.id)
        self.assertIsNotNone(d)
        self.assertEqual(set(d), _FULL_KEYS)
        self.assertEqual(d["name"], own.template.name)
        self.assertEqual(d["hp"], sum(e.hp_current for e in own.elements))
        self.assertEqual(d["hp_max"], sum(e.template.hp_max
                                          for e in own.elements))
        self.assertTrue(d["elements"])
        for el in d["elements"]:
            self.assertEqual(set(el), {"hp", "hp_max", "weapons"})
            for w in el["weapons"]:
                self.assertEqual(set(w), _WEAPON_KEYS)
                self.assertIn(w["damage_type"], ("ke", "he", "smoke"))
        self.assertIsInstance(d["optics_ground_cm"], int)
        self.assertIn(d["morale"], ("stable", "suppressed", "pinned",
                                    "routed"))
        self.assertIn(d["stance"], ("weapons_free", "hold_fire"))

    def test_enemy_unit_five_keys_only(self):
        foe = next(u for u in self.session.world.units
                   if u.team != 0 and u.alive)
        d = self.session.unit_detail(foe.id)
        self.assertIsNotNone(d)
        self.assertEqual(set(d), {"name", "category", "team", "hp", "hp_max"})
        self.assertEqual(d["team"], foe.team)

    def test_unknown_id_returns_none(self):
        self.assertIsNone(self.session.unit_detail(999999))

    def test_frame_has_no_detailed_fields(self):
        frame = self.session.frame()
        self.assertTrue(frame["units"])
        for entry in frame["units"]:
            self.assertNotIn("elements", entry)
            self.assertNotIn("armor_ke", entry)
            self.assertNotIn("weapons", entry)


if __name__ == "__main__":
    unittest.main()
