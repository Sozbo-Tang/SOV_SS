"""PB-53 载具自卫烟幕（2026-10-04 拍板纳入——断箭 N32/映射 §五.19；复用 §D.7 既有
SmokeCmd 命令类+§F6 :1274 cmd_smoke TODO 锚，不另立新命令类型；与迫击炮烟弹体系
并存——原「烟幕=迫击炮定量烟弹（D044）」口径扩为两者并存）。

覆盖面：tables 烟雾段常数 pin（发数占位/冷却/延迟——N32 仅定性「固有部署延迟」
无秒数，全部无据占位；半径/时长复用炮烟两常数不另立轨）/运行时三槽初始化
（make_unit ← template.self_smoke_charges）/发数门（无能力拒令、递减耗尽拒令）/
冷却门（窗内拒令不耗发、边界拍受令、冷却自受令拍起算）/N32 部署延迟（到拍前
无烟区、到拍落烟且圆心=元素当前位=落点车锚定、SmokeCmd.point 不消费）/SmokeZone
半径时长/与 resolve_blast 炮烟同 ttl 生命周期（当拍满额、次拍起递减、归零拍尾部
过滤）/分派支集成（queue_command→consume_commands 全链）/零掷骰（八通道 PCG32
state 不动）/在途守卫（delay>cooldown 退化配置不丢发）/延迟窗内载具被毁烟幕取消
（发数不退）/loader 元素字段映射（含缺键回退）。锚点全部手推写死，不自证。"""
import unittest

from sovs.sim import card_loader as cl
from sovs.sim.tick import (SmokeCmd, add_unit, cmd_smoke, consume_commands,
                           make_unit, make_world, queue_command, world_tick)
from sovs.sim.tables import CONFIG, BalanceConfig
from sovs.sim.types import (ElementTemplate, ElementType, MovementClass,
                            UnitTemplate, UnitType)


def _tpl(charges=2):
    """合成载具模板（测试用，不对应真实卡；template_id 597 段——test_pivot 59x 后继）。"""
    return UnitTemplate(
        template_id=597, name="smoke tank", category=2, cost=50,
        element_templates=(ElementTemplate(
            element_type=ElementType.VEHICLE, unit_type=UnitType.MECH,
            hp_max=10, self_smoke_charges=charges),),
        optics_ground_cm=20000, stealth_base=5, speed_tier=2,
        movement_class=MovementClass.TRACK)


def _world(charges=2, cooldown=5, delay=0):
    """冷却/延迟注入 cfg 的双元素世界（自卫烟幕行为仅由 cfg+模板位驱动）。"""
    cfg = BalanceConfig(self_smoke_cooldown_ticks=cooldown,
                        self_smoke_delay_ticks=delay)
    w = make_world(21)
    u = add_unit(w, make_unit(w, _tpl(charges), 0, 0, (100000, 100000)))
    return w, cfg, u


def _states(w):
    return tuple(r.state for r in w.rng._rngs)


class TestSelfSmokeCfg(unittest.TestCase):
    """tables.py 烟雾段 pin——N32 唯一证据=官方补丁定性「固有部署延迟」无秒数
    （核证 v1 未确证#13），三常数全部无据占位待数值章节定标；本锚只锁数值现状。"""

    def test_table_pin(self):
        self.assertEqual(CONFIG.self_smoke_default_charges, 2)   # 零消费者定标锚
        self.assertEqual(CONFIG.self_smoke_cooldown_ticks, 300)  # 30s
        self.assertEqual(CONFIG.self_smoke_delay_ticks, 20)      # 2s（N32 部署延迟）

    def test_radius_ttl_reuse_mortar_constants(self):
        # 半径/时长复用炮烟两常数（拍板行「复用 SmokeZone」——两体系同一烟区口径）
        self.assertEqual(CONFIG.smoke_radius_cm, 3000)
        self.assertEqual(CONFIG.smoke_ttl_ticks, 600)


class TestRuntimeSlots(unittest.TestCase):
    def test_make_unit_initializes_from_template(self):
        w = make_world(1)
        u = add_unit(w, make_unit(w, _tpl(charges=3), 0, 0, (0, 0)))
        e = u.elements[0]
        self.assertEqual(e.self_smoke_left, 3)      # ← template.self_smoke_charges
        self.assertEqual(e.self_smoke_ready_tick, 0)   # 0=开局即可
        self.assertEqual(e.self_smoke_pop_tick, -1)    # -1=无在途

    def test_default_template_zero_charges_rejects(self):
        # 模板缺省 0=无能力（现役全部卡实况——P-121）：拒令且永无烟区
        w, cfg, u = _world(charges=0)
        e = u.elements[0]
        self.assertFalse(cmd_smoke(w, e, (0, 0), cfg))
        self.assertEqual(e.self_smoke_left, 0)
        for _ in range(30):
            world_tick(w, cfg)
        self.assertEqual(w.smoke_zones, [])


