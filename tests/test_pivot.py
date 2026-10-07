"""PB-51 原地转向（2026-10-04 拍板纳入——断箭 N17 neutral steering/映射 §五.9；
推翻 MOVEMENT_PSEUDOCODE_v1.2 §2.13 reject 的**静止分支**：静止车体改朝向不再即时，
耗时=|角差|÷类分档速率整数推导；移动中 facing 仍即时 8 扇区——两口径成文分立）。

覆盖面：速率表 pin（履带快于轮带）/耗时随角度差（TRACK 180°=23t、WHEEL 180°=30t、
短角差到位拍即完）/负角归一/转向期间禁射（fire_permitted ⑧ 门 + ground_direct
集成：READY 冻结→转完 AIMING）/GAP-25 改锚（pivot 期间 narrow-arc 元素 rotating
维持 TRUE=SIDE 暴露、转完复位）/互斥不变式（cmd_pivot 停车、外部新移动令清 pivot、
StopCmd 中止、排队移动令等 pivot 完成）/三前置门（展开收起/整班车载/全被拖）/
被拖元素不随动。锚点全部手推写死，不自证；零掷骰（不触任何 PCG32 通道）。"""
import unittest

from sovs.sim.combat import compute_hit_facing
from sovs.sim.tick import (MoveCmd, PivotCmd, StopCmd, add_unit, cmd_pivot,
                           fire_permitted, make_unit, make_world, queue_command,
                           world_tick)
from sovs.sim.types import (DeployState, ElementTemplate, ElementType, Facing,
                            MovementClass, TowState, UnitTemplate, UnitType,
                            WeaponTemplate, WState)
from sovs.sim.tables import CONFIG

# 直射武器（禁射门集成用：360° 弧——不与 R-09 射界门混淆，纯测 ⑧ 门）
PIV_W = WeaponTemplate(name="PIV_W", damage=10, max_range_cm=40000, aim_time_ticks=2,
                       reload_time_ticks=20, ammo_base=10, accuracy_base_bp=10000,
                       projectile_speed_cm_tick=100)


def _tpl(movement_class=MovementClass.TRACK, fire_arc=360, n_elements=1):
    """合成模板（测试用，不对应真实卡；template_id 59x 段）。"""
    return UnitTemplate(
        template_id=590, name="pivot", category=2, cost=50,
        element_templates=tuple(
            ElementTemplate(element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
                            hp_max=10, fire_arc_deg=fire_arc, weapons=(PIV_W,))
            for _ in range(n_elements)),
        optics_ground_cm=20000, stealth_base=5, speed_tier=2,
        movement_class=movement_class)


class TestPivotCfg(unittest.TestCase):
    """tables.py 速率表 pin——数值占位（N17 无数值/N15 60/80 疑占位对调指派）待数值
    章节定标；本锚只锁「FOOT/WHEEL/TRACK/HORSE 序 + 履带快于轮式」拍板方向。"""

    def test_table_pin(self):
        self.assertEqual(CONFIG.pivot_rate_deg_per_tick, (10, 6, 8, 10))

    def test_track_faster_than_wheel(self):
        r = CONFIG.pivot_rate_deg_per_tick
        self.assertGreater(r[MovementClass.TRACK], r[MovementClass.WHEEL])


