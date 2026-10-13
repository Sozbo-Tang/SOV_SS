"""FE-T03 wire schema 与回放文件 v1 验收测试。

覆盖面（对齐 FE-01 §5 FE-T03 验收标准）：
- ① 35 类命令逐类 roundtrip（夹具 world 构造代表性实例；AirCallCmd 夹具带
  PARATROOP 载荷与不带两型、GarrisonCmd 夹具带建筑——七类引用解析全覆盖）；
- ② AST 守卫：解析 tick.py `_dispatch_command` 提取分派类名集 == wire 注册表
  （WIRE_COMMANDS）。验收口径注明：**35 支/35 类以 AST 实测为准**，FE-01
  :278-279「38 个分派支」系计数笔误——差异成因**推测**为另计入
  consume_unit_commands 三处单位级队列 isinstance 位（tick.py:2278 溯逃过滤/
  :2413 队列分派/:2415，实证行号），FE-01 原文未记载 38 的计数方式无从确证，
  勘正结论不依赖成因成立；
- ③ 回放文件写读往返（save→load→逐 tick 命令/校验和全等）+ Replayer 全量
  重放与原局逐 tick 校验和一致（经 SCENARIO_BUILDERS 注册测试场景）；
- ④ fail-fast：未知 schema_version/未知 rec 类型/校验和函数标识不符/未知
  scenario/deck 清单不一致/校验和错位/命令 tick 悬空/七类外引用/解析失败
  均明确报错不静默；
- ⑤ describe_command 改由 wire 生成后的等价回归：对 AI 层实际发出的命令子集
  （describe_command 旧覆盖族）**旧键逐键等价、允许新增键**（如 FireMissionCmd
  旧版只记 cmd/unit/form/point，wire 版必含 line/ammo_mult/salvo_mode/
  creep_speed——消费面 tick.py:2123-2125 实证；逐字节等价必红故不取）。

stdup 惯例同仓内测试：unittest、锚点写死不自证。
"""
import ast
import json
import pathlib
import tempfile
import unittest

from sovs.sim.air import cmd_air_call
from sovs.sim.air_data import CARD_OBJECTS
from sovs.sim.tick import (AirAirdropCmd, AirAfterburnerCmd, AirAltCmd,
                           AirCallCmd, AirDecoyCmd, add_unit, AirDisengageCmd,
                           AirEngageAirCmd, AirMoveCmd, AirPatrolCmd, AirRTBCmd,
                           AirStrikeCmd, AttackCmd, BuySuppliesCmd, CancelCmd,
                           CancelFireMissionCmd, CreateDumpCmd, DeployCmd,
                           DismountCmd,
                           FireMissionCmd, FormationCmd, GarrisonCmd,
                           GroundRTBCmd, LaserDesignateCmd, make_unit, MountCmd,
                           MoveCmd, PackCmd, PivotCmd, PurchaseCmd, queue_command,
                           RadarCmd, ReverseCmd, SetAirdropBeaconCmd, SetModeCmd,
                           SetSniperCoverCmd, SetStanceCmd, SmokeCmd, SprintCmd,
                           StopCmd, SupplySwitchCmd, ToggleAmbushCmd, TowCmd,
                           UnGarrisonCmd, UntowCmd)
from sovs.sim.types import (AltTier, Building, FireMissionForm, FormationShape,
                            Mode, MoveMode, SalvoMode, Stance)
from sovs.sim import wire
from sovs.sim.wire import (CHECKSUM_FN_ID, Replayer, ReplayWriter,
                           decode_command, describe_command, encode_command,
                           load_replay, state_checksum)
from tools.kev_game_demo import (GUN_TPL, MIXED_TPL, PARA_TPL, RIFLE_TPL,
                                 TANK_TPL, TRUCK_TPL, build_world)

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ── 夹具：引用面满载 world（七类引用全部在场）──


