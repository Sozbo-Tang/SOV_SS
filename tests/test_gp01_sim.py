"""GP-01 断箭玩法对照仿真侧改动验收（2026-10-12 炮击模式块＋空中可控块·sim 面）：

覆盖面（对照 docs/GP-01 §3/§4 simChanges 清单）：
  ① 炮击弹药位与烟幕武器路径——FireMissionCmd.ammo（HE|SMOKE）：SMOKE 任务查
     烟弹档（无档 REJECT）、fire_at 落 SmokeZone 不落 Projectile、耗烟档弹/装填/
     声测喂入、弹量基数与超程进位判距按烟档取、HE 缺省行为逐位不变；
  ② 空袭画线攻击轴——AirStrikeCmd.axis：run_start/run_end 按玩家线向推导（与
     机位向解耦），缺省 None=现行为；
  ③ 反炮兵声测回路——sonar_step：IntelCircle 唯一写者（累积→定位→收窄→
     停火冻结→换阵地重置→未展开/车载不侦听→圈记侦听方队）；
  ④ 命令拒绝日志——rejection_log 环形 32、不进 state_fingerprint_text；
  ⑤ 状态帧 1.1——飞机条目四新键（facing/engage_air/task/alt_pending）、
     players.air_cooldowns、顶层 rejections 尾 8 条＋视角过滤；
  ⑥ wire 1.1——FireMissionCmd.ammo / AirStrikeCmd.axis 编解码 roundtrip、
     旧 1.0 回放文件 fail-fast。

锚点手推写死（配置现值 tables.py：sonar_locate_threshold=100/hold=100/
max=6000/min=1500、smoke_ttl=600/smoke_radius=3000、strafe_run_lead=8000），
不自证。合成模板沿 test_ground_combat 惯例（template_id 5xx 段）。
"""
import json
import pathlib
import tempfile
import unittest

from sovs.sim.air import AltTier, AircraftInstance, AirTask, TaskKind, cmd_air_strike
from sovs.sim.air_data import CARD_OBJECTS
from sovs.sim.tick import (REJECTION_LOG_CAP, DeployState, FireMissionCmd,
                           IntelCircle, Mode, SmokeZone, add_unit, cmd_fire_mission,
                           make_unit, make_world, queue_command, sonar_step,
                           upsert_sound_track, world_tick)
from sovs.sim.types import (DamageType, ElementTemplate, ElementType, FireMissionForm,
                            MovementClass, SalvoMode, Trajectory, UnitTemplate,
                            UnitType, WeaponTemplate)
from sovs.sim.state_frame import state_frame
from sovs.sim.wire import (ReplayWriter, decode_command, encode_command,
                           load_replay, state_fingerprint_text)

# ── 合成模板（5xx 测试段，沿 test_ground_combat 惯例）──

# 曲射双武器行炮（GP-01 §3 表行5 载体）：主武器 HE＋第二行 SMOKE 档（GDD-01
# 「82mm/120mm 可打烟雾弹」的数据形态——damage_type=SMOKE、BALLISTIC）
HE_W = WeaponTemplate(name="HE_W", damage_type=DamageType.HE, damage=6,
                      blast_radius_cm=2500, max_range_cm=200000, dispersion_cm=0,
                      reload_time_ticks=10, ammo_base=6, salvo=1,
                      projectile_speed_cm_tick=100, trajectory=Trajectory.BALLISTIC)
SMOKE_W = WeaponTemplate(name="SMOKE_W", damage_type=DamageType.SMOKE, damage=0,
                         max_range_cm=150000, dispersion_cm=0,
                         reload_time_ticks=10, ammo_base=4, salvo=1,
                         projectile_speed_cm_tick=100,
                         trajectory=Trajectory.BALLISTIC)
SMOKE_ELEM = ElementTemplate(element_type=ElementType.GUN,
                             unit_type=UnitType.INFANTRY, hp_max=6,
                             weapons=(HE_W, SMOKE_W))
SMOKE_BATT_TPL = UnitTemplate(
    template_id=507, name="smoke battery", category=3, cost=85,
    element_templates=(SMOKE_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=1, movement_class=MovementClass.FOOT,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))

