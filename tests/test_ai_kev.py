"""sovs.ai（Kev 人机玩家层）测试：协议客户端 / 动作枚举 / 播放器全链路 / 兜底与确定性。

mock 服务端用 stdlib http.server 起在线程内——真实 HTTP 往返（urllib 栈全覆盖），
零第三方依赖、零模型依赖；真实 kev.serve 的联测按环境手动跑（tools/kev_serve.py
--start + tools/kev_game_demo.py --url）。启动器测试为进程内直调 main(argv)
（importlib 从 tools/ 路径装载）——不起子进程。
"""
from __future__ import annotations

import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sovs.ai import (KevClient, KevPlayer, KevUnavailableError,
                     enumerate_candidates, purchase_candidates,
                     situation_brief)
from sovs.ai.actions import build_commands
from sovs.sim.air import PHASE_COMBAT, PHASE_DEPLOY
from sovs.sim.tick import (AttackCmd, DeckSlot, MoveCmd, Objective,
                           PurchaseCmd, add_unit, make_unit, make_world,
                           world_tick)
from sovs.sim.types import (Armor, DamageType, ElementTemplate, ElementType,
                            Mode, MovementClass, TargetDomain, Trajectory,
                            UnitTemplate, UnitType, WeaponTemplate)

# ── 合成卡（照 tests/test_fullgame_acceptance 数值档——锚点服务非平衡档）──

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
GUN_W = WeaponTemplate(
    name="he gun", target_mask=TargetDomain.GROUND, damage_type=DamageType.HE,
    pen_min=6, pen_max=6, damage=5, blast_radius_cm=4000, salvo=2,
    aim_time_ticks=8, reload_time_ticks=60, ammo_base=40,
    max_range_cm=110000, dispersion_cm=800, accuracy_base_bp=5500,
    projectile_speed_cm_tick=5000, trajectory=Trajectory.BALLISTIC,
    suppression_power=8, reveal_time_ticks=10)

RIFLE_TPL = UnitTemplate(
    template_id=901, name="rifle plt", category=1, cost=60,
    element_templates=(ElementTemplate(element_type=ElementType.SQUAD,
                                       unit_type=UnitType.INFANTRY, hp_max=10,
                                       weapons=(RIFLE_W,)),),
    optics_ground_cm=120000, stealth_base=5, speed_tier=1,
    movement_class=MovementClass.FOOT)
TANK_TPL = UnitTemplate(
    template_id=903, name="tank", category=2, cost=180,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=15,
        armor_ke=Armor(10, 7, 5, 3), armor_he=Armor(8, 6, 4, 3),
        weapons=(CANNON_W,)),),
    optics_ground_cm=110000, stealth_base=3, speed_tier=2,
    movement_class=MovementClass.TRACK)
GUN_TPL = UnitTemplate(
    template_id=902, name="assault gun", category=3, cost=150,
    element_templates=(ElementTemplate(
        element_type=ElementType.GUN, unit_type=UnitType.MECH, hp_max=12,
        armor_ke=Armor(8, 5, 3, 2), armor_he=Armor(6, 4, 3, 2),
        weapons=(GUN_W,)),),
    optics_ground_cm=120000, stealth_base=3, speed_tier=2,
    movement_class=MovementClass.TRACK,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))

DECK = ((RIFLE_TPL, 2), (TANK_TPL, 1), (GUN_TPL, 1))
SOUTH, NORTH = (100000, 0), (100000, 100000)


def demo_world(seed: int = 42, *, phase: int = PHASE_DEPLOY):
    w = make_world(seed, phase=phase, size_cm=(200000, 100000))
    w.objectives.append(Objective(id=1, pos=(100000, 50000), radius_cm=5000))
    for p in w.players:
        p.deck_slots = [DeckSlot(tpl, n) for tpl, n in DECK]
    return w


# ── mock kev.serve（/v1/systemone；mode 决定应答策略）──