def rich_world():
    """build_world 底座（deck 含 PARATROOP 305）+ 两队地面单位 + 建筑 + 真实
    cmd_air_call 呼叫的航空器（经济/扣份走真实产线——引用解析对真实实例）。"""
    w = build_world(1234)
    add_unit(w, make_unit(w, RIFLE_TPL, 0, 0, (20000, 10000)))     # 步枪排×2 队
    add_unit(w, make_unit(w, RIFLE_TPL, 1, 1, (180000, 90000)))
    tank0 = add_unit(w, make_unit(w, TANK_TPL, 0, 0, (30000, 12000)))
    gun0 = add_unit(w, make_unit(w, GUN_TPL, 0, 0, (40000, 14000)))
    truck0 = add_unit(w, make_unit(w, TRUCK_TPL, 0, 0, (50000, 16000)))
    mixed0 = add_unit(w, make_unit(w, MIXED_TPL, 0, 0, (60000, 18000)))
    w.buildings.append(Building(id=1, pos=(100000, 50000), hp=100,
                                garrison_slots=2))
    bomber = cmd_air_call(w, w.players[0], CARD_OBJECTS["IL2M"], {"BOMB": 2})
    fighter = cmd_air_call(w, w.players[0], CARD_OBJECTS["YAK9"], {})
    transport = cmd_air_call(w, w.players[0], CARD_OBJECTS["LI2"],
                             {"PARATROOP": PARA_TPL})   # 换装路径产物（活引用）
    enemy_fighter = cmd_air_call(w, w.players[1], CARD_OBJECTS["FW190A"], {})
    assert None not in (bomber, fighter, transport, enemy_fighter)
    return {"w": w, "rifle0": w.units[0], "rifle1": w.units[1], "tank0": tank0,
            "gun0": gun0, "truck0": truck0, "mixed0": mixed0,
            "bomber": bomber, "fighter": fighter, "transport": transport,
            "enemy_fighter": enemy_fighter, "building": w.buildings[0]}


def representative_commands(fx) -> list:
    """35 类命令代表性实例清单（含任务点名变体：AirCallCmd 带/不带 PARATROOP、
    PARATROOP=None 三型；AttackCmd 元素/建筑双目标；FireMissionCmd POINT/LINE）。"""
    w, p0, p1 = fx["w"], fx["w"].players[0], fx["w"].players[1]
    para_slot_tpl = next(s.template for s in p0.deck_slots
                         if s.template is PARA_TPL)
    return [
        MoveCmd(unit=fx["rifle0"], path=[(30000, 12000), (40000, 15000)],
                mode=MoveMode.MARCH, queue=True),
        MoveCmd(unit=fx["rifle0"], path=[(25000, 11000)]),
        ReverseCmd(unit=fx["tank0"], dest=(25000, 11000)),
        StopCmd(unit=fx["rifle0"]),
        CancelCmd(unit=fx["rifle0"]),
        PivotCmd(unit=fx["tank0"], facing_deg=90),
        FormationCmd(units=[fx["rifle0"], fx["tank0"]], shape=FormationShape.WEDGE),
        DeployCmd(unit=fx["gun0"]),
        PackCmd(unit=fx["gun0"]),
        SetModeCmd(element=fx["gun0"].elements[0], mode=Mode.INDIRECT),
        PurchaseCmd(player=p1, template=TANK_TPL),        # deck_slots 身份解析
        PurchaseCmd(player=p1, template=TANK_TPL,
                    dest=(60000, 30000)),                 # v1.2 垂足出动目的地
        FireMissionCmd(unit=fx["gun0"], form=FireMissionForm.POINT,
                       point=(50000, 40000)),
        FireMissionCmd(unit=fx["gun0"], form=FireMissionForm.LINE,
                       line=[(50000, 40000), (60000, 45000)], ammo_mult=2,
                       salvo_mode=SalvoMode.HALF, creep_speed=7),
        CancelFireMissionCmd(unit=fx["gun0"]),
        SmokeCmd(element=fx["truck0"].elements[0], point=(21000, 11000)),
        SmokeCmd(element=fx["truck0"].elements[0], point=None),
        SetStanceCmd(unit=fx["rifle0"], stance=Stance.HOLD_FIRE),
        ToggleAmbushCmd(unit=fx["rifle0"]),
        SprintCmd(unit=fx["rifle0"]),
        GarrisonCmd(unit=fx["rifle0"], building=fx["building"]),   # 建筑引用
        UnGarrisonCmd(unit=fx["rifle0"]),
        MountCmd(squad_elements=[fx["mixed0"].elements[0],
                                 fx["mixed0"].elements[1]],
                 carrier_unit=fx["truck0"]),
        DismountCmd(squad_unit=fx["mixed0"]),
        TowCmd(tower_elements=[fx["truck0"].elements[0]],
               towed_element=fx["gun0"].elements[0]),
        UntowCmd(element=fx["gun0"].elements[0]),
        AttackCmd(element=fx["tank0"].elements[0],
                  target=fx["rifle1"].elements[0]),
        AttackCmd(element=fx["tank0"].elements[0], target=fx["building"]),
        SetSniperCoverCmd(sniper_unit=fx["rifle0"], target_unit=fx["rifle1"]),
        SetAirdropBeaconCmd(unit=fx["rifle0"], pos=(15000, 9000)),
        SetAirdropBeaconCmd(unit=fx["rifle0"], pos=None),
        BuySuppliesCmd(truck_element=fx["truck0"].elements[0], rounds=10,
                       medical=5),
        CreateDumpCmd(unit=fx["truck0"], pos=(140000, 90000)),   # 终审修复块 1.4
        AirCallCmd(player=p0, template=CARD_OBJECTS["IL2M"],
                   payload={"BOMB": 2}),                    # 不带 PARATROOP
        AirCallCmd(player=p0, template=CARD_OBJECTS["LI2"],
                   payload={"PARATROOP": para_slot_tpl}),   # 换装产物活引用
        AirCallCmd(player=p0, template=CARD_OBJECTS["LI2"],
                   payload={"PARATROOP": None}),            # None 保持 None
        AirMoveCmd(aircraft=fx["transport"], path=[(90000, 45000)]),
        AirPatrolCmd(aircraft=fx["fighter"], center=(100000, 50000), radius=3000),
        AirAltCmd(aircraft=fx["fighter"], tier=AltTier.HIGH),
        AirStrikeCmd(aircraft=fx["bomber"], target=(100000, 48000), weapon="BOMB"),
        AirAirdropCmd(aircraft=fx["transport"], drop_point=(90000, 46000)),
        AirEngageAirCmd(aircraft=fx["fighter"], engage=True),
        AirDisengageCmd(aircraft=fx["fighter"]),
        AirRTBCmd(aircraft=fx["transport"]),
        # ── P1 机制块 6 类（2026-10-13，wire 1.3）──
        GroundRTBCmd(unit=fx["rifle0"]),
        LaserDesignateCmd(designator_unit=fx["rifle0"], target_unit=fx["rifle1"]),
        RadarCmd(unit=fx["gun0"], engage=True),
        SupplySwitchCmd(unit=fx["truck0"], switch="heal", on=False),
        AirAfterburnerCmd(aircraft=fx["fighter"], engage=True),
        AirDecoyCmd(aircraft=fx["fighter"], action="POP"),
    ]