# 单 HE 武器炮（无烟档——SMOKE 任务 REJECT 载体）
HE_ONLY_ELEM = ElementTemplate(element_type=ElementType.GUN,
                               unit_type=UnitType.INFANTRY, hp_max=6,
                               weapons=(HE_W,))
HE_ONLY_TPL = UnitTemplate(
    template_id=508, name="he battery", category=3, cost=80,
    element_templates=(HE_ONLY_ELEM,), optics_ground_cm=20000, stealth_base=4,
    speed_tier=1, movement_class=MovementClass.FOOT,
    mode_set=(1 << Mode.DIRECT) | (1 << Mode.INDIRECT))

# 声测班（R-03 载体）：sonar_radius_cm/sonar_rate 模板位（types.py §D.1#22/23）
SONAR_ELEM = ElementTemplate(element_type=ElementType.SQUAD,
                             unit_type=UnitType.INFANTRY, hp_max=8)
SONAR_TPL = UnitTemplate(
    template_id=509, name="sound ranger", category=1, cost=30,
    element_templates=(SONAR_ELEM,), optics_ground_cm=15000, stealth_base=5,
    speed_tier=1, movement_class=MovementClass.FOOT,
    sonar_radius_cm=30000, sonar_rate=60)


def _armed(w, tpl, team, pos):
    u = add_unit(w, make_unit(w, tpl, team, 0, pos))
    for e in u.elements:
        e.mode = Mode.INDIRECT
    return u


class TestSmokeFireMission(unittest.TestCase):
    """① GP-01 §3 表行5：弹药位＋武器烟弹路径。"""

    def _world_with_smoke_battery(self):
        w = make_world(11)
        u = _armed(w, SMOKE_BATT_TPL, 0, (100000, 100000))
        return w, u

    def test_smoke_mission_creates_and_fires_smoke_zone_not_projectile(self):
        w, u = self._world_with_smoke_battery()
        pt = (120000, 100000)
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT, pt, 1,
                                         "SMOKE", SalvoMode.FULL, 0))
        fm = u.fire_mission
        self.assertEqual(fm.ammo, "SMOKE")
        self.assertEqual(fm.shots_left, 4)      # 1 门 × SMOKE_W.ammo_base 4 × 1
        from sovs.sim.tick import process_fire_mission
        process_fire_mission(w, u)
        self.assertEqual(len(w.smoke_zones), 1)             # 落 SmokeZone
        self.assertEqual(len(w.projectiles), 0)             # 不落 Projectile
        z = w.smoke_zones[0]
        self.assertIsInstance(z, SmokeZone)
        self.assertEqual(z.radius_cm, 3000)                 # tables.py smoke_radius_cm
        self.assertEqual(z.ttl_ticks, 600)                  # 600tick=60s（断箭 1.1.1）
        # 耗烟档弹：第二武器行（index 1）4→3；主武器 HE 弹不动
        self.assertEqual(u.elements[0].weapon_states[0].ammo_left, 6)
        self.assertEqual(u.elements[0].weapon_states[1].ammo_left, 3)
        self.assertEqual(fm.shots_left, 3)
        # 声测喂入（AMB-14/17②：曲射恒喂——敌方队一条）
        self.assertEqual(len(w.sound_tracks), 1)
        self.assertEqual(w.sound_tracks[0].listening_team, 1)
        # 烟弹不校射（R-16=HE 观测收束链；SMOKE 任务 calib 恒 0）
        self.assertEqual(fm.calib_progress, 0)

    def test_smoke_mission_rejected_without_smoke_weapon_profile(self):
        # 「查 SMOKE 武器档」门：无烟档单位 REJECT（经命令流——顺验 rejection_log）
        w = make_world(12)
        u = _armed(w, HE_ONLY_TPL, 0, (100000, 100000))
        queue_command(w, FireMissionCmd(unit=u, form=FireMissionForm.POINT,
                                        point=(120000, 100000), ammo="SMOKE"))
        world_tick(w)
        self.assertIsNone(u.fire_mission)
        self.assertEqual(len(w.rejection_log), 1)
        entry = w.rejection_log[0]
        self.assertEqual(entry["cmd"], "FireMissionCmd")
        self.assertEqual(entry["ref_id"], u.id)
        self.assertEqual(entry["tick"], w.tick)

    def test_ammo_value_domain_gate(self):
        # 值域外（wire str 自由面，处理体收口）REJECT
        w = make_world(13)
        u = _armed(w, SMOKE_BATT_TPL, 0, (100000, 100000))
        self.assertFalse(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                          (120000, 100000), 1, "AP",
                                          SalvoMode.FULL, 0))
        self.assertIsNone(u.fire_mission)

    def test_he_default_behavior_unchanged(self):
        # 缺省 "HE"：主武器路径逐位不变（弹丸/耗弹/弹量基数）
        w = make_world(14)
        u = _armed(w, SMOKE_BATT_TPL, 0, (100000, 100000))
        self.assertTrue(cmd_fire_mission(w, u, FireMissionForm.POINT,
                                         (120000, 100000), 1,
                                         "HE", SalvoMode.FULL, 0))
        fm = u.fire_mission
        self.assertEqual(fm.ammo, "HE")
        self.assertEqual(fm.shots_left, 6)      # 基数=主武器 HE_W.ammo_base
        from sovs.sim.tick import process_fire_mission
        process_fire_mission(w, u)
        self.assertEqual(len(w.projectiles), 1)             # HE 落 Projectile
        self.assertEqual(len(w.smoke_zones), 0)
        self.assertEqual(u.elements[0].weapon_states[0].ammo_left, 5)   # 主武器耗弹
        self.assertEqual(u.elements[0].weapon_states[1].ammo_left, 4)   # 烟档不动


