"""FE-T02 状态帧导出测试：帧头契约 / 迷雾三视角 / 不截断 / 序列化值域 / 口径一致性。

覆盖 FE-01 §5 FE-T02 验收标准的全部可测项：
- 迷雾三档各一单测——None 视角=双方全量、team0/team1 视角=未侦察敌单位
  不出现（构造已 spotted/未 spotted 夹具）；
- 帧头断言（tick/phase/view/schema_version）；
- 单位数超 16 不截断（公共契约；16 上限=AI 摘要档行为，对照断言留在 AI 层）；
- json 序列化往返 + 递归值域 ∈ {int,str,bool,None,list,dict}、显式禁 float
  ——objectives.owner=None（types.py Objective「owner None=无主」）与
  spotted/suppressed/moving 等 bool 是合法值；
- state_view 与 state_frame 迷雾口径一致性（同 world 同视角可见敌集相等）；
- 整米化收敛对照——公共帧 pos_cm 保持 int cm，AI 摘要档 pos_m 整米化
  （TECH-00 §12.11 拍板口径的机器断言）。
"""
from __future__ import annotations

import json
import unittest

from sovs.ai.state_view import situation_brief
from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY, AirState, AircraftInstance
from sovs.sim.air_data import CARD_OBJECTS
from sovs.sim.state_frame import state_frame
from sovs.sim.tick import (DeckSlot, Objective, Projectile, Settlement,
                           add_unit, make_unit, make_world)
from sovs.sim.types import (Building, DamageType, ElementTemplate,
                            ElementType, FireMission, FireMissionForm,
                            FormationShape, MoraleState,
                            MovementClass, MoveMode, SmokeZone, Stance,
                            Trajectory, UnitFlag, UnitTemplate, UnitType)
from tests.test_ai_kev import RIFLE_W, RIFLE_TPL, TANK_TPL

# 预备队空降卡（照 tests/test_ai_fullflow.PARA_TPL——空裁8 投送限定旗）
PARA_TPL = UnitTemplate(
    template_id=922, name="paratroop plt", category=1, cost=60,
    element_templates=(
        ElementTemplate(element_type=ElementType.SQUAD,
                        unit_type=UnitType.INFANTRY, hp_max=10,
                        weapons=(RIFLE_W,)),) * 3,
    optics_ground_cm=120000, stealth_base=6, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.DELIVERY_AIRDROP_ONLY)


def fog_world(*, phase: int = PHASE_COMBAT, tick: int = 77):
    """迷雾夹具：队0 两单位、队1 两单位——敌 a 仅被队0 发现、敌 b 仅被
    队1 发现、队0 的 c 仅被队1 发现（已 spotted/未 spotted 两态俱备）。"""
    w = make_world(7, phase=phase, tick=tick, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    w.objectives.append(Objective(id=2, pos=(150000, 50000),
                                  radius_cm=4000, owner=0))
    mine = add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (50000, 30000)))
    c = add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (60000, 30000)))
    a = add_unit(w, make_unit(w, TANK_TPL, 1, 1, (150000, 30000)))
    b = add_unit(w, make_unit(w, TANK_TPL, 1, 1, (150000, 60000)))
    a.spotted_mask |= 1 << 0          # 仅被队0 发现
    b.spotted_mask |= 1 << 1          # 仅被队1 发现
    c.spotted_mask |= 1 << 1          # 队0 的 c 被队1 发现
    mine.id, c.id, a.id, b.id = 1, 2, 3, 4   # 显式定 id 便断言（add_unit 自增亦确定）
    return w


def mk_air(w, key: str, *, team: int, state=AirState.PATROL, spotted=0,
           ammo=None, cargo=None, pos=(100000, 50000)):
    """飞机夹具（照 tests/test_ai_fullflow.mk_aircraft——真卡模板）。"""
    tpl = CARD_OBJECTS[key]
    a = AircraftInstance(id=w.next_aircraft_id, team=team, player_index=team,
                         template=tpl, pos=pos, alt_tier=tpl.alt_ceiling,
                         hp_current=tpl.hp_max, state=state)
    w.next_aircraft_id += 1
    a.ammo_left = dict(ammo or {})
    a.paratroop_cargo = cargo
    a.spotted_mask = spotted
    w.aircraft.append(a)
    return a