class TestRoundtripAllCommandTypes(unittest.TestCase):
    """① 35 类命令 encode→json→decode 往返一致（同 world 引用恒等）。"""

    def test_all_35_types_roundtrip_via_json(self):
        fx = rich_world()
        w = fx["w"]
        cmds = representative_commands(fx)
        seen = {type(c).__name__ for c in cmds}
        self.assertEqual(seen, set(wire.WIRE_COMMANDS))    # 41 类无一遗漏（P1 +6）
        for c in cmds:
            with self.subTest(cmd=type(c).__name__):
                wire_dict = encode_command(c)
                # wire dict 本身必须 stdlib json 直序列化（纯数据契约）
                blob = json.dumps(wire_dict, ensure_ascii=False)
                decoded = decode_command(w, json.loads(blob))
                self.assertEqual(decoded, c)               # dataclass 逐字段等


class TestFailFast(unittest.TestCase):
    """④ fail-fast：七类外引用 encode 报错、解析失败/未知类型 decode 报错。"""

    def test_encode_unknown_command_type(self):
        with self.assertRaises(ValueError):
            encode_command(object())

    def test_encode_foreign_unit_reference(self):
        # 七类外引用（裸 object 无 id）出现即 encode 报错
        with self.assertRaises(ValueError):
            encode_command(MoveCmd(unit=object(), path=[(1, 2)]))

    def test_encode_paratroop_bool_payload_rejected(self):
        # PARATROOP 布尔原料（actions.py:131-136 换装前的 Candidate.params 形态）
        # 不是合法 wire 形态——执行期换装后才可入流
        fx = rich_world()
        with self.assertRaises(ValueError):
            encode_command(AirCallCmd(player=fx["w"].players[0],
                                      template=CARD_OBJECTS["LI2"],
                                      payload={"PARATROOP": True}))

    def test_decode_unknown_unit(self):
        fx = rich_world()
        with self.assertRaises(ValueError):
            decode_command(fx["w"], {"cmd": "MoveCmd", "unit_id": 999,
                                     "path": [[1, 2]], "mode": "NORMAL",
                                     "queue": False})

    def test_decode_unknown_element_composite_key(self):
        fx = rich_world()
        u = fx["rifle0"]
        with self.assertRaises(ValueError):
            decode_command(fx["w"], {"cmd": "SetModeCmd",
                                     "element": [u.id, 99], "mode": "DIRECT"})

    def test_decode_unknown_aircraft(self):
        fx = rich_world()
        with self.assertRaises(ValueError):
            decode_command(fx["w"], {"cmd": "AirRTBCmd", "aircraft_id": 999})

    def test_decode_unknown_building(self):
        fx = rich_world()
        with self.assertRaises(ValueError):
            decode_command(fx["w"], {"cmd": "GarrisonCmd", "unit_id": 1,
                                     "building_id": 99})

    def test_decode_unknown_air_template(self):
        fx = rich_world()
        with self.assertRaises(ValueError):
            decode_command(fx["w"], {"cmd": "AirCallCmd", "player_index": 0,
                                     "air_template_id": 999, "payload": {}})

    def test_decode_purchase_template_not_in_deck(self):
        # deck_slots 身份解析失败（template_id 不在该玩家卡组）→ fail-fast
        fx = rich_world()
        with self.assertRaises(ValueError):
            decode_command(fx["w"], {"cmd": "PurchaseCmd", "player_index": 0,
                                     "template_id": 9999})

    def test_decode_unknown_command_name(self):
        fx = rich_world()
        with self.assertRaises(ValueError):
            decode_command(fx["w"], {"cmd": "NoSuchCmd"})