class MockKevHandler(BaseHTTPRequestHandler):
    mode = "first"          # first=选首选项 | fixed:XXX=指定选项 | illegal=选项外 | bad=500
    last_body: dict = {}

    def do_POST(self):  # noqa: N802（http.server 约定名）
        if self.path != "/v1/systemone":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).last_body = body
        qid, q = next(iter(body.get("questions", {}).items()))
        if self.mode == "bad":
            self.send_error(500, "mock boom")
            return
        if q["type"] == "noul":                        # ping 探活路径
            ans = {"type": "noul", "noul": 0.5}
            criteria = []
        else:
            criteria = list(q["criteria"] or {})
            if self.mode.startswith("fixed:"):
                choice = self.mode.split(":", 1)[1]
            elif self.mode == "illegal":
                choice = "no_such_option"
            else:
                choice = criteria[0]
            ans = {"type": "choice", "choice": choice, "confidence": 0.5,
                   "probabilities": {k: round(1.0 / len(criteria), 4)
                                     for k in criteria}}
        resp = json.dumps({"model": body.get("model", "kev-latest"),
                           "answers": {qid: ans}, "usage": {},
                           "latency_ms": 1}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *args):  # 静默（测试输出不刷屏）
        pass


class MockKevServer:
    """线程内 mock 服务：with MockKevServer() as s: KevClient(s.url)..."""

    def __init__(self, mode: str = "first"):
        MockKevHandler.mode = mode
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), MockKevHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()


# ── 客户端协议层 ──

class TestKevClient(unittest.TestCase):
    def test_choose_roundtrip_and_wire_format(self):
        with MockKevServer("first") as s:
            c = KevClient(s.url)
            ans = c.choose({"k": 1}, "act", "选一个",
                           {"a": "描述A", "b": "描述B"})
            self.assertEqual(ans.choice, "a")
            self.assertEqual(ans.confidence, 0.5)
            self.assertIn("a", ans.probabilities)
            body = MockKevHandler.last_body
            self.assertEqual(body["model"], "kev-latest")
            self.assertEqual(set(body["questions"]), {"act"})
            q = body["questions"]["act"]
            self.assertEqual(q["type"], "choice")
            self.assertEqual(q["criteria"], {"a": "描述A", "b": "描述B"})
            self.assertEqual(body["state"], {"k": 1})

    def test_choose_fixed_option(self):
        with MockKevServer("fixed:b") as s:
            ans = KevClient(s.url).choose("s", "q", "i", {"a": None, "b": None})
            self.assertEqual(ans.choice, "b")

    def test_illegal_choice_raises(self):
        with MockKevServer("illegal") as s:
            with self.assertRaises(KevUnavailableError):
                KevClient(s.url).choose("s", "q", "i", {"a": None})

    def test_http_500_raises(self):
        with MockKevServer("bad") as s:
            with self.assertRaises(KevUnavailableError):
                KevClient(s.url).choose("s", "q", "i", {"a": None})

    def test_connection_refused_raises(self):
        # 127.0.0.1:1 连接被拒——统一收敛为 KevUnavailableError
        with self.assertRaises(KevUnavailableError):
            KevClient("http://127.0.0.1:1", timeout_s=2.0).ping()

    def test_bad_base_url_rejected(self):
        with self.assertRaises(KevUnavailableError):
            KevClient("file:///etc/passwd")
        with self.assertRaises(KevUnavailableError):
            KevClient("http://u:p@127.0.0.1:8011")

    def test_ping(self):
        with MockKevServer("first") as s:
            self.assertTrue(KevClient(s.url).ping())


# ── 态势/候选枚举 ──

class TestStateAndCandidates(unittest.TestCase):
    def test_brief_fog_of_war(self):
        w = demo_world(phase=PHASE_COMBAT)
        add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 40000)))
        foe = add_unit(w, make_unit(w, TANK_TPL, 1, 1, (100000, 60000)))
        brief = situation_brief(w, 0)
        self.assertEqual(brief["我方"]["单位数"], 1)
        self.assertEqual(brief["可见敌军"]["数量"], 0)   # 未被探测=不可见
        foe.spotted_mask |= 1 << 0                      # 手动标记已被队0发现
        brief = situation_brief(w, 0)
        self.assertEqual(brief["可见敌军"]["数量"], 1)
        self.assertEqual(brief["可见敌军"]["单位列表"][0]["dist_m"], 200)

    def test_candidates_deterministic_and_capped(self):
        w = demo_world(phase=PHASE_COMBAT)
        for i in range(6):
            add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, i * 2000)))
        c1 = enumerate_candidates(w, 0, artillery_issued=set(),
                                  enemy_anchor=NORTH)
        c2 = enumerate_candidates(w, 0, artillery_issued=set(),
                                  enemy_anchor=NORTH)
        self.assertEqual([c.key for c in c1], [c.key for c in c2])
        self.assertLessEqual(len(c1), 12)
        self.assertEqual(c1[-1].key, "wait")            # 兜底项恒在
        limited = enumerate_candidates(w, 0, artillery_issued=set(),
                                       enemy_anchor=NORTH, limit=4)
        self.assertLessEqual(len(limited), 4)

    def test_purchase_candidates_affordability(self):
        w = demo_world()
        p = w.players[0]
        p.points = 60                                   # 只买得起步枪排
        cands = purchase_candidates(w, 0)
        self.assertEqual([k for _t, k, _d in cands], ["buy_0"])
        p.points = 0
        self.assertEqual(purchase_candidates(w, 0), [])