class TestFrameHeader(unittest.TestCase):
    """帧头契约③：schema_version/tick/phase/view 每帧必带。"""

    def test_header_fields_all_views(self):
        for pi, view in ((None, None), (0, 0), (1, 1)):
            with self.subTest(view=pi):
                f = state_frame(fog_world(), pi)
                self.assertEqual(f["schema_version"], "1.1")  # GP-01 §4 ①段帧档扩面（1.0→1.1）
                self.assertEqual(f["tick"], 77)
                self.assertEqual(f["phase"], "combat")
                if view is None:
                    self.assertIsNone(f["view"])
                else:
                    self.assertEqual(f["view"], view)
                self.assertEqual(f["map_cm"], [200000, 100000])

    def test_header_phase_names(self):
        self.assertEqual(state_frame(fog_world(phase=PHASE_DEPLOY), 0)["phase"],
                         "deploy")
        self.assertEqual(state_frame(fog_world(), 0)["phase"], "combat")


class TestFogOfWar(unittest.TestCase):
    """迷雾三档：None=裁判全知、队号=spotted_mask 位裁剪。"""

    def test_referee_view_sees_both_sides(self):
        f = state_frame(fog_world(), None)
        # 双方全量：4 单位全在（含互未侦察的）
        self.assertEqual(len(f["units"]), 4)
        self.assertEqual({u["team"] for u in f["units"]}, {0, 1})
        self.assertEqual(len(f["players"]), 2)     # 双方玩家经济全导出

    def test_team0_view_fog(self):
        f = state_frame(fog_world(), 0)
        # 己方全量（mine=1、c=2）+ 敌方仅被队0 发现的 a=3；b=4（仅被队1 发现）不出现
        self.assertEqual({u["id"] for u in f["units"]}, {1, 2, 3})
        # 敌方玩家经济不导出（私有信息边界）
        self.assertEqual([p["index"] for p in f["players"]], [0])

    def test_team1_view_fog(self):
        f = state_frame(fog_world(), 1)
        # 己方全量（a=3、b=4）+ 敌方仅被队1 发现的 c=2；mine=1（mask=0）不出现
        self.assertEqual({u["id"] for u in f["units"]}, {2, 3, 4})
        self.assertEqual(len([u for u in f["units"] if u["team"] == 1]), 2)
        self.assertEqual([p["index"] for p in f["players"]], [1])

    def test_fog_aircraft_same_mask_rule(self):
        w = fog_world()
        mk_air(w, "YAK9", team=0)
        mk_air(w, "FW190A", team=1, spotted=1 << 0)   # 被队0 发现
        mk_air(w, "FW190A", team=1, spotted=0)        # 未被任何队发现
        f0 = state_frame(w, 0)
        self.assertEqual(len(f0["aircraft"]), 2)      # 己方1+可见敌机1
        fn = state_frame(w, None)
        self.assertEqual(len(fn["aircraft"]), 3)      # 裁判全知=全部

    def test_visible_enemy_never_includes_unspotted(self):
        """夹具双向核对：任一队视角下，帧内敌单位 spotted_mask 必含本队位。"""
        w = fog_world()
        for pi in (0, 1):
            f = state_frame(w, pi)
            for u in f["units"]:
                if u["team"] != f["view"]:
                    self.assertTrue((next(x for x in w.units
                                          if x.id == u["id"]).spotted_mask
                                     >> f["view"]) & 1)


class TestNoTruncation(unittest.TestCase):
    """契约②：不带 max_units 截断（16 上限是 AI 摘要档行为）。"""

    def test_over_16_units_not_truncated(self):
        w = make_world(9, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        for i in range(20):                          # 己方 20
            add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (50000 + i * 100, 30000)))
        for i in range(3):                           # 被队0 发现的敌 3
            u = add_unit(w, make_unit(w, TANK_TPL, 1, 1,
                                      (150000 + i * 100, 30000)))
            u.spotted_mask |= 1 << 0
        f = state_frame(w, 0)
        self.assertEqual(len(f["units"]), 23)        # 全量 23>16 不截断
        # 对照：AI 摘要档 16 上限行为保留在 AI 层（每方各截 16 → 16+3=19 中己方 16）
        brief = situation_brief(w, 0)
        self.assertEqual(brief["我方"]["单位数"], 16)
        self.assertEqual(len(brief["我方"]["单位列表"]), 16)