class TestAirStrikeAxis(unittest.TestCase):
    """② GP-01 §4 ③段：K+拖拽画线攻击轴。"""

    def _aircraft(self, w, pos):
        a = AircraftInstance(id=w.next_aircraft_id, team=0, player_index=0,
                             template=CARD_OBJECTS["IL2M"], pos=pos,
                             alt_tier=AltTier.LOW, hp_current=100)
        w.next_aircraft_id += 1
        a.ammo_left["BOMB"] = 2
        w.aircraft.append(a)
        return a

    def test_axis_derives_run_points_from_player_line(self):
        # 画线 (400000,500000)→(600000,500000)＝向东攻击；target=(500000,500000)。
        # run 轴沿东西向（rs=target−lead·东=(492000,500000)），与机位（正北
        # 100000cm）无关——机位向会给南北轴，即证 axis 生效且解耦。
        w = make_world(15)
        a = self._aircraft(w, (500000, 600000))
        self.assertTrue(cmd_air_strike(w, a, (500000, 500000), "BOMB",
                                       axis=((400000, 500000), (600000, 500000))))
        self.assertEqual(a.task.run_start, (492000, 500000))   # 8000cm lead·DIR8[2]
        self.assertEqual(a.task.run_end, (508000, 500000))
        self.assertEqual(a.flight_plan, [(492000, 500000)])

    def test_axis_none_keeps_bearing_run(self):
        # 缺省 None=现行为：run 轴按机位向（机位正北→由北向南穿目标）
        w = make_world(16)
        a = self._aircraft(w, (500000, 600000))
        self.assertTrue(cmd_air_strike(w, a, (500000, 500000), "BOMB"))
        self.assertEqual(a.task.run_start, (500000, 508000))
        self.assertEqual(a.task.run_end, (500000, 492000))