class TestPivotDuration(unittest.TestCase):
    """耗时=⌈|角差|/速率⌉ 拍（步进同 rotate_step：|diff|<=step 直接到位）。"""

    def _unit(self, cls=MovementClass.TRACK, fire_arc=360):
        w = make_world(11)
        return w, add_unit(w, make_unit(w, _tpl(cls, fire_arc), 0, 0, (0, 0)))

    def test_track_180_takes_23_ticks(self):
        w, u = self._unit()
        e = u.elements[0]
        e.facing = 0
        self.assertTrue(cmd_pivot(u, 180))
        for t in range(1, 23):                      # 前 22 拍每拍 +8（22×8=176）
            world_tick(w)
            self.assertEqual(u.pivot_to, 180)        # 未完：目标槽保持
            self.assertEqual(e.facing, 8 * t)
        world_tick(w)                               # 第 23 拍 |176−180|=4 ≤ 8 → 到位
        self.assertEqual(u.pivot_to, -1)
        self.assertEqual(e.facing, 180)

    def test_wheel_slower_than_track(self):
        w, u = self._unit(MovementClass.WHEEL)      # 速率 6 → 180°=30 拍
        e = u.elements[0]
        e.facing = 0
        cmd_pivot(u, 180)
        for _ in range(23):
            world_tick(w)
        self.assertNotEqual(e.facing, 180)          # TRACK 同角差 23 拍已完、WHEEL 未完
        self.assertEqual(u.pivot_to, 180)
        for _ in range(7):
            world_tick(w)
        self.assertEqual(e.facing, 180)
        self.assertEqual(u.pivot_to, -1)

    def test_small_angle_snaps_first_tick(self):
        w, u = self._unit()
        e = u.elements[0]
        e.facing = 0
        cmd_pivot(u, 5)                             # |5| ≤ 8 → 第一拍直接到位
        world_tick(w)
        self.assertEqual(u.pivot_to, -1)
        self.assertEqual(e.facing, 5)

    def test_negative_facing_normalized(self):
        w, u = self._unit()
        e = u.elements[0]
        e.facing = 350
        self.assertTrue(cmd_pivot(u, -90))          # −90 % 360 = 270（整型归一）
        self.assertEqual(u.pivot_to, 270)
        for _ in range(10):                         # |angle_diff(270,350)|=80 → 10 拍
            world_tick(w)
        self.assertEqual(u.pivot_to, -1)
        self.assertEqual(e.facing, 270)

    def test_towed_element_skipped(self):
        w = make_world(17)
        u = add_unit(w, make_unit(w, _tpl(n_elements=2), 0, 0, (0, 0)))
        e0, e1 = u.elements
        e0.facing = e1.facing = 0
        e1.towed = TowState.TOWED                   # 被拖元素由牵引方带动，不随本单位转向
        cmd_pivot(u, 90)
        for _ in range(12):                         # 90/8 → 12 拍（11×8=88 后到位）
            world_tick(w)
        self.assertEqual(u.pivot_to, -1)
        self.assertEqual(e0.facing, 90)
        self.assertEqual(e1.facing, 0)              # GAP-03 同谓词：被拖不随动


class TestPivotNoFire(unittest.TestCase):
    """⑧ 禁射门：pivot 期间不开新 AIMING（ground_direct 集成）；转完即恢复。"""

    def _pair(self):
        w = make_world(13)
        u = add_unit(w, make_unit(w, _tpl(), 0, 0, (0, 0)))
        v = add_unit(w, make_unit(w, _tpl(), 1, 0, (15000, 0)))   # 敌 15000cm 东侧
        v.spotted_mask = 1                          # 已发现（队 0 位；侦测范围内稳定）
        return w, u, v

    def test_fire_permitted_gate8(self):
        w, u, _v = self._pair()
        e = u.elements[0]
        ws = e.weapon_states[0]
        self.assertTrue(fire_permitted(w, u, e, ws))    # 常态放行
        u.pivot_to = 90
        self.assertFalse(fire_permitted(w, u, e, ws))  # ⑧ pivot 期间禁射
        u.pivot_to = -1
        self.assertTrue(fire_permitted(w, u, e, ws))

    def test_no_aim_during_pivot_and_resume_after(self):
        w, u, _v = self._pair()
        e = u.elements[0]
        e.facing = 270                              # 敌在 90 方位；270→90 = 180° = 23 拍
        cmd_pivot(u, 90)
        for _ in range(10):
            world_tick(w)
        self.assertEqual(u.pivot_to, 90)
        self.assertTrue(all(ws.state is WState.READY                   # 转向中禁射
                            for ws in e.weapon_states))
        for _ in range(13):                         # 共 23 拍：pivot 完成
            world_tick(w)
        self.assertEqual(u.pivot_to, -1)
        self.assertTrue(any(ws.state is WState.AIMING                  # 转完即可射
                            for ws in e.weapon_states))


class TestPivotRotating(unittest.TestCase):
    """GAP-25 改锚：pivot 期间 fire_arc<360 元素 rotating 维持 TRUE（SIDE 暴露窗口，
    R-09 同语义）；非 pivot 拍清零（原 GAP-25 语义保持）。360° 炮塔载具不受影响
    （方案6 现状口径——rotating 仅 narrow-arc 消费）。"""

    def test_rotating_held_during_pivot_and_cleared_after(self):
        w = make_world(19)
        u = add_unit(w, make_unit(w, _tpl(fire_arc=30), 0, 0, (0, 0)))
        e = u.elements[0]
        e.facing = 0
        cmd_pivot(u, 180)
        world_tick(w)
        self.assertTrue(e.rotating)                 # 转向中：SIDE 暴露
        self.assertIs(compute_hit_facing(e, 180, CONFIG), Facing.SIDE)  # 正面来袭也吃侧面
        for _ in range(22):                         # 共 23 拍完成
            world_tick(w)
        self.assertEqual(u.pivot_to, -1)
        self.assertFalse(e.rotating)                # 同拍 GAP-25 已按新式复位
        self.assertIs(compute_hit_facing(e, 180, CONFIG), Facing.FRONT)  # 恢复几何面

    def test_turret_unit_unaffected(self):
        w = make_world(23)
        u = add_unit(w, make_unit(w, _tpl(fire_arc=360), 0, 0, (0, 0)))
        e = u.elements[0]
        e.facing = 0
        cmd_pivot(u, 180)
        world_tick(w)
        self.assertFalse(e.rotating)                # 360° 模板不分配 rotating 语义（方案6）
        self.assertIs(compute_hit_facing(e, 0, CONFIG), Facing.FRONT)