class TestSerialization(unittest.TestCase):
    """stdlib json 直序列化 + 值域纪律（禁 float；None/bool 合法）。"""

    @staticmethod
    def rich_world():
        """全字段夹具：单位/飞机（含载伞）/占点（含无主）/玩家卡组/烟区/
        弹丸/建筑/结算——值域断言的覆盖面。"""
        w = fog_world()
        w.players[0].deck_slots = [DeckSlot(RIFLE_TPL, 2),
                                   DeckSlot(PARA_TPL, 3)]
        mk_air(w, "YAK9", team=0, ammo={"BOMB": 2}, cargo=PARA_TPL)
        mk_air(w, "FW190A", team=1, spotted=1 << 0, ammo={"STRAFE": 16})
        w.smoke_zones.append(SmokeZone(center=(120000, 50000),
                                       ttl_ticks=300, radius_cm=2500))
        w.projectiles.append(Projectile(
            shooter=None, weapon=None, damage_type=DamageType.HE, damage=5,
            blast_cm=400, pos=(100000, 50000), dest=(100500, 50000),
            speed_cm_tick=5000, trajectory=Trajectory.BALLISTIC,
            hit_target=None, will_hit=False))
        w.buildings.append(Building(id=1, pos=(100000, 40000),
                                    hp=80, garrison_slots=4))
        w.result = Settlement(winner=1, obj_counts=(1, 3),
                              unit_scores=(120, 200), hp_totals=(15, 30))
        return w

    def assert_jsonable(self, node):
        self.assertNotIsInstance(node, float,
                                 f"float 出现在帧值域: {node!r}")
        if node is None or isinstance(node, (bool, int, str)):
            return
        if isinstance(node, list):
            for x in node:
                self.assert_jsonable(x)
            return
        if isinstance(node, dict):
            for k, v in node.items():
                self.assertIsInstance(k, str)
                self.assert_jsonable(v)
            return
        raise self.failureException(f"帧值域外类型: {type(node)!r} ({node!r})")

    def test_json_roundtrip_and_value_domain(self):
        for pi in (None, 0, 1):
            with self.subTest(view=pi):
                f = state_frame(self.rich_world(), pi)
                self.assert_jsonable(f)
                text = json.dumps(f)                 # stdlib 直序列化成功
                self.assertEqual(json.loads(text), f)  # 往返深度相等

    def test_objectives_owner_none_and_bools_are_legal_values(self):
        f = state_frame(self.rich_world(), 0)
        self.assertIs(f["objectives"][0]["owner"], None)   # None=无主 合法
        u = f["units"][0]
        for k in ("moving", "suppressed", "mounted", "garrisoned", "towed"):
            self.assertIsInstance(u[k], bool, k)