class TestSonarStep(unittest.TestCase):
    """③ GP-01 §3 表行13：sonar_step（IntelCircle 唯一写者，R-03 回路闭合）。"""

    def _world(self):
        w = make_world(17)
        listener = add_unit(w, make_unit(w, SONAR_TPL, 0, 0, (100000, 100000)))
        listener.deploy_state = DeployState.DEPLOYED
        gun = _armed(w, HE_ONLY_TPL, 1, (105000, 100000))     # 距声测班 5000≤30000
        return w, listener, gun

    def test_accumulate_locate_then_narrow(self):
        # acoustic_signature=1、sonar_rate=60：两拍 accum=120 过 threshold=100
        # →圈出（radius=6000−4500×20÷100=5100）；再开火收窄至 2400；封顶 1500
        w, _lst, gun = self._world()
        w.tick = 1
        upsert_sound_track(w, gun, gun.pos)
        sonar_step(w)
        self.assertEqual(len(w.intel_circles), 0)             # accum=60 未达门
        w.tick = 2
        upsert_sound_track(w, gun, gun.pos)
        sonar_step(w)
        self.assertEqual(len(w.intel_circles), 1)
        c = w.intel_circles[0]
        self.assertIsInstance(c, IntelCircle)
        self.assertEqual(c.team, 0)                           # 圈记侦听方队（审查#2）
        self.assertIs(c.source_unit, gun)                     # (team, source_unit) 键
        self.assertEqual(c.center, gun.pos)
        self.assertEqual(c.radius_cm, 5100)
        w.tick = 3
        upsert_sound_track(w, gun, gun.pos)
        sonar_step(w)
        self.assertEqual(w.intel_circles[0].radius_cm, 2400)  # accum=180→t=80
        w.tick = 4
        upsert_sound_track(w, gun, gun.pos)
        sonar_step(w)
        self.assertEqual(w.intel_circles[0].radius_cm, 1500)  # t 封顶→min
        self.assertEqual(len(w.intel_circles), 1)             # 同炮 upsert 不增圈

    def test_cease_fire_freezes_circle(self):
        # C4③：停火超 sonar_hold_ticks（100）accum 不增长、圈冻结
        w, _lst, gun = self._world()
        for t in (1, 2, 3):                     # 逐拍开火+侦听：accum=180→圈 2400
            w.tick = t
            upsert_sound_track(w, gun, gun.pos)
            sonar_step(w)
        self.assertEqual(len(w.intel_circles), 1)
        before_radius = w.intel_circles[0].radius_cm
        accum_before = w.sound_tracks[0].accum
        w.tick = 3 + 101                                       # 停火 101 拍>100
        sonar_step(w)
        self.assertEqual(w.intel_circles[0].radius_cm, before_radius)  # 冻结不撤销
        self.assertEqual(w.sound_tracks[0].accum, accum_before)  # accum 亦冻结

    def test_move_reset_restarts_accum(self):
        # C4②：换阵地（>sonar_move_reset_cm=3000）accum 清零重计
        w, _lst, gun = self._world()
        for t in (1, 2, 3):                     # 先建圈（accum=180）
            w.tick = t
            upsert_sound_track(w, gun, gun.pos)
            sonar_step(w)
        self.assertEqual(len(w.intel_circles), 1)
        w.tick = 4
        upsert_sound_track(w, gun, (120000, 100000))           # 移动 15000>3000
        self.assertEqual(w.sound_tracks[0].accum, 0)
        sonar_step(w)
        self.assertEqual(w.sound_tracks[0].accum, 60)          # 重计（未达定位门）
        self.assertEqual(len(w.intel_circles), 1)              # 圈冻结不撤销

    def test_listener_gates(self):
        # 未展开（MOBILE）＝「静止展开」口径：不侦听、无圈
        w, listener, gun = self._world()
        listener.deploy_state = DeployState.MOBILE
        w.tick = 1
        upsert_sound_track(w, gun, gun.pos)
        w.tick = 2
        upsert_sound_track(w, gun, gun.pos)
        sonar_step(w)
        self.assertEqual(len(w.intel_circles), 0)
        # 声源在 sonar_radius_cm 外：有效侦听者空→圈冻结（不出新圈）
        listener.deploy_state = DeployState.DEPLOYED
        gun.elements[0].pos = (200000, 100000)                 # 距 100000>30000
        gun.pos = (200000, 100000)
        w.tick = 3
        upsert_sound_track(w, gun, gun.pos)
        sonar_step(w)
        self.assertEqual(len(w.intel_circles), 0)