# ── 播放器全链路 ──

class TestKevPlayer(unittest.TestCase):
    def test_purchase_via_kev(self):
        with MockKevServer("fixed:buy_2") as s:        # 指定买第3张（突击炮）
            w = demo_world()
            ai = KevPlayer(0, KevClient(s.url), air_every=0)
            ai.step(w)
            self.assertEqual(len(w.command_queue), 1)
            cmd = w.command_queue[0]
            self.assertIsInstance(cmd, PurchaseCmd)
            self.assertIs(cmd.template, GUN_TPL)
            self.assertEqual(ai.stats["kev"], 1)
            world_tick(w)                               # 落地：扣点+入队出生
            self.assertEqual(w.players[0].points, 1000 - GUN_TPL.cost)
            ai.close()

    def test_purchase_fallback_on_dead_server(self):
        w = demo_world()
        ai = KevPlayer(0, KevClient("http://127.0.0.1:1", timeout_s=1.0),
                           air_every=0)
        ai.step(w)
        # 兜底=可负担首张（HeadlessAI 同款策略）
        self.assertIsInstance(w.command_queue[0], PurchaseCmd)
        self.assertIs(w.command_queue[0].template, RIFLE_TPL)
        self.assertEqual(ai.stats["fallback"], 1)
        ai.close()

    def test_combat_beat_issues_move_and_logs(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            log_path = os.path.join(td, "dec.jsonl")
            w = demo_world(phase=PHASE_COMBAT)
            add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 10000)))
            ai = KevPlayer(0, None, anchors=(SOUTH, NORTH), log=log_path,
                           air_every=0)
            ai.step(w)                                  # tick=0：直接命中节拍
            self.assertEqual(ai.stats["fallback"], 1)   # 无 client=规则兜底
            self.assertGreaterEqual(len(w.command_queue), 1)
            self.assertTrue(any(isinstance(c, MoveCmd) for c in w.command_queue))
            ai.close()
            with open(log_path, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source"], "fallback")
            self.assertEqual(rows[0]["phase"], "combat")
            self.assertTrue(rows[0]["commands"])
            self.assertEqual(rows[0]["commands"][0]["cmd"], "MoveCmd")

    def test_combat_kev_choice_executes(self):
        with MockKevServer("first") as s:               # first=效用最高候选
            w = demo_world(phase=PHASE_COMBAT)
            ai = KevPlayer(0, KevClient(s.url), anchors=(SOUTH, NORTH),
                           air_every=0)
            ai.step(w)
            self.assertEqual(ai.stats["kev"], 1)
            body = MockKevHandler.last_body
            # 紧凑态=单行文本（0.5B 384 token 预算）；含迷雾过滤后的态势段
            self.assertIsInstance(body["state"], str)
            self.assertIn("我方", body["state"])
            ai.close()

    def test_artillery_once_then_not_reissued(self):
        w = demo_world(phase=PHASE_COMBAT)
        add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (100000, 10000)))
        add_unit(w, make_unit(w, GUN_TPL, 0, 0, (100000, 5000)))
        issued = set()
        cands = enumerate_candidates(w, 0, artillery_issued=issued,
                                     enemy_anchor=NORTH)
        arty = next(c for c in cands if c.kind == "artillery")
        cmds = build_commands(w, w.players[0], arty)
        self.assertEqual(len(cmds), 2)                  # SetMode + FireMission
        issued.add(arty.params["unit_id"])
        again = [c for c in enumerate_candidates(w, 0, artillery_issued=issued,
                                                 enemy_anchor=NORTH)
                 if c.kind == "artillery"]
        self.assertEqual(again, [])                     # 一局一次门

    def test_attack_candidate_targets_visible_foe(self):
        w = demo_world(phase=PHASE_COMBAT)
        add_unit(w, make_unit(w, TANK_TPL, 0, 0, (100000, 45000)))
        foe = add_unit(w, make_unit(w, RIFLE_TPL, 1, 1, (100000, 55000)))
        foe.spotted_mask |= 1 << 0
        cands = enumerate_candidates(w, 0, artillery_issued=set(),
                                     enemy_anchor=NORTH)
        atk = [c for c in cands if c.kind == "attack"]
        self.assertEqual(len(atk), 1)
        cmds = build_commands(w, w.players[0], atk[0])
        self.assertIsInstance(cmds[0], AttackCmd)
        self.assertEqual(cmds[0].target.unit.id, foe.id)