class TestFireMissionSummary(unittest.TestCase):
    """units[].fire_mission 判别摘要（battle.png 复检①「炮击目标标记不可辨」
    修复的数据面——2026-10-12 帧档 1.1 加键，向后兼容不 bump）。

    口径：己方单位导出 form/point/line/ammo 判别键；敌方即使 spotted 也不导出
    （敌方炮击目标=情报私有，不随迷雾 spotted 位泄露）；裁判全知（view=None）
    全量。None=无任务。
    """

    def test_own_point_mission_exported(self):
        w = fog_world()
        gun = next(u for u in w.units if u.id == 1)
        gun.fire_mission = FireMission(form=FireMissionForm.POINT,
                                       target_point=(100000, 80000))
        e = next(u for u in state_frame(w, 0)["units"] if u["id"] == 1)
        self.assertEqual(e["fire_mission"], {"form": "point",
                                             "point": [100000, 80000],
                                             "line": None, "ammo": "HE"})

    def test_own_creep_line_and_smoke_ammo(self):
        w = fog_world()
        gun = next(u for u in w.units if u.id == 1)
        gun.fire_mission = FireMission(
            form=FireMissionForm.CREEP,
            target_line=((100000, 78000), (115000, 88000)),
            ammo="SMOKE", creep_speed_cm_tick=300)
        e = next(u for u in state_frame(w, 0)["units"] if u["id"] == 1)
        self.assertEqual(e["fire_mission"]["form"], "creep")
        self.assertEqual(e["fire_mission"]["line"],
                         [[100000, 78000], [115000, 88000]])
        self.assertEqual(e["fire_mission"]["ammo"], "SMOKE")

    def test_no_mission_is_none(self):
        f = state_frame(fog_world(), 0)
        self.assertTrue(all(u["fire_mission"] is None for u in f["units"]))

    def test_spotted_enemy_mission_not_leaked(self):
        """被己方发现的敌单位条目在场但 fire_mission 恒 None（情报私有边界）。"""
        w = fog_world()
        foe = next(u for u in w.units if u.id == 3)      # 敌 a=已 spotted
        foe.fire_mission = FireMission(form=FireMissionForm.POINT,
                                       target_point=(50000, 30000))
        f = state_frame(w, 0)
        e = next(u for u in f["units"] if u["id"] == 3)
        self.assertIsNone(e["fire_mission"])
        # 裁判全知（view=None）=全量导出（观战器面）
        fr = state_frame(w, None)
        er = next(u for u in fr["units"] if u["id"] == 3)
        self.assertEqual(er["fire_mission"]["form"], "point")

    def test_summary_value_domain(self):
        """摘要在帧值域内（int/str/None/list/dict——禁 float）。"""
        import json
        w = fog_world()
        gun = next(u for u in w.units if u.id == 1)
        gun.fire_mission = FireMission(form=FireMissionForm.LINE,
                                       target_line=((1, 2), (3, 4)))
        f = state_frame(w, 0)
        json.dumps(f)                                   # 直序列化成功


class TestConsistencyWithStateView(unittest.TestCase):
    """迷雾口径一致性：state_view 摘要在 state_frame 帧之上生成（单实现）。"""

    def test_same_visible_enemy_set_both_views(self):
        w = fog_world()
        for pi in (0, 1):
            with self.subTest(view=pi):
                f = state_frame(w, pi)
                brief = situation_brief(w, pi)
                self.assertEqual(
                    {u["id"] for u in f["units"] if u["team"] != f["view"]},
                    {u["id"] for u in brief["可见敌军"]["单位列表"]})


