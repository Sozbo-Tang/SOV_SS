"""士气状态机测试（2026-10-04 士气块——GDD-00 D014 四态/D025 阈值制/GDD-05 下篇
B0~B4 落地，拍板清单 PB-54）：
- 逐档迁移与边界（40/70/100 占位阈值：≥ 阈值进档、衰减回落降档）；
- 聚合=max 存活元素压制（最差元素定档——PB-49 语义自洽）；
- 阈值占位可调（BalanceConfig 覆盖生效——D025「数值待配」）；
- 溃逃：进入拍清玩家令+装向己方部署区锚点航点、失控五门（issue_move 门0 含
  queue 入队/cmd_halt/cmd_pivot/cmd_sprint/consume_unit_commands）、强制移动、
  routed_until 到拍原地重整回 SUPPRESSED（B4:182 默认=D014 待定②留痕）、
  仍在碾压火力下再溃逃；
- PB-49 全链激活：pinned() 判据缝读 morale 真槽（钉住=可动减速，非旧文「无法
  移动」）+ 冲刺破压制降档。

锚点算术（手推不自证）：
- FOOT speed_tier 3：档 3=70 × 越野 8000‰ = 56 cm/tick（溃逃全速——ROUTED 不走
  pinned 减半缝）；钉住=56×5000//10000=28；
- 拍内序锚：world_tick ①system_timers 衰减先于 ⑤.5 system_morale 判态——直设
  suppression=100 经一拍 world_tick 判态时为 99（PINNED 非 ROUTED），登记表
  留待项⑨ 的可观测行为锚。
"""
import unittest
from dataclasses import replace

from sovs.sim.movement import issue_move, move_speed_cm_tick, pinned
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (MoveCmd, StopCmd, add_unit, cmd_halt, cmd_pivot,
                           cmd_sprint, consume_commands, make_unit,
                           make_world, queue_command, system_morale,
                           world_tick)
from sovs.sim.types import (ElementTemplate, ElementType, MoraleState,
                            MovementClass, UnitInstance, UnitTemplate,
                            UnitType)


def foot_tpl(template_id=950, n_elements=1, speed_tier=3):
    ets = tuple(ElementTemplate(element_type=ElementType.SQUAD,
                                unit_type=UnitType.INFANTRY, hp_max=10)
                for _ in range(n_elements))
    return UnitTemplate(template_id=template_id, name="foot plt", category=1,
                        cost=40, element_templates=ets, optics_ground_cm=20000,
                        stealth_base=5, speed_tier=speed_tier,
                        movement_class=MovementClass.FOOT)


def mk_unit(w, tpl, team=0, pos=(500000, 400000)):
    return add_unit(w, make_unit(w, tpl, team, team, pos))


class TestMoraleSlots(unittest.TestCase):
    def test_defaults_and_slot_count(self):
        w = make_world(3)
        u = mk_unit(w, foot_tpl())
        self.assertIs(u.morale, MoraleState.STABLE)
        self.assertEqual(u.routed_until, -1)          # -1 哨兵（pivot_to 同款风格）
        self.assertFalse(pinned(u))
        import dataclasses
        names = [f.name for f in dataclasses.fields(UnitInstance)]
        self.assertIn("morale", names)
        self.assertIn("routed_until", names)
        self.assertEqual(len(names), 31)              # 23→25（士气 +2）→26（还击窗）
                                                       # →30（P1 机制块 2026-10-13
                                                       # +rtb_pending/radar_on/
                                                       # radar_ready_tick/supply_switches）
                                                       # →31（终审修复块 2026-10-13
                                                       # +dump_pending 卸货成堆在途位）
        # （P0 键位纠偏块 2026-10-13 +return_fire_until 受击还击窗槽）