class TestChargesGate(unittest.TestCase):
    def test_decrement_and_exhaustion(self):
        # 发数递减（受令即耗）；冷却窗内拒令；耗尽后过冷却仍拒令（发数门）
        w, cfg, u = _world(charges=2, cooldown=5, delay=0)
        e = u.elements[0]
        self.assertTrue(cmd_smoke(w, e, (9, 9), cfg))            # tick0 受令
        self.assertEqual((e.self_smoke_left, e.self_smoke_pop_tick,
                          e.self_smoke_ready_tick), (1, 0, 5))
        world_tick(w, cfg)                                        # tick1：到拍落烟
        self.assertEqual(len(w.smoke_zones), 1)
        self.assertEqual(e.self_smoke_pop_tick, -1)
        self.assertFalse(cmd_smoke(w, e, (9, 9), cfg))           # tick1<5 冷却门拒
        for _ in range(3):
            world_tick(w, cfg)                                    # tick2..4
        self.assertFalse(cmd_smoke(w, e, (9, 9), cfg))           # tick4<5 冷却门拒
        world_tick(w, cfg)                                        # tick5
        self.assertTrue(cmd_smoke(w, e, (9, 9), cfg))            # 5>=5 边界拍受令
        self.assertEqual(e.self_smoke_left, 0)
        world_tick(w, cfg)                                        # tick6：第二发落烟
        self.assertEqual(len(w.smoke_zones), 2)
        self.assertEqual(e.self_smoke_ready_tick, 10)
        for _ in range(5):
            world_tick(w, cfg)                                    # tick7..11 过冷却
        self.assertFalse(cmd_smoke(w, e, (9, 9), cfg))           # 11>=10 冷却过→发数门拒
        self.assertEqual(e.self_smoke_left, 0)                    # 拒令不耗发
        self.assertEqual(len(w.smoke_zones), 2)


class TestCooldownGate(unittest.TestCase):
    def test_window_reject_keeps_charge_boundary_accepts(self):
        # 冷却自受令拍起算（ready=受令拍+cooldown）；窗内拒令不耗发；边界拍（==）受令
        w, cfg, u = _world(charges=2, cooldown=10, delay=0)
        e = u.elements[0]
        self.assertTrue(cmd_smoke(w, e, (0, 0), cfg))            # tick0 → ready=10
        world_tick(w, cfg)                                        # tick1 落烟（pop=-1）
        for _ in range(8):
            world_tick(w, cfg)                                    # tick2..9
        self.assertEqual(w.tick, 9)
        self.assertFalse(cmd_smoke(w, e, (0, 0), cfg))           # 9<10 冷却门拒
        self.assertEqual(e.self_smoke_left, 1)                    # 拒令不耗发
        world_tick(w, cfg)                                        # tick10
        self.assertTrue(cmd_smoke(w, e, (0, 0), cfg))            # 10>=10 边界受令


class TestDeployDelay(unittest.TestCase):
    def test_delay_window_then_vehicle_anchored_zone(self):
        # N32「固有部署延迟」：到拍前无烟区；到拍以**元素当前位置**为心落烟（勘察两案
        # 取「以车为心圆」简化案）；SmokeCmd.point 不消费（远处点不偏移圆心）
        w, cfg, u = _world(charges=1, cooldown=0, delay=20)
        e = u.elements[0]
        self.assertTrue(cmd_smoke(w, e, (999999, 999999), cfg))  # point 远处
        self.assertEqual(e.self_smoke_pop_tick, 20)
        for _ in range(19):
            world_tick(w, cfg)                                    # tick1..19 延迟窗
        self.assertEqual(w.tick, 19)
        self.assertEqual(w.smoke_zones, [])
        e.pos = (123456, 654321)                                  # 延迟窗内载具机动
        u.pos = e.pos
        world_tick(w, cfg)                                        # tick20 到拍落烟
        self.assertEqual(len(w.smoke_zones), 1)
        z = w.smoke_zones[0]
        self.assertEqual(z.center, (123456, 654321))              # 圆心=落烟拍元素位置
        self.assertEqual((z.radius_cm, z.ttl_ticks), (3000, 600))  # 复用炮烟两常数
        self.assertEqual(e.self_smoke_pop_tick, -1)               # 在途复位

    def test_zone_ttl_lifecycle_matches_mortar_zones(self):
        # 与 resolve_blast 炮烟同生命周期：落烟拍满额 ttl=600（本拍不递减——system_timers
        # 落烟环置于 ttl 递减环后）、次拍起递减、归零拍尾部过滤
        w, cfg, u = _world(charges=1, cooldown=0, delay=0)
        e = u.elements[0]
        self.assertTrue(cmd_smoke(w, e, (0, 0), cfg))            # tick0：pop=0
        world_tick(w, cfg)                                        # tick1 落烟
        self.assertEqual(w.smoke_zones[0].ttl_ticks, 600)
        for _ in range(598):
            world_tick(w, cfg)                                    # tick2..599 → ttl 2
        self.assertEqual(w.smoke_zones[0].ttl_ticks, 2)
        world_tick(w, cfg)                                        # tick600 → ttl 1
        self.assertEqual(w.smoke_zones[0].ttl_ticks, 1)
        world_tick(w, cfg)                                        # tick601 → ttl 0 过滤
        self.assertEqual(w.smoke_zones, [])