class TestRejectionLog(unittest.TestCase):
    """④ GP-01 §4 ④段：命令拒绝环形日志。"""

    def test_ring_buffer_capacity_32(self):
        # 无 INDIRECT 位单位连发 40 令（一次 world_tick 全消费）→环形留 32
        w = make_world(18)
        nb = add_unit(w, make_unit(w, SONAR_TPL, 0, 0, (0, 0)))
        for _ in range(40):
            queue_command(w, FireMissionCmd(unit=nb, form=FireMissionForm.POINT,
                                            point=(1, 1)))
        world_tick(w)
        self.assertEqual(len(w.rejection_log), REJECTION_LOG_CAP)
        self.assertEqual(REJECTION_LOG_CAP, 32)
        self.assertEqual(w.rejection_log[-1]["tick"], w.tick)

    def test_rejection_log_not_in_state_fingerprint(self):
        # 回放校验和面零扰动：同 seed 双世界推同拍数——一个落拒令（写日志）、
        # 一个不落，指纹逐字节相等（拒令零副作用+rejection_log 不进指纹面）。
        w1 = make_world(19)
        u = add_unit(w1, make_unit(w1, SONAR_TPL, 0, 0, (0, 0)))
        queue_command(w1, FireMissionCmd(unit=u, form=FireMissionForm.POINT,
                                         point=(1, 1)))
        world_tick(w1)
        w2 = make_world(19)
        add_unit(w2, make_unit(w2, SONAR_TPL, 0, 0, (0, 0)))
        world_tick(w2)
        self.assertEqual(len(w1.rejection_log), 1)
        self.assertEqual(len(w2.rejection_log), 0)
        self.assertEqual(state_fingerprint_text(w1), state_fingerprint_text(w2))


class TestStateFrame11(unittest.TestCase):
    """⑤ GP-01 §4 ①段：状态帧 1.1（飞机富化＋air_cooldowns＋rejections）。"""

    def _world_with_aircraft(self):
        w = make_world(20)
        a = AircraftInstance(id=w.next_aircraft_id, team=0, player_index=0,
                             template=CARD_OBJECTS["YAK9"], pos=(400000, 400000),
                             alt_tier=AltTier.LOW, hp_current=80)
        w.next_aircraft_id += 1
        a.facing = 135
        a.engage_air = False                    # YAK9 战斗机→有对空槽
        a.task = AirTask(kind=TaskKind.PATROL, center=(400000, 400000), radius=3000)
        a.alt_pending = (AltTier.HIGH, 3)
        w.aircraft.append(a)
        w.players[0].air_cooldowns[CARD_OBJECTS["YAK9"].template_id] = 120
        return w, a

    def test_aircraft_entry_new_keys(self):
        w, a = self._world_with_aircraft()
        f = state_frame(w, None)
        entry = f["aircraft"][0]
        self.assertEqual(f["schema_version"], "1.1")
        self.assertEqual(entry["facing"], 135)
        self.assertIs(entry["engage_air"], False)
        self.assertEqual(entry["task"],
                         {"kind": "patrol", "center": [400000, 400000],
                          "radius": 3000})
        self.assertEqual(entry["alt_pending"], {"tier": "high", "ticks_left": 3})

    def test_task_summary_strike_and_airdrop_and_none(self):
        w, _a = self._world_with_aircraft()
        a = w.aircraft[0]
        a.task = AirTask(kind=TaskKind.STRIKE, weapon="BOMB", target=(1, 2))
        self.assertEqual(state_frame(w, None)["aircraft"][0]["task"],
                         {"kind": "strike", "weapon": "BOMB", "target": [1, 2]})
        a.task = AirTask(kind=TaskKind.AIRDROP, drop=(3, 4))
        self.assertEqual(state_frame(w, None)["aircraft"][0]["task"],
                         {"kind": "airdrop", "drop": [3, 4]})
        a.task = None
        self.assertIsNone(state_frame(w, None)["aircraft"][0]["task"])

    def test_player_entry_air_cooldowns(self):
        w, _a = self._world_with_aircraft()
        f = state_frame(w, 0)
        tid = CARD_OBJECTS["YAK9"].template_id
        self.assertEqual(f["players"][0]["air_cooldowns"], {tid: 120})

    def test_rejections_tail8_and_view_filter(self):
        w, a = self._world_with_aircraft()
        enemy = add_unit(w, make_unit(w, SONAR_TPL, 1, 0, (900000, 900000)))
        for i in range(10):                     # 己方飞机 10 条拒绝（ref_id=a.id）
            w.rejection_log.append({"tick": i, "cmd": "AirAltCmd", "ref_id": a.id})
        w.rejection_log.append({"tick": 99, "cmd": "FireMissionCmd",
                                "ref_id": enemy.id})          # 敌方未发现单位
        judge = state_frame(w, None)["rejections"]
        self.assertEqual(len(judge), 8)                       # 尾 8 条
        self.assertEqual(judge[-1]["tick"], 99)               # 裁判全知全量
        mine = state_frame(w, 0)["rejections"]
        self.assertEqual(len(mine), 8)
        self.assertTrue(all(r["ref_id"] == a.id for r in mine))   # 敌方条目被滤