class TestTierTransitions(unittest.TestCase):
    """D025 阈值制：≥ 阈值进档、衰减回落降档（system_morale 直调——阈值判定本体）。"""

    def setUp(self):
        self.w = make_world(5)
        self.u = mk_unit(self.w, foot_tpl())
        self.e = self.u.elements[0]

    def _eval(self, sup):
        self.e.suppression = sup
        system_morale(self.w, CONFIG)
        return self.u.morale

    def test_boundaries(self):
        for sup, expect in [(0, MoraleState.STABLE), (39, MoraleState.STABLE),
                            (40, MoraleState.SUPPRESSED), (69, MoraleState.SUPPRESSED),
                            (70, MoraleState.PINNED), (99, MoraleState.PINNED),
                            (100, MoraleState.ROUTED)]:
            self.assertIs(self._eval(sup), expect, sup)

    def test_downgrade_on_decay(self):
        # D025：随时间衰减回落时降档——非 ROUTED 态压制值回落，状态逐级下降
        self.assertIs(self._eval(90), MoraleState.PINNED)
        self.assertIs(self._eval(70), MoraleState.PINNED)
        self.assertIs(self._eval(69), MoraleState.SUPPRESSED)
        self.assertIs(self._eval(40), MoraleState.SUPPRESSED)
        self.assertIs(self._eval(39), MoraleState.STABLE)

    def test_world_tick_decay_integration(self):
        # 衰减本体=①system_timers 既有环：41→经一拍衰减 40→判态 SUPPRESSED（含拍内序锚）
        self.e.suppression = 41
        self.u.morale = MoraleState.STABLE
        world_tick(self.w, CONFIG)
        self.assertEqual(self.e.suppression, 40)
        self.assertIs(self.u.morale, MoraleState.SUPPRESSED)
        for _ in range(40):
            world_tick(self.w, CONFIG)
        self.assertEqual(self.e.suppression, 0)
        self.assertIs(self.u.morale, MoraleState.STABLE)

    def test_world_tick_order_decay_before_morale(self):
        # 登记表留待项⑨ 行为锚：同拍内 ①衰减 先于 ⑤.5 判态——直设 100 经一拍判 99=PINNED
        self.e.suppression = 100
        world_tick(self.w, CONFIG)
        self.assertEqual(self.e.suppression, 99)
        self.assertIs(self.u.morale, MoraleState.PINNED)

    def test_config_thresholds_override(self):
        # 阈值占位可调（D025「数值待配」——BalanceConfig 单点出表）
        cfg2 = replace(CONFIG, morale_sup_th=10, morale_pin_th=20,
                       morale_rout_th=30, morale_rally_ticks=50)
        self.e.suppression = 15
        system_morale(self.w, cfg2)
        self.assertIs(self.u.morale, MoraleState.SUPPRESSED)
        self.e.suppression = 25
        system_morale(self.w, cfg2)
        self.assertIs(self.u.morale, MoraleState.PINNED)
        self.e.suppression = 30
        system_morale(self.w, cfg2)
        self.assertIs(self.u.morale, MoraleState.ROUTED)
        self.assertEqual(self.u.routed_until, self.w.tick + 50)   # 重整时长同表可调

    def test_constants_pin(self):
        # 表 pin（数值全占位待定标——D025/GDD-05 B4 默认）
        self.assertEqual((CONFIG.morale_sup_th, CONFIG.morale_pin_th,
                          CONFIG.morale_rout_th, CONFIG.morale_rally_ticks),
                         (40, 70, 100, 300))

    def test_dead_unit_skipped(self):
        self.u.alive = False
        self.e.suppression = 100
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.STABLE)   # 不写死者


class TestAggregation(unittest.TestCase):
    def test_max_over_elements(self):
        # 聚合=max（最差元素定档）：(10, 90) → PINNED；压制本体保持元素级不动
        w = make_world(7)
        u = mk_unit(w, foot_tpl(n_elements=3))
        u.elements[0].suppression = 10
        u.elements[1].suppression = 90
        u.elements[2].suppression = 30
        system_morale(w, CONFIG)
        self.assertIs(u.morale, MoraleState.PINNED)
        self.assertEqual([e.suppression for e in u.elements], [10, 90, 30])

    def test_destroyed_element_excluded(self):
        # 元素销毁=物理移除（combat.destroy_element §D.4 不变式）——聚合天然只算存活
        w = make_world(7)
        u = mk_unit(w, foot_tpl(n_elements=2))
        u.elements.remove(u.elements[1])
        u.elements[0].suppression = 15
        system_morale(w, CONFIG)
        self.assertIs(u.morale, MoraleState.STABLE)