class TestDispatchAstromGuard(unittest.TestCase):
    """② AST 守卫：_dispatch_command 分派支类名集 == wire 注册表。

    验收口径：35 支/35 类以 AST 实测为准；FE-01 :278-279「38 个分派支」系计数
    笔误——差异成因推测为另计入 consume_unit_commands 三处单位级队列
    isinstance 位（tick.py:2278/:2413/:2415 实证；FE-01 原文未记载 38 的计数
    方式无从确证），勘正结论不依赖成因成立。新增命令时本守卫即红——按分派支
    枚举补 wire codec + roundtrip 夹具。
    """

    def _dispatch_classes(self):
        src = (ROOT / "sovs" / "sim" / "tick.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_command":
                return {n.args[1].id for n in ast.walk(node)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name)
                        and n.func.id == "isinstance"
                        and len(n.args) == 2
                        and isinstance(n.args[1], ast.Name)}
        self.fail("tick.py 未找到 _dispatch_command")

    def test_dispatch_branches_equal_wire_registry(self):
        classes = self._dispatch_classes()
        self.assertEqual(len(classes), 42)                # 42 支（AST 实测；P1 +6→
                                                       # 终审修复块 2026-10-13 +CreateDumpCmd）
        self.assertEqual(classes, set(wire.WIRE_COMMANDS))