class TestPivotExclusivity(unittest.TestCase):
    """互斥不变式：pivot_to>=0 ⇒ move_path 恒空（双写点保证）+ 后令胜出。"""

    def _unit(self):
        w = make_world(29)
        return w, add_unit(w, make_unit(w, _tpl(), 0, 0, (0, 0)))

    def test_dispatch_via_queue_command(self):
        w, u = self._unit()
        u.elements[0].facing = 0
        queue_command(w, PivotCmd(unit=u, facing_deg=180))     # 世界级收件箱入口
        world_tick(w)                                          # 命令落地 + 第一拍推进
        self.assertEqual(u.pivot_to, 180)
        self.assertEqual(u.elements[0].facing, 8)

    def test_pivot_halts_active_move(self):
        w, u = self._unit()
        queue_command(w, MoveCmd(unit=u, path=[(50000, 0)]))
        world_tick(w)
        self.assertTrue(u.move_path)                           # 在途移动令
        self.assertTrue(cmd_pivot(u, 0))                       # 原地转向=停车后转
        self.assertEqual(u.move_path, [])
        self.assertEqual(u.move_mode.value, 0)                 # NORMAL 复位（HaltCmd 语义）
        self.assertEqual(u.pivot_to, 0)

    def test_new_move_order_cancels_pivot(self):
        w, u = self._unit()
        u.elements[0].facing = 0
        cmd_pivot(u, 180)
        world_tick(w)
        self.assertEqual(u.elements[0].facing, 8)
        queue_command(w, MoveCmd(unit=u, path=[(50000, 0)]))   # 外部非排队新令（后令胜出）
        world_tick(w)
        self.assertEqual(u.pivot_to, -1)                       # pivot 取消
        self.assertTrue(u.move_path)                           # 移动接管
        self.assertEqual(u.elements[0].facing, 90)             # 移动 facing=即时 8 扇区（§2.13 移动分支）

    def test_stop_cancels_pivot(self):
        w, u = self._unit()
        u.elements[0].facing = 0
        cmd_pivot(u, 180)
        world_tick(w)
        self.assertEqual(u.elements[0].facing, 8)
        queue_command(w, StopCmd(unit=u))
        world_tick(w)
        self.assertEqual(u.pivot_to, -1)                       # 停止令中止转向
        world_tick(w)
        self.assertEqual(u.elements[0].facing, 8)              # 不转完即停（停在半途朝向）

    def test_queued_move_waits_for_pivot(self):
        w, u = self._unit()
        u.elements[0].facing = 0
        cmd_pivot(u, 180)
        queue_command(w, MoveCmd(unit=u, path=[(50000, 0)], queue=True))   # 排队令
        world_tick(w)
        self.assertEqual(u.pivot_to, 180)                      # pivot 进行中：队列头不安装
        self.assertFalse(u.move_path)
        self.assertEqual(len(u.command_queue), 1)
        for _ in range(22):                                    # 共 23 拍：pivot 完成
            world_tick(w)
        self.assertEqual(u.pivot_to, -1)
        world_tick(w)                                          # 下一拍队列头安装
        self.assertTrue(u.move_path)


class TestPivotGates(unittest.TestCase):
    """cmd_pivot 三前置门（issue_move 同款）：展开/收起互锁、整班车载、全被拖。"""

    def _unit(self):
        w = make_world(31)
        return w, add_unit(w, make_unit(w, _tpl(), 0, 0, (0, 0)))

    def test_deploying_rejected(self):
        _w, u = self._unit()
        u.deploy_state = DeployState.DEPLOYING
        self.assertFalse(cmd_pivot(u, 90))
        self.assertEqual(u.pivot_to, -1)
        u.deploy_state = DeployState.PACKING
        self.assertFalse(cmd_pivot(u, 90))
        self.assertEqual(u.pivot_to, -1)

    def test_all_mounted_rejected(self):
        _w, u = self._unit()
        u.elements[0].mounted_in = object()        # 整班车载（门 3 判据：全 mounted_in）
        self.assertFalse(cmd_pivot(u, 90))
        self.assertEqual(u.pivot_to, -1)

    def test_all_towed_rejected(self):
        _w, u = self._unit()
        u.elements[0].towed = TowState.TOWED       # 全被拖：由牵引方带动
        self.assertFalse(cmd_pivot(u, 90))
        self.assertEqual(u.pivot_to, -1)


if __name__ == "__main__":
    unittest.main()