class TestRouted(unittest.TestCase):
    """D014 溃逃：失控强制移动 + routed_until 到拍原地重整（B4:182 默认）。"""

    def setUp(self):
        self.w = make_world(11)
        self.u = mk_unit(self.w, foot_tpl())          # team0 @ (500000, 400000)
        self.e = self.u.elements[0]

    def _rout(self):
        self.e.suppression = 100
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.ROUTED)

    def test_entry_clears_orders_installs_flee_path(self):
        self.u.command_queue = [MoveCmd(unit=self.u, path=[(123, 123)])]
        self.u.move_path = [(1, 1)]
        self._rout()
        self.assertEqual(self.u.routed_until, self.w.tick + 300)   # B4:182「30s」=300t 占位
        self.assertEqual(self.u.command_queue, [])                  # 清玩家令
        # 溃逃航点=己方部署区锚点（team0 南底边中点——_deploy_anchor 近似口径）
        self.assertEqual(self.u.move_path, [(self.w.map_center[0], 0)])

    def test_team1_flees_to_north_edge(self):
        w2 = make_world(12)
        u2 = mk_unit(w2, foot_tpl(template_id=951), team=1)
        u2.elements[0].suppression = 100
        system_morale(w2, CONFIG)
        self.assertEqual(u2.move_path, [(w2.map_center[0], w2.map_extent[1])])

    def test_flee_movement_full_speed(self):
        # ROUTED 全速强制移动（不走 pinned 减半缝）：56/tick；判态拍后一拍起位移
        self._rout()                                   # world.tick=0 时判态
        self.assertEqual(self.u.pos, (500000, 400000))
        world_tick(self.w, CONFIG)                     # tick1：位移 56
        world_tick(self.w, CONFIG)                     # tick2：位移 56
        self.assertEqual(self.u.pos, (500000, 400000 - 2 * 56))
        self.assertIs(self.u.morale, MoraleState.ROUTED)   # 计时态：压制已衰减仍 ROUTED

    def test_control_lockout_five_gates(self):
        self._rout()
        path = list(self.u.move_path)
        # 门0a：外部非排队移动令拒令
        self.assertFalse(issue_move(self.w, CONFIG,
                                    MoveCmd(unit=self.u, path=[(9, 9)])))
        # 门0b：queue=TRUE 入队支同拒（失控期间不得预排队）
        self.assertFalse(issue_move(self.w, CONFIG,
                                    MoveCmd(unit=self.u, path=[(9, 9)], queue=True)))
        self.assertEqual(self.u.command_queue, [])
        # cmd_halt / cmd_pivot / cmd_sprint 三门
        cmd_halt(self.u)
        self.assertEqual(self.u.move_path, path)
        self.assertFalse(cmd_pivot(self.u, 90))
        self.assertEqual(self.u.pivot_to, -1)
        self.e.suppression = 90
        cmd_sprint(self.w, self.u)
        self.assertEqual(self.u.sprint_until, 0)       # 未写冲刺计时
        self.assertEqual(self.e.suppression, 90)       # 未吃冲刺减半
        # 世界级收件箱路径（StopCmd/MoveCmd 分派）同拒
        queue_command(self.w, StopCmd(unit=self.u))
        queue_command(self.w, MoveCmd(unit=self.u, path=[(9, 9)]))
        consume_commands(self.w, CONFIG)
        self.assertEqual(self.u.move_path, path)

    def test_queued_command_not_consumed_while_routed(self):
        self._rout()
        self.u.move_path = []                          # 航点耗尽（已抵锚点）的溃逃中段
        self.u.command_queue = [MoveCmd(unit=self.u, path=[(9, 9)])]
        self.w.command_queue = []
        world_tick(self.w, CONFIG)                     # 全链验证：失控期不消费单位级队列
        self.assertIs(self.u.morale, MoraleState.ROUTED)
        self.assertEqual(self.u.move_path, [])         # 队列头未安装（失控不消费）
        self.assertEqual(len(self.u.command_queue), 1)

    def test_rally_in_place_after_timer(self):
        self._rout()                                   # routed_until = 0 + 300
        # 推进至重整前一拍：仍 ROUTED
        while self.w.tick < 299:
            world_tick(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.ROUTED)
        world_tick(self.w, CONFIG)                     # tick=300：重整拍
        self.assertIs(self.u.morale, MoraleState.SUPPRESSED)   # B4:182 默认（待定②留痕）
        self.assertEqual(self.u.routed_until, -1)
        self.assertEqual(self.u.move_path, [])                 # 原地重整：清溃逃航点
        y_at_rally = self.u.pos[1]
        world_tick(self.w, CONFIG)                     # 压制已衰减尽 → 次拍降档 STABLE
        self.assertIs(self.u.morale, MoraleState.STABLE)
        self.assertEqual(self.u.pos[1], y_at_rally)            # 重整后原地不动
        # 恢复受令
        self.assertTrue(issue_move(self.w, CONFIG,
                                   MoveCmd(unit=self.u, path=[(500000, 390000)])))
        self.assertEqual(self.u.move_path, [(500000, 390000)])

    def test_rerout_if_still_under_crushing_fire(self):
        self._rout()
        while self.w.tick < 300:
            world_tick(self.w, CONFIG)
        self.e.suppression = 100                       # 重整拍仍在碾压火力下（≥rout_th）
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.ROUTED)       # 再溃逃
        self.assertEqual(self.u.routed_until, self.w.tick + 300)
        self.assertEqual(self.u.move_path, [(self.w.map_center[0], 0)])  # 重装溃逃航点

    def test_rally_tick_only_resets_once(self):
        # 重整拍回 SUPPRESSED 为单拍过渡：压制若在 [40,70) 则次拍稳定 SUPPRESSED
        self._rout()
        while self.w.tick < 299:
            world_tick(self.w, CONFIG)
        self.e.suppression = 55                        # 衰减未尽的重整（模拟持续受压）
        system_morale(self.w, CONFIG)                  # 仍 ROUTED（tick<300）
        world_tick(self.w, CONFIG)                     # tick=300：重整 → SUPPRESSED
        self.assertIs(self.u.morale, MoraleState.SUPPRESSED)
        self.e.suppression = 55                        # 维持（模拟继续受击注入）
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.SUPPRESSED)
        self.e.suppression = 75
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.PINNED)       # 正常阈值迁移恢复