def _legacy_describe_command(cmd) -> dict:
    """旧 describe_command 冻结快照（sovs/ai/decision_log.py:47-149，FE-T03 迁
    wire 前字面——等价回归的对照片，不再随实现演进）。"""
    name = type(cmd).__name__
    if name == "MoveCmd":
        return {"cmd": name, "unit": cmd.unit.id,
                "dest": list(cmd.path[-1]) if cmd.path else None,
                "mode": getattr(cmd.mode, "name", str(cmd.mode)), "queue": cmd.queue}
    if name in ("StopCmd", "CancelCmd", "DeployCmd", "PackCmd",
                "ToggleAmbushCmd", "CancelFireMissionCmd"):
        unit = getattr(cmd, "unit", None)
        return {"cmd": name, "unit": unit.id if unit is not None else None}
    if name == "AttackCmd":
        return {"cmd": name, "element": cmd.element.id,
                "unit": cmd.element.unit.id, "target_unit": cmd.target.unit.id,
                "target_element": cmd.target.id}
    if name == "SetModeCmd":
        return {"cmd": name, "element": cmd.element.id,
                "unit": cmd.element.unit.id, "mode": getattr(cmd.mode, "name", str(cmd.mode))}
    if name == "FireMissionCmd":
        return {"cmd": name, "unit": cmd.unit.id,
                "form": getattr(cmd.form, "name", str(cmd.form)),
                "point": list(cmd.point) if cmd.point else None}
    if name == "PurchaseCmd":
        return {"cmd": name, "player_index": cmd.player.index,
                "template_id": cmd.template.template_id,
                "template": cmd.template.name, "cost": cmd.template.cost}
    if name == "FormationCmd":
        return {"cmd": name, "units": [u.id for u in cmd.units],
                "shape": getattr(cmd.shape, "name", str(cmd.shape))}
    if name == "AirCallCmd":
        return {"cmd": name, "player_index": cmd.player.index,
                "aircraft": cmd.template.name,
                "payload": {k: (v if isinstance(v, (int, str)) else
                                getattr(v, "name", str(v)))
                            for k, v in (cmd.payload or {}).items()}}
    if name == "AirStrikeCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id,
                "target": list(cmd.target), "weapon": cmd.weapon}
    if name == "AirAirdropCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id,
                "point": list(cmd.drop_point)}
    if name == "AirPatrolCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id,
                "center": list(cmd.center), "radius": cmd.radius}
    if name == "AirEngageAirCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id, "engage": cmd.engage}
    if name == "AirRTBCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id}
    if name == "AirAltCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id,
                "tier": getattr(cmd.tier, "name", str(cmd.tier))}
    if name == "MountCmd":
        return {"cmd": name, "squads": [s.id for s in cmd.squad_elements],
                "carrier_unit": cmd.carrier_unit.id}
    if name == "DismountCmd":
        return {"cmd": name, "unit": cmd.squad_unit.id}
    if name == "TowCmd":
        return {"cmd": name, "towers": [t.id for t in cmd.tower_elements],
                "towed": cmd.towed_element.id,
                "towed_unit": cmd.towed_element.unit.id}
    if name == "UntowCmd":
        return {"cmd": name, "element": cmd.element.id,
                "unit": cmd.element.unit.id}
    if name == "GarrisonCmd":
        return {"cmd": name, "unit": cmd.unit.id, "building": cmd.building.id}
    if name == "UnGarrisonCmd":
        return {"cmd": name, "unit": cmd.unit.id}
    if name == "SmokeCmd":
        return {"cmd": name, "element": cmd.element.id,
                "unit": cmd.element.unit.id,
                "pos": list(cmd.point) if cmd.point else None}
    if name == "PivotCmd":
        return {"cmd": name, "unit": cmd.unit.id, "facing": cmd.facing_deg}
    if name == "SprintCmd":
        return {"cmd": name, "unit": cmd.unit.id}
    if name == "SetStanceCmd":
        return {"cmd": name, "unit": cmd.unit.id,
                "stance": getattr(cmd.stance, "name", str(cmd.stance))}
    if name == "SetSniperCoverCmd":
        return {"cmd": name, "sniper": cmd.sniper_unit.id,
                "target": cmd.target_unit.id}
    if name == "BuySuppliesCmd":
        return {"cmd": name, "element": cmd.truck_element.id,
                "unit": cmd.truck_element.unit.id,
                "rounds": cmd.rounds, "medical": cmd.medical}
    if name == "SetAirdropBeaconCmd":
        return {"cmd": name, "unit": cmd.unit.id,
                "pos": list(cmd.pos) if cmd.pos else None}
    if name == "AirMoveCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id,
                "dest": list(cmd.path[-1]) if cmd.path else None}
    if name == "AirDisengageCmd":
        return {"cmd": name, "aircraft": cmd.aircraft.id}
    return {"cmd": name}