class TestFieldSpot(unittest.TestCase):
    """全量字段档抽查：pos_cm 精度 / deck 余份 / 结算 / 公开实体。"""

    def test_unit_pos_keeps_cm_precision_vs_ai_brief(self):
        """整米化收敛对照：公共帧 int cm，AI 摘要档整米化（TECH-00 §12.11）。"""
        w = make_world(3, phase=PHASE_COMBAT)
        add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (50123, 30234)))
        f = state_frame(w, 0)
        self.assertEqual(f["units"][0]["pos_cm"], [50123, 30234])   # cm 原值
        self.assertEqual(situation_brief(w, 0)["我方"]["单位列表"][0]["pos_m"],
                         [501, 302])                                # 整米化在 AI 档

    def test_unit_entry_full_fields(self):
        w = fog_world()
        u = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (70000, 30000)))
        u.stance = Stance.HOLD_FIRE
        u.morale = MoraleState.PINNED
        u.move_mode = MoveMode.ATTACK
        u.formation_shape = FormationShape.WEDGE
        e = state_frame(w, 0)["units"][-1]
        self.assertEqual(e["team"], 0)
        self.assertEqual(e["category"], 2)
        self.assertEqual(e["name"], "tank")
        self.assertEqual(e["stance"], "hold_fire")
        self.assertEqual(e["morale"], "pinned")
        self.assertEqual(e["mode"], "attack")
        self.assertEqual(e["formation"], "wedge")
        self.assertEqual(e["hp_max"], 15)
        self.assertIsInstance(e["ammo_pct"], int)

    def test_aircraft_entry_fields(self):
        w = TestSerialization.rich_world()
        f = state_frame(w, 0)
        mine = next(a for a in f["aircraft"] if a["team"] == 0)
        self.assertEqual(mine["ammo"], {"BOMB": 2})
        self.assertEqual(mine["paratroop"], PARA_TPL.template_id)  # 载伞=卡 id
        self.assertEqual(mine["state"], "patrol")
        self.assertFalse(mine["spotted"])                # 未见报（未被对方发现）
        foe = next(a for a in f["aircraft"] if a["team"] != 0)
        self.assertTrue(foe["spotted"])

    def test_players_deck_slots(self):
        f = state_frame(TestSerialization.rich_world(), 0)
        p = f["players"][0]
        self.assertEqual(p["points"], 1000)
        self.assertEqual([(s["template_id"], s["copies_left"], s["airdrop"])
                          for s in p["deck"]],
                         [(RIFLE_TPL.template_id, 2, False),
                          (PARA_TPL.template_id, 3, True)])

    def test_result_three_level_evidence(self):
        f = state_frame(TestSerialization.rich_world(), None)
        self.assertEqual(f["result"], {
            "winner": 1, "obj_counts": [1, 3],
            "unit_scores": [120, 200], "hp_totals": [15, 30]})

    def test_result_none_before_settle(self):
        self.assertIsNone(state_frame(fog_world(), 0)["result"])

    def test_public_entities_all_views(self):
        """占点/烟区/弹丸/建筑=公开信息：三视角下同值全量。"""
        w = TestSerialization.rich_world()
        frames = [state_frame(w, pi) for pi in (None, 0, 1)]
        for key in ("objectives", "smoke_zones", "projectiles", "buildings",
                    "result"):
            with self.subTest(key=key):
                self.assertEqual(frames[0][key], frames[1][key])
                self.assertEqual(frames[0][key], frames[2][key])
        self.assertEqual(frames[0]["smoke_zones"],
                         [{"pos_cm": [120000, 50000], "radius_cm": 2500,
                           "ttl_ticks": 300}])
        self.assertEqual(frames[0]["projectiles"][0]["type"], "he")
        self.assertEqual(frames[0]["buildings"][0]["slots_free"], 4)
        self.assertIs(frames[0]["objectives"][0]["owner"], None)
        self.assertEqual(frames[0]["objectives"][1]["owner"], 0)


class TestCapsSummary(unittest.TestCase):
    """units[].caps 命令能力位（B3 修复块 2026-10-13——命令格三态过滤数据面）。

    口径：己方全键（squad/smoke/reverse/ambush/sniper/seats/deploy_gun/
    indirect/tow/transport/radar——值域 bool/int；radar=对空资格位，终审第四批
    2026-10-13 加键——帧 1.1 加键不 bump 口径）；敌方条目**无 caps 键**（敌方
    能力=对方私有情报，fire_mission 同款边界）；裁判全知（view=None）全量。
    """

    def test_own_caps_full_keys_and_domain(self):
        w = fog_world()
        f = state_frame(w, 0)
        own = next(u for u in f["units"] if u["team"] == 0)
        self.assertEqual(set(own["caps"]), {
            "squad", "smoke", "reverse", "ambush", "sniper", "seats",
            "deploy_gun", "indirect", "tow", "transport", "radar"})
        for k, v in own["caps"].items():
            self.assertIsInstance(v, (bool, int), k)

    def test_enemy_entries_have_no_caps_key(self):
        w = fog_world()
        for pi in (0, 1):
            f = state_frame(w, pi)
            for u in f["units"]:
                if u["team"] != f["view"]:
                    self.assertNotIn("caps", u)

    def test_referee_sees_caps_for_both_sides(self):
        w = fog_world()
        f = state_frame(w, None)
        self.assertTrue(all("caps" in u for u in f["units"]))

    def test_caps_reflect_engine_gate_predicates(self):
        """判据与引擎真实门同源：SQUAD 元素位/曲射 mode_set 位/倒车 bp/
        对空资格位（radar=tick._aa_eligible 同式，终审第四批）。"""
        from tests.test_p1_mechanics import _aa_tpl
        w = fog_world()
        flak = add_unit(w, make_unit(w, _aa_tpl(), 0, 0, (80000, 30000)))
        tank = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (70000, 30000)))
        f = state_frame(w, 0)
        rifle = next(u for u in f["units"] if u["id"] == 1)   # RIFLE_TPL 班卡
        self.assertTrue(rifle["caps"]["squad"])
        self.assertFalse(rifle["caps"]["indirect"])
        own_tank = next(u for u in f["units"] if u["id"] == tank.id)
        self.assertFalse(own_tank["caps"]["squad"])           # 载具无班元素
        self.assertTrue(own_tank["caps"]["reverse"])          # TRACK 类倒车 bp>0
        self.assertFalse(rifle["caps"]["reverse"])            # FOOT 类恒 0
        own_flak = next(u for u in f["units"] if u["id"] == flak.id)
        self.assertTrue(own_flak["caps"]["radar"])            # AIR 弹 mask+对空光学
        self.assertFalse(rifle["caps"]["radar"])
        self.assertFalse(own_tank["caps"]["radar"])