class TestPB49FullChain(unittest.TestCase):
    """PB-49 全链激活：pinned() 判据缝读 morale 真槽——钉住=可动减速（非旧文「无法
    移动」；GDD-00 D014 已批注废止）+ 冲刺破压制阈值降档。"""

    def setUp(self):
        self.w = make_world(13)
        self.u = mk_unit(self.w, foot_tpl())
        self.e = self.u.elements[0]

    def test_pinned_slows_to_half_via_real_slot(self):
        # 不 monkeypatch：system_morale 判态 → morale==PINNED → move_speed 减半
        self.assertEqual(move_speed_cm_tick(CONFIG, self.u, 0), 56)   # 70×8000‰
        self.e.suppression = 75
        system_morale(self.w, CONFIG)
        self.assertTrue(pinned(self.u))
        self.assertEqual(move_speed_cm_tick(CONFIG, self.u, 0), 28)   # 56×5000//10000

    def test_sprint_breaks_pin_threshold(self):
        # 冲刺破压制（MV-B-04 改B）接入士气链：80 →×0.5→ 40 →判态 SUPPRESSED（≥40 边界）
        self.e.suppression = 80
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.PINNED)
        cmd_sprint(self.w, self.u)
        self.assertEqual(self.e.suppression, 40)
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.SUPPRESSED)
        self.assertFalse(pinned(self.u))
        # 速度还原（冲刺窗内升档 70→100×8000‰=80；窗过后回落 56——两拍都非钉住减速）
        self.assertEqual(move_speed_cm_tick(CONFIG, self.u, 0), 80)
        self.assertEqual(move_speed_cm_tick(
            CONFIG, self.u, CONFIG.sprint_duration_ticks + 1), 56)

    def test_routed_not_pinned_no_slowdown(self):
        # ROUTED 不走 pinned 缝：全速溃逃（减速缝仅 PINNED——语义分立锚）
        self.e.suppression = 100
        system_morale(self.w, CONFIG)
        self.assertFalse(pinned(self.u))
        self.assertEqual(move_speed_cm_tick(CONFIG, self.u, 0), 56)

    def test_stable_suppressed_no_slowdown(self):
        self.e.suppression = 50
        system_morale(self.w, CONFIG)
        self.assertIs(self.u.morale, MoraleState.SUPPRESSED)
        self.assertFalse(pinned(self.u))
        self.assertEqual(move_speed_cm_tick(CONFIG, self.u, 0), 56)


if __name__ == "__main__":
    unittest.main()