class TestDescribeEquivalence(unittest.TestCase):
    """⑤ describe_command 等价回归：旧覆盖族旧键逐键等价、允许新增键。"""

    def test_old_keys_equal_for_all_families(self):
        fx = rich_world()
        # 等价口径=「AI 层实际发出的命令子集」：建筑目标 AttackCmd 不在旧覆盖面
        # （旧实现 cmd.target.unit 即 AttributeError——AI 从不发出）；PARATROOP=None
        # 的 AirCallCmd 亦非 AI 产出形态（actions.py 换装产物=模板或整键不出现），
        # 且旧实现把 None 字符串化为 "None" 系负值语义——均排除比对
        cmds = [c for c in representative_commands(fx)
                if not (isinstance(c, AttackCmd) and isinstance(c.target, Building))
                and not (isinstance(c, AirCallCmd)
                         and c.payload.get("PARATROOP", 1) is None)]
        for c in cmds:
            with self.subTest(cmd=type(c).__name__):
                old = _legacy_describe_command(c)
                new = describe_command(c)
                # 允许新增键（如 FireMissionCmd 的 line/ammo_mult/salvo_mode/
                # creep_speed），但旧键必须逐键在且值等
                self.assertTrue(set(old) <= set(new),
                                "旧键缺失：%s" % (set(old) - set(new),))
                for k, v in old.items():
                    self.assertEqual(new[k], v, "旧键 %r 值不等" % k)

    def test_unknown_command_fallback_keeps_class_name(self):
        # 旧契约保持：未知命令兜底只记类名（日志永不阻断对局）
        self.assertEqual(describe_command(object()), {"cmd": "object"})

    def test_decision_log_reexports_wire_describe(self):
        # 导入面不变：sovs.ai.decision_log.describe_command is wire 生成版
        from sovs.ai import decision_log
        self.assertIs(decision_log.describe_command, describe_command)