class TestWire11(unittest.TestCase):
    """⑥ wire 1.1：ammo/axis 编解码＋旧 1.0 文件 fail-fast。"""

    def _world(self, seed=21):
        w = make_world(seed)
        u = _armed(w, SMOKE_BATT_TPL, 0, (100000, 100000))
        a = AircraftInstance(id=w.next_aircraft_id, team=0, player_index=0,
                             template=CARD_OBJECTS["IL2M"], pos=(500000, 600000),
                             alt_tier=AltTier.LOW, hp_current=100)
        w.next_aircraft_id += 1
        w.aircraft.append(a)
        return w, u, a

    def test_fire_mission_ammo_roundtrip(self):
        w, u, _a = self._world()
        for ammo in ("HE", "SMOKE"):
            cmd = FireMissionCmd(unit=u, form=FireMissionForm.POINT,
                                 point=(1, 2), ammo_mult=2, ammo=ammo,
                                 salvo_mode=SalvoMode.HALF, creep_speed=7)
            wire = encode_command(cmd)
            self.assertEqual(wire["ammo"], ammo)              # 恒写（1.1 面）
            back = decode_command(w, wire)
            self.assertIs(back.unit, u)
            self.assertEqual(back.ammo, ammo)
        # 缺省 HE：encode 恒写、无键旧 dict 解码回 HE（缺省=1.0 行为）
        self.assertEqual(encode_command(
            FireMissionCmd(unit=u, form=FireMissionForm.POINT, point=(1, 2)))["ammo"],
            "HE")

    def test_air_strike_axis_roundtrip(self):
        w, _u, a = self._world()
        axis = ((400000, 500000), (600000, 500000))
        from sovs.sim.tick import AirStrikeCmd
        c = AirStrikeCmd(aircraft=a, target=(500000, 500000), weapon="BOMB",
                         axis=axis)
        wire = encode_command(c)
        self.assertEqual(wire["axis"], [[400000, 500000], [600000, 500000]])
        back = decode_command(w, wire)
        self.assertIs(back.aircraft, a)
        self.assertEqual(back.axis, ((400000, 500000), (600000, 500000)))
        # 缺省 None：wire 恒写 null、无键旧 dict 解码回 None
        c2 = AirStrikeCmd(aircraft=a, target=(500000, 500000), weapon="BOMB")
        self.assertIsNone(encode_command(c2)["axis"])

    def test_old_1_0_replay_file_fails_fast(self):
        # 升版后旧 1.0 文件在 load_replay schema_version 门 fail-fast（预期行为）
        w, u, _a = self._world(22)
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "old.jsonl"
            with ReplayWriter(path, world=w, seed=22,
                              scenario="kev_game_demo.v1") as rw:
                rw.command(0, 0, FireMissionCmd(unit=u,
                                                form=FireMissionForm.POINT,
                                                point=(1, 2)))
            header, _records = load_replay(path)              # 现版本自读通过
            self.assertEqual(header["schema_version"], "1.4")  # 终审修复块升版
            #（1.3→1.4＝+CreateDumpCmd 卸货成堆——basics:202-204）
                                                                # （1.2→1.3 非向后
                                                                # 兼容——六新命令族）
            lines = path.read_text(encoding="utf-8").splitlines()
            old = json.loads(lines[0])
            old["schema_version"] = "1.0"                     # 篡改回旧版
            lines[0] = json.dumps(old, ensure_ascii=False,
                                  separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_replay(path)
            self.assertIn("schema_version", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