class TestAircraftCapabilityKeys(unittest.TestCase):
    """aircraft[] 机型能力位（B3：alt_ceiling/can_afterburner/can_decoy）。"""

    def test_yak9_capability_bits(self):
        w = fog_world()
        mk_air(w, "YAK9", team=0)
        a = state_frame(w, 0)["aircraft"][0]
        self.assertEqual(a["alt_ceiling"], "high")     # air.py 模板实测
        self.assertTrue(a["can_afterburner"])
        self.assertTrue(a["can_decoy"])
        self.assertIsInstance(a["decoy_left"], int)

    def test_po2_single_tier_no_caps(self):
        w = fog_world()
        mk_air(w, "PO2", team=0)
        a = state_frame(w, 0)["aircraft"][0]
        self.assertEqual(a["alt_ceiling"], "low")
        self.assertFalse(a["can_afterburner"])
        self.assertFalse(a["can_decoy"])


class TestMovePathExport(unittest.TestCase):
    """units[].move_path/queued（B4 修复块 2026-10-13——真实路线呈现数据面）。

    口径：己方导出剩余航点+排队令航点（issue_move 写点直读）；敌方=移动意图
    私有情报恒 []；值域 list[list[int]]（json 往返深度相等）。
    """

    def test_own_move_path_and_queued_exported(self):
        from sovs.sim.movement import issue_move
        from sovs.sim.types import MoveCmd
        from sovs.sim.tables import CONFIG
        w = make_world(73, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        u = add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (50000, 30000)))
        issue_move(w, CONFIG, MoveCmd(unit=u,
                                      path=[(60000, 30000), (70000, 30000)]))
        issue_move(w, CONFIG, MoveCmd(unit=u, path=[(80000, 30000)],
                                      queue=True))          # Shift 排队第二令
        f = state_frame(w, 0)
        e = next(x for x in f["units"] if x["id"] == u.id)
        self.assertEqual(e["move_path"], [[60000, 30000], [70000, 30000]])
        self.assertNotEqual(e["move_path"][0], e["pos_cm"])  # 首点≠当前位置
        self.assertEqual(e["queued"], [[[80000, 30000]]])    # 第二令航点
        json.dumps(f)                                        # 值域可序列化

    def test_enemy_move_intent_not_leaked(self):
        from sovs.sim.movement import issue_move
        from sovs.sim.types import MoveCmd
        from sovs.sim.tables import CONFIG
        w = make_world(74, phase=PHASE_COMBAT, size_cm=(200000, 100000))
        mine = add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (50000, 30000)))
        issue_move(w, CONFIG, MoveCmd(unit=mine, path=[(60000, 30000)]))
        mine.spotted_mask |= 1 << 1                          # 被队1发现（帧在场）
        foe_view = state_frame(w, 1)
        e = next(x for x in foe_view["units"] if x["id"] == mine.id)
        self.assertEqual(e["move_path"], [])                 # 敌视角恒 []
        self.assertEqual(e["queued"], [])
        ref_view = state_frame(w, None)                      # 裁判全知全量
        er = next(x for x in ref_view["units"] if x["id"] == mine.id)
        self.assertEqual(er["move_path"], [[60000, 30000]])

    def test_idle_unit_empty_lists(self):
        w = fog_world()
        for u in state_frame(w, 0)["units"]:
            self.assertEqual(u["move_path"], [])
            self.assertEqual(u["queued"], [])


if __name__ == "__main__":
    unittest.main()