class TestReplayFileRoundtrip(unittest.TestCase):
    """③ 回放文件写读往返 + Replayer 全量重放逐 tick 校验和一致。"""

    def _record_scripted(self, path, seed=99, ticks=40):
        """短局脚本：购卡→出生→移动/队形/航呼，逐 tick 命令+校验和落盘。
        返回 (header, records)。"""
        w = build_world(seed)
        p0 = w.players[0]
        with ReplayWriter(path, world=w, seed=seed,
                          scenario="kev_game_demo.v1") as rw:
            pending = []                                   # (tick, pi, cmd)
            for _ in range(ticks):
                if w.tick == 0:
                    queue_command(w, PurchaseCmd(player=p0, template=RIFLE_TPL))
                    pending.append((0, 0, PurchaseCmd(player=p0,
                                                      template=RIFLE_TPL)))
                if w.tick == 20 and w.units:
                    mv = MoveCmd(unit=w.units[0], path=[(50000, 25000)],
                                 mode=MoveMode.NORMAL, queue=False)
                    queue_command(w, mv)
                    pending.append((20, 0, mv))
                wire.world_tick(w)
                tick_cmds = [pc for pc in pending if pc[0] == w.tick - 1]
                for t, pi, c in tick_cmds:
                    rw.command(t, pi, c)
                pending = [pc for pc in pending if pc[0] != w.tick - 1]
                rw.checksum(w.tick, w)
        return load_replay(path)

    def test_save_load_records_identical_and_replay_matches(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "scripted.jsonl"
            header, records = self._record_scripted(path)
            # 文件头契约逐字段（v1）
            self.assertEqual(header["schema_version"], "1.4")  # 终审修复块升版（1.3→1.4 +CreateDumpCmd）
            self.assertEqual(header["checksum_fn"], CHECKSUM_FN_ID)
            self.assertEqual(header["scenario"], "kev_game_demo.v1")
            self.assertEqual(header["seed"], 99)
            self.assertEqual(header["phase_ticks"], [600, 13200])  # 实现现值
            self.assertEqual(header["players_per_team"], 1)
            self.assertEqual(header["map_key"], "none")
            self.assertEqual(header["decks"],
                             [[301, 303, 302, 306, 307, 305]] * 2)  # 含 PARATROOP
            cmd_records = [r for r in records if r["rec"] == "cmd"]
            ck_records = [r for r in records if r["rec"] == "cksum"]
            self.assertEqual([r["tick"] for r in ck_records],
                             list(range(1, 41)))           # 逐 tick 校验和流
            self.assertEqual({r["wire"]["cmd"] for r in cmd_records},
                             {"PurchaseCmd", "MoveCmd"})
            # 全量重放：逐 tick 校验和一致（run 内断言，完成即一致）
            world = Replayer(path).run()
            self.assertEqual(world.tick, 40)

    def test_replayer_build_assertions(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "scripted.jsonl"
            self._record_scripted(path)
            header, records = load_replay(path)

            def rewrite(mutate):
                obj = json.loads(json.dumps(header))
                mutate(obj)
                lines = [json.dumps(obj, ensure_ascii=False,
                                    separators=(",", ":"))]
                lines += [json.dumps(r, ensure_ascii=False,
                                     separators=(",", ":")) for r in records]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            # deck 清单不一致 → 报错
            rewrite(lambda h: h.__setitem__("decks", [[1]]))
            with self.assertRaises(ValueError):
                Replayer(path).build()
            # phase_ticks 不符 → 报错（配置漂移守卫）
            rewrite(lambda h: h.__setitem__("phase_ticks", [90, 13200]))
            with self.assertRaises(ValueError):
                Replayer(path).build()
            # players_per_team 不符 → 报错
            rewrite(lambda h: h.__setitem__("players_per_team", 2))
            with self.assertRaises(ValueError):
                Replayer(path).build()
            # 未知 scenario → fail-fast 报错不静默
            rewrite(lambda h: h.__setitem__("scenario", "no.such.scenario"))
            with self.assertRaises(ValueError):
                Replayer(path).build()

    def test_malformed_files_fail_fast(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "scripted.jsonl"
            header, records = self._record_scripted(path)

            def rewrite_file(header_mut=None, rec_mut=None):
                """重写回放文件：header_mut(h) 原地改头；rec_mut(r)→dict 替换该
                记录 / None 删除该记录 / 缺省保留。"""
                h = json.loads(json.dumps(header))
                if header_mut:
                    header_mut(h)
                lines = [json.dumps(h, ensure_ascii=False,
                                    separators=(",", ":"))]
                for r in records:
                    rr = rec_mut(r) if rec_mut else r
                    if rr is None:
                        continue
                    lines.append(json.dumps(rr, ensure_ascii=False,
                                            separators=(",", ":")))
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            # 未知 schema_version
            rewrite_file(header_mut=lambda h: h.__setitem__("schema_version", "9.9"))
            with self.assertRaises(ValueError):
                load_replay(path)
            # 校验和函数标识不符
            rewrite_file(header_mut=lambda h: h.__setitem__("checksum_fn", "crc32-x"))
            with self.assertRaises(ValueError):
                load_replay(path)
            # 未知 rec 类型
            rewrite_file(rec_mut=lambda r: ({**r, "rec": "bogus"}
                                            if r["rec"] == "cksum" else r))
            with self.assertRaises(ValueError):
                load_replay(path)
            # 校验和错位（篡改一条 sum）→ run 抛
            def flip_sum(r):
                if r["rec"] == "cksum" and r["tick"] == 30:
                    return {**r, "sum": r["sum"] + 1}
                return r
            rewrite_file(rec_mut=flip_sum)
            with self.assertRaises(ValueError):
                Replayer(path).run()
            # 校验和流非逐 tick 连续（删一条中间记录）→ 报错
            rewrite_file(rec_mut=lambda r: None if (r["rec"] == "cksum"
                                                    and r["tick"] == 15) else r)
            with self.assertRaises(ValueError):
                Replayer(path)
            # 命令 tick 悬空超出校验和窗 → 报错
            def dangle(r):
                if r["rec"] == "cmd" and r["tick"] == 20:
                    return {**r, "tick": 999}
                return r
            rewrite_file(rec_mut=dangle)
            with self.assertRaises(ValueError):
                Replayer(path)
            # 首行非 header
            path.write_text('{"rec":"cmd"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_replay(path)
            # 空文件
            path.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_replay(path)


class TestChecksum(unittest.TestCase):
    """state_checksum：FNV-1a 64 整型、与指纹文本同源、确定性。"""

    def test_checksum_deterministic_and_int(self):
        w1, w2 = build_world(5), build_world(5)
        self.assertIsInstance(state_checksum(w1), int)
        self.assertEqual(state_checksum(w1), state_checksum(w2))
        wire.world_tick(w1)
        self.assertNotEqual(state_checksum(w1), state_checksum(build_world(5)))

    def test_fnv1a64_known_vector(self):
        # FNV-1a 64 标准测试向量（"a" / "foobar"）——算法锚点不自证
        self.assertEqual(wire.fnv1a64(b""), 0xcbf29ce484222325)
        self.assertEqual(wire.fnv1a64(b"a"), 0xaf63dc4c8601ec8c)
        self.assertEqual(wire.fnv1a64(b"foobar"), 0x85944171f73967e8)


if __name__ == "__main__":
    unittest.main()