class TestDispatchIntegration(unittest.TestCase):
    def test_queue_command_full_chain_and_zero_rng(self):
        # 分派支集成：queue_command→consume_commands→system_timers 全链；
        # 零掷骰——八通道 PCG32 state 全程不动
        w, cfg, u = _world(charges=1, cooldown=0, delay=3)
        e = u.elements[0]
        before = _states(w)
        queue_command(w, SmokeCmd(element=e, point=(777777, 777777)))
        self.assertEqual(len(w.command_queue), 1)
        world_tick(w, cfg)                                        # tick1：受令
        self.assertEqual(e.self_smoke_left, 0)
        self.assertEqual(w.smoke_zones, [])                       # 延迟未到
        world_tick(w, cfg)
        world_tick(w, cfg)                                        # tick2,3
        self.assertEqual(w.smoke_zones, [])
        world_tick(w, cfg)                                        # tick4：pop=1+3=4 到拍
        self.assertEqual(len(w.smoke_zones), 1)
        self.assertEqual(w.smoke_zones[0].center, e.pos)          # 落点车锚定
        self.assertEqual(_states(w), before)

    def test_consume_commands_direct_drain(self):
        # consume_commands 直调亦落地（命令层处理体口径——处理体真调用非丢弃）
        w, cfg, u = _world(charges=1, cooldown=0, delay=0)
        e = u.elements[0]
        queue_command(w, SmokeCmd(element=e, point=(0, 0)))
        consume_commands(w, cfg)
        self.assertEqual(w.command_queue, [])
        self.assertEqual((e.self_smoke_left, e.self_smoke_pop_tick), (0, 0))


class TestEdgeSemantics(unittest.TestCase):
    def test_in_flight_guard_no_double_pending(self):
        # 退化配置 delay>cooldown：上一发未落烟前第二发拒令（防受令覆盖 pop_tick 丢发）；
        # 在途清后（落烟拍）再受令
        w, cfg, u = _world(charges=2, cooldown=2, delay=50)
        e = u.elements[0]
        self.assertTrue(cmd_smoke(w, e, (0, 0), cfg))            # tick0：pop=50 ready=2
        for _ in range(5):
            world_tick(w, cfg)                                    # tick1..5 冷却已过
        self.assertFalse(cmd_smoke(w, e, (0, 0), cfg))           # pop=50 在途→拒
        self.assertEqual(e.self_smoke_left, 1)                    # 拒令不耗发
        for _ in range(45):
            world_tick(w, cfg)                                    # tick6..50
        self.assertEqual(len(w.smoke_zones), 1)                   # tick50 落烟
        self.assertTrue(cmd_smoke(w, e, (0, 0), cfg))            # 在途已清→受令
        self.assertEqual(e.self_smoke_left, 0)

    def test_vehicle_destroyed_during_delay_cancels_pop(self):
        # 载具延迟窗内被毁→烟幕取消（发数已耗不退——N32「不能导弹临头才按」代价）
        w, cfg, u = _world(charges=1, cooldown=0, delay=10)
        e = u.elements[0]
        self.assertTrue(cmd_smoke(w, e, (0, 0), cfg))
        u.alive = False                       # 手置终态（destroy_element 全灭同款）
        for _ in range(12):
            world_tick(w, cfg)                # 尾部尸体清扫出 units
        self.assertEqual(w.smoke_zones, [])
        self.assertEqual(e.self_smoke_left, 0)  # 发数不退


class TestLoaderField(unittest.TestCase):
    def test_build_element_reads_self_smoke_charges(self):
        et = cl._build_element(
            {"element_type": 0, "unit_type": 1, "hp_max": 10,
             "self_smoke_charges": 3}, "x")
        self.assertEqual(et.self_smoke_charges, 3)
        et0 = cl._build_element(
            {"element_type": 0, "unit_type": 1, "hp_max": 10}, "x")
        self.assertEqual(et0.self_smoke_charges, 0)   # 缺键=默认 0（DATA-01 §2.3-1）


if __name__ == "__main__":
    unittest.main()