# ── 整局：兜底全链路 + 确定性（同 seed 双跑逐位一致）──

def _fingerprint(w) -> str:
    parts = []
    for u in sorted(w.units, key=lambda x: x.id):
        parts.append(f"u{u.id}:t{u.team}:alive{u.alive}:"
                     f"{u.pos[0]},{u.pos[1]}:"
                     f"{sum(e.hp_current for e in u.elements)}:"
                     f"{u.morale}")
    for p in w.players:
        parts.append(f"p{p.index}:{p.points}:{p.spawn_serial}:"
                     f"{len(p.spawn_queue)}")
    for o in w.objectives:
        parts.append(f"o{o.id}:{o.owner}")
    parts.append(f"tick{w.tick}:phase{w.phase}")
    return "|".join(parts)


class TestFullGameFallback(unittest.TestCase):
    """纯规则兜底（无模型）打完部署相位+实战前段——门面：零异常+双跑一致。"""

    def _run(self, seed: int, ticks: int) -> str:
        w = demo_world(seed=seed)
        red = KevPlayer(0, None, anchors=(SOUTH, NORTH))
        blue = KevPlayer(1, None, anchors=(SOUTH, NORTH))
        for _ in range(ticks):
            red.step(w)
            blue.step(w)
            world_tick(w)
            if w.result is not None:
                break
        red.close()
        blue.close()
        return _fingerprint(w)

    def test_deterministic_replay(self):
        # 800 拍=盲部署购卡全程+实战前段（购买/移动/攻击令真实落地）
        a = self._run(42, 800)
        b = self._run(42, 800)
        self.assertEqual(a, b)

    def test_purchases_deplete_points(self):
        w = demo_world()
        red = KevPlayer(0, None, anchors=(SOUTH, NORTH))
        for _ in range(601):                            # 走完盲部署相位
            red.step(w)
            world_tick(w)
            if w.result is not None:
                break
        red.close()
        p = w.players[0]
        self.assertLess(p.points, 1000)                 # 真实购卡扣点
        self.assertEqual(p.spawn_serial, 4)             # 2 步枪+1 坦克+1 突击炮
        self.assertEqual(len([u for u in w.units if u.team == 0]), 4)


# ── 启动器 --check（进程内直调 main——不起子进程）──

def _load_launcher():
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "kev_serve.py")
    spec = importlib.util.spec_from_file_location("kev_serve_tool", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLauncherCheck(unittest.TestCase):
    def test_check_runs_and_reports(self):
        mod = _load_launcher()
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = mod.main(["--check", "--kev-dir", "/nonexistent/kev"])
        out = buf.getvalue()
        self.assertEqual(rc, 1)                         # kev 仓库不存在→未就绪
        self.assertIn("环境探测", out)
        self.assertIn("torch 后端", out)
        self.assertIn("启动命令", out)

    def test_safe_token_rejects_metacharacters(self):
        mod = _load_launcher()
        with self.assertRaises(SystemExit):
            mod._safe_token("--evil", "--model")
        with self.assertRaises(SystemExit):
            mod._safe_token("a b;rm", "--model")
        self.assertEqual(mod._safe_token("jaredpalmer/kev-0.5b", "--model"),
                         "jaredpalmer/kev-0.5b")


if __name__ == "__main__":
    unittest.main()
