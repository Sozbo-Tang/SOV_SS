"""sovs.ai.AgentSquad（四块 agent 班组）测试：角色候选归属 / 1Hz 顺序节拍 /
角色统计与日志 kind / 同 seed 双跑确定性 / 工具 --mode squad 接线。

零模型依赖：FakeEngine 进程内桩（KevClient/LocalKevEngine 鸭子类型同口
choose——只记录入参并按 picker 应答）+ 无 client 纯规则兜底两路都覆盖；
本文件不 import torch、不起端口服务、不起子进程（工具测试进程内直调
main/run，照 tests/test_ai_kev._load_launcher 先例）。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

from sovs.ai import (AgentSquad, air_candidates, enumerate_candidates,
                     split_air_candidates)
from sovs.ai.kev_client import KevChoiceAnswer, KevUnavailableError
from sovs.sim.air import (AircraftInstance, AirState, PHASE_COMBAT,
                          PHASE_DEPLOY, PHASE_SETTLE)
from sovs.sim.air_data import CARD_OBJECTS
from sovs.sim.tick import (DeckSlot, Objective, add_unit, make_unit,
                           make_world, world_tick)
from sovs.sim.types import (AltTier, Armor, DamageType, ElementTemplate,
                            ElementType, MovementClass, TargetDomain,
                            Trajectory, UnitFlag, UnitTemplate, UnitType,
                            WeaponTemplate)

# ── 合成卡（照 tools/kev_game_demo 数值档——锚点服务非平衡档）──

RIFLE_W = WeaponTemplate(
    name="rifle", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    damage=2, salvo=1, aim_time_ticks=5, reload_time_ticks=30, ammo_base=50,
    max_range_cm=120000, dispersion_cm=500, accuracy_base_bp=6000,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    suppression_power=3, reveal_time_ticks=10)
CANNON_W = WeaponTemplate(
    name="cannon", target_mask=TargetDomain.GROUND, damage_type=DamageType.KE,
    pen_min=6, pen_max=9, damage=6, salvo=1, aim_time_ticks=6,
    reload_time_ticks=50, ammo_base=30, max_range_cm=115000,
    dispersion_cm=400, accuracy_base_bp=6200,
    projectile_speed_cm_tick=20000, trajectory=Trajectory.DIRECT,
    blast_radius_cm=500, suppression_power=5, reveal_time_ticks=10)

RIFLE_TPL = UnitTemplate(
    template_id=921, name="rifle plt", category=1, cost=60,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=10,
                                       weapons=(RIFLE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
TANK_TPL = UnitTemplate(
    template_id=923, name="tank", category=2, cost=180,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=15,
        armor_ke=Armor(10, 7, 5, 3), armor_he=Armor(8, 6, 4, 3),
        weapons=(CANNON_W,)),),
    optics_ground_cm=110000, stealth_base=3, speed_tier=2,
    movement_class=MovementClass.TRACK)
# 预备队空降卡（空裁8 投送限定——购卡门恒拒，走运输机 PARATROOP 载荷投放）
PARA_TPL = UnitTemplate(
    template_id=925, name="paratroop plt", category=1, cost=60,
    element_templates=(RIFLE_TPL.element_templates[0],) * 3,
    optics_ground_cm=120000, stealth_base=6, speed_tier=1,
    movement_class=MovementClass.FOOT,
    flags=UnitFlag.DELIVERY_AIRDROP_ONLY)

DECK = ((RIFLE_TPL, 2), (TANK_TPL, 1), (PARA_TPL, 1))
SOUTH, NORTH = (100000, 0), (100000, 100000)


def combat_world(seed: int = 42, *, rich_air: bool = False):
    """实战相位场景：南北 步兵×2+坦克×1 相距 10km 互见；卡组含预备队空降卡。"""
    w = make_world(seed, phase=PHASE_COMBAT, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    for p in w.players:
        p.deck_slots = [DeckSlot(tpl, n) for tpl, n in DECK]
    for team, base_y in ((0, 45000), (1, 55000)):
        for k in range(2):
            add_unit(w, make_unit(w, RIFLE_TPL, team, team,
                                  (100000 - 15000 * k, base_y)))
        add_unit(w, make_unit(w, TANK_TPL, team, team, (100000, base_y)))
    for u in w.units:
        u.spotted_mask = 0b11              # 双方互见（决策链有真实目标可打）
    if rich_air:
        _add_rich_air(w)
    return w


def deploy_world(seed: int = 42):
    """盲部署相位场景（预置两单位——排兵节拍有队形/车道候选可用）。"""
    w = make_world(seed, phase=PHASE_DEPLOY, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    for p in w.players:
        p.deck_slots = [DeckSlot(tpl, n) for tpl, n in DECK]
    add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (90000, 10000)))
    add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (110000, 10000)))
    return w


def _add_rich_air(w):
    """在空飞机全家桶（全队0）：让两角色的空中候选同时在场。

    IL2M 挂弹=strike；PE2 弹尽=rtb；YAK9 低层未交战=engage/cap/climb；
    LI2 载预备队=drop——另有四型呼叫（点数 750 全开）。
    """
    def ac(key, *, ammo=None, cargo=None, alt=AltTier.MID, engage=None):
        tpl = CARD_OBJECTS[key]
        a = AircraftInstance(id=w.next_aircraft_id, team=0, player_index=0,
                             template=tpl, pos=(100000, 30000), alt_tier=alt,
                             hp_current=tpl.hp_max, state=AirState.PATROL,
                             ammo_left=dict(ammo or {}))
        a.paratroop_cargo = cargo
        if engage is not None:
            a.engage_air = engage
        w.next_aircraft_id += 1
        w.aircraft.append(a)

    ac("IL2M", ammo={"BOMB": 2})                 # 角色3：strike
    ac("PE2", ammo={"BOMB": 0})                  # 角色3：rtb
    ac("YAK9", alt=AltTier.LOW, engage=False)    # 角色3：engage/cap/climb
    ac("LI2", ammo={"BOMB": 0}, cargo=PARA_TPL)  # 角色4：drop


# ── 测试桩：KevClient/LocalKevEngine 鸭子类型同口（choose）──

class FakeEngine:
    """记录每次 choose 完整入参；picker(call)→选项名（缺省=首选项）。"""

    def __init__(self, picker=None):
        self.calls = []
        self._picker = picker or (lambda call: next(iter(call["options"])))

    def choose(self, state, question_id, instructions, options):
        call = {"state": state, "qid": question_id,
                "instructions": instructions, "options": dict(options)}
        self.calls.append(call)
        choice = self._picker(call)
        probs = {k: 0.0 for k in options}
        probs[choice] = 1.0
        return KevChoiceAnswer(question_id=question_id, choice=choice,
                               confidence=1.0, probabilities=probs)


class BrokenEngine:
    """恒抛 KevUnavailableError——验证班组降级链（argmax 兜底不中断）。"""

    def choose(self, state, question_id, instructions, options):
        raise KevUnavailableError("engine down (test stub)")


# ── ① 角色候选归属 ──

_RESERVE_PREFIXES = ("call_troop_", "call_supply_", "drop_", "supply_")
_COMBAT_PREFIXES = ("strike_", "cap_", "climb_", "rtb_", "engage_", "break_")


class TestCandidateOwnership(unittest.TestCase):
    """空中 agent 纯作战、预备队 agent 纯投送、地面 agent 零 air_* 呼叫。"""

    @classmethod
    def setUpClass(cls):
        cls.w = combat_world(rich_air=True)

    def _split(self):
        return split_air_candidates(
            air_candidates(self.w, 0, enemy_anchor=NORTH, limit=30))

    def test_split_partitions_all_candidates(self):
        cands = air_candidates(self.w, 0, enemy_anchor=NORTH, limit=30)
        combat, reserve = self._split()
        keys = sorted(c.key for c in cands if c.kind != "wait")
        self.assertEqual(keys, sorted(c.key for c in combat + reserve))
        self.assertNotIn("wait", [c.key for c in combat + reserve])
        self.assertTrue(combat and reserve)      # 两侧都非空（场景自证）

    def test_air_agent_pure_combat(self):
        combat, _ = self._split()
        for c in combat:
            self.assertFalse(c.key.startswith(_RESERVE_PREFIXES), c.key)
            self.assertNotIn(c.kind, ("airdrop", "air_move"), c.kind)
        self.assertTrue(any(c.key.startswith("strike_") for c in combat))
        self.assertTrue(any(c.key.startswith("cap_") for c in combat))
        self.assertTrue(any(c.key.startswith("rtb_") for c in combat))
        self.assertTrue(any(c.key.startswith("call_") for c in combat))

    def test_reserve_agent_pure_delivery(self):
        _, reserve = self._split()
        for c in reserve:
            self.assertFalse(c.key.startswith(_COMBAT_PREFIXES), c.key)
            self.assertNotIn(c.kind, ("strike", "air_patrol", "air_alt",
                                      "air_rtb", "air_engage",
                                      "air_disengage"), c.kind)
        self.assertTrue(any(c.key.startswith("drop_") for c in reserve))
        self.assertFalse([c for c in reserve          # ferry 已裁撤（模型陷阱）
                          if c.key.startswith("ferry_")])
        self.assertTrue(any(c.key.startswith("call_troop_") for c in reserve))
        self.assertTrue(any(c.key.startswith("call_supply_") for c in reserve))

    def test_ground_agent_no_air_calls(self):
        cands = enumerate_candidates(self.w, 0, artillery_issued=set(),
                                     enemy_anchor=NORTH, limit=30)
        for c in cands:
            self.assertFalse(c.kind.startswith("air"), c.kind)
            self.assertFalse(c.key.startswith("call_"), c.key)
        kinds = {c.kind for c in cands}
        self.assertIn("attack", kinds)           # 互见敌在射程内
        self.assertIn("objective", kinds)        # 中央占点无主


# ── ② 1Hz 顺序节拍 ──

class TestSquadSequencer(unittest.TestCase):
    """决策按 地面,空中,预备队,地面,… 循环；每 10 拍恰一次；命令真实入队。"""

    def test_rotation_order_cadence_and_commands(self):
        w = combat_world()
        engine = FakeEngine()
        squad = AgentSquad(0, engine, anchors=(SOUTH, NORTH))
        beat_ticks, queued_beats = [], 0
        for tick in range(65):                    # 0..64：6 个半轮转窗
            n_calls, n_q = len(engine.calls), len(w.command_queue)
            squad.step(w)
            if len(engine.calls) > n_calls:
                beat_ticks.append(tick)
            if len(w.command_queue) > n_q:
                queued_beats += 1
            world_tick(w)
            if w.result is not None:
                break
        squad.close()
        self.assertEqual(beat_ticks,
                         [0, 10, 20, 30, 40, 50, 60])   # 每 10 拍恰一次
        self.assertEqual([c["qid"] for c in engine.calls],
                         ["squad_ground", "squad_air", "squad_reserve"] * 2
                         + ["squad_ground"])
        self.assertEqual(queued_beats, 7)                # 每次决策命令真实入队
        for call in engine.calls:                        # 节拍内选项也按角色归属
            if call["qid"] == "squad_air":
                self.assertFalse(any(k.startswith(_RESERVE_PREFIXES)
                                      for k in call["options"]))
            if call["qid"] == "squad_reserve":
                self.assertFalse(any(k.startswith(_COMBAT_PREFIXES)
                                      for k in call["options"]))

    def test_silent_roles_do_not_stall_rotation(self):
        w = combat_world()
        for p in w.players:
            p.air_points = 0                     # 空中/预备队候选全闭（静默位）
        engine = FakeEngine()
        squad = AgentSquad(0, engine, anchors=(SOUTH, NORTH))
        for _ in range(95):                       # 9 个轮转窗：地面位 0/30/60/90
            squad.step(w)
            world_tick(w)
        squad.close()
        self.assertEqual([c["qid"] for c in engine.calls],
                         ["squad_ground"] * 4)   # 轮转照走：空中/预备队拍静默不占决策

    def test_deploy_phase_keeps_kevplayer_cadence(self):
        w = deploy_world()
        engine = FakeEngine()
        squad = AgentSquad(0, engine, anchors=(SOUTH, NORTH))
        for _ in range(100):
            squad.step(w)
            world_tick(w)
        squad.close()
        # 购卡 %50、排兵错半拍（25/75）；实战角色（ground/air/reserve）不上场
        self.assertEqual([c["qid"] for c in engine.calls],
                         ["squad_purchase", "squad_deploy",
                          "squad_purchase", "squad_deploy"])

    def test_settle_phase_silent(self):
        w = make_world(42, phase=PHASE_SETTLE, size_cm=(200000, 100000))
        engine = FakeEngine()
        squad = AgentSquad(0, engine)
        for _ in range(25):
            squad.step(w)
        squad.close()
        self.assertEqual(engine.calls, [])
        self.assertEqual(w.command_queue, [])


# ── ③ 各角色统计与日志 kind ──

class TestRoleStatsAndLog(unittest.TestCase):
    """kev/兜底分角色计数；日志 kind=deploy|purchase|combat|air|reserve。"""

    def test_kev_stats_per_role(self):
        w = combat_world()
        squad = AgentSquad(0, FakeEngine(), anchors=(SOUTH, NORTH))
        for _ in range(30):
            squad.step(w)
            world_tick(w)
        squad.close()
        rs = squad.role_stats
        self.assertEqual((rs["ground"]["kev"], rs["air"]["kev"],
                          rs["reserve"]["kev"]), (1, 1, 1))
        self.assertEqual(squad.stats["kev"], 3)      # 总量面=分角色面之和
        self.assertEqual(squad.stats["fallback"], 0)

    def test_fallback_stats_and_degradation_chain(self):
        for client in (None, BrokenEngine()):        # 无 client / 服务故障同兜底
            w = combat_world()
            squad = AgentSquad(0, client, anchors=(SOUTH, NORTH))
            queued = 0
            for _ in range(30):
                n_q = len(w.command_queue)
                squad.step(w)
                if len(w.command_queue) > n_q:
                    queued += 1
                world_tick(w)
            squad.close()
            self.assertEqual(squad.stats["kev"], 0)
            self.assertEqual(squad.stats["fallback"], 3)
            self.assertEqual(queued, 3)              # 兜底决策照样发令

    def test_instructions_role_specific(self):
        w = combat_world()
        engine = FakeEngine()
        squad = AgentSquad(0, engine, anchors=(SOUTH, NORTH))
        for _ in range(30):                          # 实战三角色各一轮
            squad.step(w)
            world_tick(w)
        wd = deploy_world()
        for _ in range(76):                          # 部署相位两节拍各两轮
            squad.step(wd)
            world_tick(wd)
        squad.close()
        self.assertEqual({c["qid"] for c in engine.calls},
                         {"squad_ground", "squad_air", "squad_reserve",
                          "squad_purchase", "squad_deploy"})
        by_qid = {c["qid"]: c["instructions"] for c in engine.calls}
        texts = list(by_qid.values())
        self.assertEqual(len(set(texts)), len(texts))          # 句句不同
        self.assertIn("地面指挥官", by_qid["squad_ground"])
        self.assertIn("空中管制官", by_qid["squad_air"])
        self.assertIn("预备队参谋", by_qid["squad_reserve"])
        self.assertIn("排兵布阵官", by_qid["squad_purchase"])
        self.assertIn("排兵布阵官", by_qid["squad_deploy"])

    def test_log_kinds_per_role(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "squad.jsonl")
            wd = deploy_world()
            sd = AgentSquad(0, None, anchors=(SOUTH, NORTH),
                            log=path, label="t")
            for _ in range(76):
                sd.step(wd)
                world_tick(wd)
            sd.close()
            wc = combat_world()
            sc = AgentSquad(0, None, anchors=(SOUTH, NORTH),
                            log=path, label="t")
            for _ in range(30):
                sc.step(wc)
                world_tick(wc)
            sc.close()
            with open(path, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh]
        self.assertEqual([(r["kind"], r["role"]) for r in rows],
                         [("purchase", "deploy"), ("deploy", "deploy"),
                          ("purchase", "deploy"), ("deploy", "deploy"),
                          ("combat", "ground"), ("air", "air"),
                          ("reserve", "reserve")])
        self.assertEqual([r["phase"] for r in rows],
                         ["deploy"] * 4 + ["combat"] * 3)
        self.assertTrue(all(r["source"] == "fallback" for r in rows))
        self.assertTrue(all(r["commands"] for r in rows))     # 决策都落了命令


# ── ④ 同 seed 双跑确定性 ──

def _fingerprint(w) -> str:
    parts = []
    for u in sorted(w.units, key=lambda x: x.id):
        parts.append(f"u{u.id}:t{u.team}:{int(u.alive)}:{u.pos[0]},{u.pos[1]}:"
                     f"{sum(e.hp_current for e in u.elements)}:{u.morale.name}")
    for a in sorted(w.aircraft, key=lambda x: x.id):
        parts.append(f"a{a.id}:t{a.team}:{a.state.name}:{a.pos[0]},{a.pos[1]}:"
                     f"{a.ammo_left.get('BOMB', 0)}:{int(a.paratroop_cargo is not None)}")
    for p in w.players:
        parts.append(f"p{p.index}:{p.points}:{p.air_points}:{p.spawn_serial}:"
                     f"{len(p.spawn_queue)}:{[s.copies_left for s in p.deck_slots]}")
    for o in w.objectives:
        parts.append(f"o{o.id}:{o.owner}")
    parts.append(f"tick{w.tick}:phase{w.phase}")
    return "|".join(parts)


class TestDeterminism(unittest.TestCase):
    """盲部署全程+实战前段（1Hz 轮转 40 拍），同 seed 双跑逐位一致。"""

    def _run(self, seed: int, ticks: int):
        w = make_world(seed, phase=PHASE_DEPLOY, size_cm=(200000, 100000))
        w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
        for p in w.players:
            p.deck_slots = [DeckSlot(tpl, n) for tpl, n in DECK]
        red = AgentSquad(0, None, anchors=(SOUTH, NORTH))
        blue = AgentSquad(1, None, anchors=(SOUTH, NORTH))
        for _ in range(ticks):
            red.step(w)
            blue.step(w)
            world_tick(w)
            if w.result is not None:
                break
        red.close()
        blue.close()
        return _fingerprint(w), red.role_stats, blue.role_stats

    def test_same_seed_double_run_identical(self):
        fp1, rs1, _ = self._run(42, 1000)
        fp2, rs2, _ = self._run(42, 1000)
        self.assertEqual(fp1, fp2)
        self.assertEqual(rs1, rs2)
        # 三实战角色都真实决策过（防止"零决策=平凡一致"的假绿）
        for role in ("ground", "air", "reserve"):
            self.assertGreater(rs1[role]["kev"] + rs1[role]["fallback"], 0,
                               role)


# ── 真模型门修复：Hub 不可达离线回退（kev_local，零 torch 依赖）──

class TestHubOfflineFallback(unittest.TestCase):
    """权重已缓存而 Hub 不可达（Errno 60 类）→ HF_HUB_OFFLINE 离线重试。

    真模型 squad bench 曾在断网环境加载超时退码 2（snapshot_download 向
    Hub 校验 etag 整体超时）；此修复不引入任何网络代码，仅按异常征切换
    hub 的纯缓存解析。判别函数与重试器均可无 torch 导入单测。
    """

    def test_classifier_network_vs_local_errors(self):
        from sovs.ai.kev_local import is_hub_unreachable
        self.assertTrue(is_hub_unreachable(TimeoutError("timed out")))
        self.assertTrue(is_hub_unreachable(ConnectionError("refused")))
        self.assertTrue(is_hub_unreachable(OSError(60, "Operation timed out")))
        self.assertTrue(is_hub_unreachable(OSError(61, "Connection refused")))
        try:                              # 包装链：外层无网络征、内层有
            raise RuntimeError("resolve_run 失败") from OSError(
                60, "Operation timed out")
        except RuntimeError as e:
            self.assertTrue(is_hub_unreachable(e))
        self.assertFalse(is_hub_unreachable(
            FileNotFoundError(2, "No such file or directory")))
        self.assertFalse(is_hub_unreachable(ValueError("bad dtype")))

    def test_load_predictor_retries_offline_on_network_error(self):
        import sovs.ai.kev_local as kl
        keys = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
        saved = {k: os.environ.get(k) for k in keys}
        try:
            calls = []

            class FlakyPredictor:          # 首次网络超时，重试（离线）成功
                def __init__(self, run, dev, opts):
                    calls.append(os.environ.get("HF_HUB_OFFLINE"))
                    if len(calls) == 1:
                        raise OSError(60, "Operation timed out")

            obj = kl.LocalKevEngine._load_predictor("r", "cpu", None,
                                                    FlakyPredictor)
            self.assertIsInstance(obj, FlakyPredictor)
            self.assertEqual(calls, [None, "1"])     # 恰两次：在线→离线
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")

            os.environ["HF_HUB_OFFLINE"] = "1"       # 已离线：不再重试
            calls.clear()

            class AlwaysDown:
                def __init__(self, run, dev, opts):
                    calls.append(1)
                    raise OSError(60, "Operation timed out")

            with self.assertRaises(OSError):
                kl.LocalKevEngine._load_predictor("r", "cpu", None, AlwaysDown)
            self.assertEqual(calls, [1])

            os.environ.pop("HF_HUB_OFFLINE")         # 非网络错误：不切离线
            calls.clear()

            class MissingWeights:
                def __init__(self, run, dev, opts):
                    calls.append(1)
                    raise FileNotFoundError(2, "No such file or directory")

            with self.assertRaises(FileNotFoundError):
                kl.LocalKevEngine._load_predictor("r", "cpu", None,
                                                  MissingWeights)
            self.assertEqual(calls, [1])
            self.assertNotIn("HF_HUB_OFFLINE", os.environ)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


# ── 工具 --mode squad 接线（进程内直调——照 tests/test_ai_kev 先例）──

def _load_tool(name: str):
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", name)
    spec = importlib.util.spec_from_file_location(
        name.replace(".py", "_tool"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestToolsSquadMode(unittest.TestCase):
    """bench：fallback+squad 走 PASS；demo：squad 整段跑完且日志含 reserve。"""

    def test_bench_squad_mode_passes(self):
        mod = _load_tool("kev_bench_1hz.py")
        with tempfile.TemporaryDirectory() as td:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mod.main(["--engine", "fallback", "--mode", "squad",
                               "--decisions", "6", "--pace", "0.05",
                               "--warmup", "1",
                               "--log", os.path.join(td, "b.jsonl")])
            out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)
        self.assertIn("AgentSquad", out)
        self.assertIn("角色决策", out)

    def test_demo_squad_mode_runs_and_logs_reserve(self):
        mod = _load_tool("kev_game_demo.py")
        with tempfile.TemporaryDirectory() as td:
            log_path = os.path.join(td, "demo.jsonl")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mod.run(seed=7, max_ticks=640, url=None, both_kev=False,
                             log_path=log_path, api_key=None, mode="squad")
            out = buf.getvalue()
            with open(log_path, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh]
        self.assertEqual(rc, 0)
        self.assertIn("AgentSquad", out)
        self.assertIn("对局结束", out)
        kinds = {r["kind"] for r in rows}
        self.assertIn("reserve", kinds)         # 640 拍=部署600+实战40：轮到预备队
        self.assertIn("combat", kinds)


class TestConfidenceGate(unittest.TestCase):
    """min_top_prob 置信度门控：模型首选概率低于阈值→argmax 兜底。"""

    def test_gate_routes_flat_guesses_to_argmax(self):
        from tests.test_ai_fullflow import world_at
        from tests.test_ai_kev import RIFLE_TPL as RT

        class FlatEngine:                      # 概率平坦（p=0.25×4——瞎猜画像）
            def choose(self, state, qid, instructions, options):
                p = 1.0 / len(options)
                return KevChoiceAnswer(qid, next(iter(options)), 0.0,
                                       {k: p for k in options})

        anchors = ((100000, 0), (100000, 100000))
        w = world_at(PHASE_COMBAT)
        add_unit(w, make_unit(w, RT, 0, 0, (100000, 40000)))
        w.command_queue.clear()
        ai = AgentSquad(0, FlatEngine(), anchors=anchors, squad_every=1,
                        min_top_prob=0.60)     # 阈值 0.60 > 平坦 1/2 → 兜底
        ai.step(w)
        self.assertEqual(ai.stats["fallback"], 1)
        self.assertEqual(ai.stats["kev"], 0)
        w2 = world_at(PHASE_COMBAT)
        add_unit(w2, make_unit(w2, RT, 0, 0, (100000, 40000)))
        w2.command_queue.clear()
        ai2 = AgentSquad(0, FlatEngine(), anchors=anchors, squad_every=1,
                         min_top_prob=0.45)    # 阈值 0.45 < 平坦 1/2 → 模型放行
        ai2.step(w2)
        self.assertEqual(ai2.stats["kev"], 1)


if __name__ == "__main__":
    unittest.main()
