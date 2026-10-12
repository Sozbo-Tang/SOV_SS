"""数据定标 v1 真卡端到端锚（2026-10-07 数据定标块；数值总账 v1 §二定标行）。

四簇：
① vs_fort 攻坚值（P-122）：真卡拆楼资格+伤害链端到端——SU_T3485（D-5T 5000‰＝
   10×5=50/发）/SU_ZIS3 直射（4000‰＝8×4=32/发，needs_deployed 展开@Path）/GER_PAK40
   （3000‰＝10×3=30/发）对 Building 玩家令 AttackCmd 全链（cmd_attack ① 建筑资格门
   →begin_aim→fire_direct 建筑支 w.damage×vs_fort〔HE 档选择 tick.py fire_direct 建筑支+×vs_fort 乘算 combat.py resolve_hit/resolve_blast 建筑支（原引 :2505-2507 系对空支错位，2026-10-07 收口评审#6 勘正——
   建筑走基础 damage 非 alt_profile〕→resolve_hit ×vs_fort→hit_building→塌楼除名）；
   步兵武器（莫辛纳甘缺省 1000）REJECT=无攻坚资格；多武器滤除（T-34 车载机枪与主炮
   同元素、① 门自然滤除保持 READY）。
② turn_rate_deg（P-123）：真卡 rotate_step 逐卡读值（AMB-5 换算 MAX(1,deg//10)）——
   牵引炮 50→5°/tick（180°=36 拍=3.6s＝ask 可用量级窗下限）/坦克 100→10°/tick
   （180°=18 拍）；SU_T3485 arc=360 现为死值（射界门对 360° 恒假——为窄弧 profile
   留位），其值经模板读数仍可达（rotate_step 直调验证）。
③ self_smoke_charges（P-121 更新）：真卡自卫烟幕链——SU_TRUCK/SU_T34 配 2
   （cmd_smoke 发数门→冷却门→N32 延迟落烟 SmokeZone 复用 smoke_radius_cm/
   smoke_ttl_ticks），无能力卡（SU_RIFLE 缺省 0）拒令。
④ 压制衰减裁处：cfg.sup_decay_per_tick 表 pin（GDD-05 B2:127/B4:177 写 5/s vs
   现码 10/s 两档——2026-10-07 裁处留痕，详见 tables.py:155-159 注释与数值总账 v1 §一）。

数据源=仓库 data/gen（CSV 经 tools/build_cards.py 重建）；锚点全部手推写死，不自证；
零掷骰（本文件不触 PCG32 通道——cmd_attack 门序/begin_aim/rotate_step/cmd_smoke 纯整数，
发射段 HIT/SCATTER 掷骰属 fire_direct 既有通道纪律、真卡 acc 缺省 10000 必中）。"""
import unittest
from pathlib import Path

from sovs.sim import card_loader as cl
from sovs.sim.geom import angle_diff
from sovs.sim.movement import rotate_step
from sovs.sim.tables import CONFIG
from sovs.sim.tick import (add_unit, cmd_attack, cmd_smoke, make_unit,
                           make_world, world_tick)
from sovs.sim.types import Building, DeployState, WState

REPO_ROOT = Path(__file__).resolve().parents[1]
GEN_LIBRARY = REPO_ROOT / "data" / "gen" / "cards_ground.v1.json"

#: v1 定标（2026-10-07 数据定标块，P-122/P-123/P-121——数值总账 v1 §二）＋
#: GP-01 M1 新 57 卡类档插值扩展（2026-10-12；P-303/P-304/P-308/P-309 登记：
#: 炮塔车/坦克 turn=100、牵引炮=50、卡车/摩托留 1=死槽；攻坚值仅 GDD 卡面字面三类
#: 承载——75mm 步兵炮拆建筑/工兵爆破/喷火器对建筑毁伤；德卡车与 T-34 底盘烟幕镜像 P-121）
VS_FORT_V1 = {"D-5T 85mm坦克炮": 5000, "ZiS-3 76mm加农炮（直射）": 4000,
              "ZiS-3 76mm加农炮（曲射）": 4000, "PaK 40 75mm反坦克炮": 3000,
              "le.IG 18 75mm步兵炮（直射）": 3000,
              "炸药包": 3000, "爆破包": 3000,
              "ATO-41喷火器": 3000, "喷火器": 3000}
TURN_RATE_V1 = {
    "SU_T3485": 100, "SU_ZIS3": 50, "GER_PAK40": 50,
    # 坦克/炮塔车 100（履带档——P-123 外推 P-308）
    "SU_T3476": 100, "SU_IS2": 100, "SU_SU76": 100, "SU_SU85": 100,
    "SU_ISU152": 100, "SU_OT34": 100, "SU_BA64": 100,
    "GER_PUMA": 100, "GER_PZIV": 100, "GER_PANTHER": 100, "GER_TIGER": 100,
    "GER_STUG": 100, "GER_JGDPZ4": 100, "GER_HETZER": 100,
    "GER_NASHORN": 100, "GER_BERGE": 100,
    # 牵引炮/高炮 50（牵引炮档——P-123 外推 P-308）
    "SU_ZIS2": 50, "SU_M30": 50, "SU_ML20": 50,
    "SU_DSHK": 50, "SU_61K": 50, "SU_52K": 50,
    "GER_IG18": 50, "GER_PAK38": 50, "GER_FH18": 50, "GER_SFH18": 50,
    "GER_NEBEL": 50, "GER_FLAK38": 50, "GER_FLAK43": 50, "GER_FLAK36": 50,
}
SELF_SMOKE_V1 = {"SU_TRUCK": 2, "SU_T3485": 2,
                 "GER_TRUCK": 2,      # 德卡车镜像（P-309）
                 "SU_T3476": 2, "SU_OT34": 2}  # T-34 底盘 BDSh 史实锚随 P-121 扩展


def _lib():
    return cl.load_library(GEN_LIBRARY)


class TestVsFortCalibration(unittest.TestCase):
    """① vs_fort 攻坚值（ask 字面 85/76/75mm≈3000-5000‰ 口径递进推算占位）。"""

    @classmethod
    def setUpClass(cls):
        cls.lib = _lib()

    def test_data_pin_exactly_four_siege_weapons(self):
        # 攻坚配值恰＝VS_FORT_V1 清单（首批 4 攻坚＋GP-01 M1 新增 5 类——75mm 步兵炮
        # 拆建筑/工兵爆破×2/喷火×2，均 GDD-01 卡面字面承载）；其余武器（含铁拳/全部
        # 步枪机枪/新卡坦克炮——P-312 未配 HE 档同批）缺省 1000=无攻坚资格
        filled = {}
        for key in self.lib:
            for et in self.lib[key].unit_template.element_templates:
                for w in et.weapons:
                    if w.vs_fort_mult_permille != 1000:
                        filled[w.name] = w.vs_fort_mult_permille
        self.assertEqual(filled, VS_FORT_V1)

    def _tank_world(self, hp):
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_T3485"].unit_template,
                                  0, 0, (100000, 100000)))
        b = Building(id=1, pos=(103000, 100000), hp=hp)      # dist 3000 ≤ 100000
        w.buildings.append(b)
        return w, u.elements[0], b

    def test_t3485_d5t_demolition_full_chain(self):
        # D-5T 5000‰：aim 30/reload 80/速 7900>程 3000 同拍到达——手推节拍
        # t0 受令 AIMING(30)→t30 发射 hp 100−50=50→t110 READY→复令→t140 发射
        # hp 0 塌楼除名；车载 MG vs_fort=1000 被 ① 滤除全程 READY
        w, e, b = self._tank_world(hp=100)
        ws, mg = e.weapon_states[0], e.weapon_states[1]
        self.assertEqual(ws.template.name, "D-5T 85mm坦克炮")
        cmd_attack(w, e, b, CONFIG)
        self.assertIs(ws.state, WState.AIMING)
        self.assertEqual(ws.timer, 30)                       # aim_time_ticks=30
        for _ in range(30):
            world_tick(w, CONFIG)
        self.assertIs(ws.state, WState.RELOADING)            # t30 已发射
        self.assertEqual(b.hp, 50)                           # 10×5000‰=50/发
        self.assertIs(mg.state, WState.READY)                # ① 滤除不冒充
        for _ in range(80):
            world_tick(w, CONFIG)                            # t110 RELOADING→READY
        self.assertIs(ws.state, WState.READY)
        cmd_attack(w, e, b, CONFIG)
        for _ in range(30):
            world_tick(w, CONFIG)
        self.assertLessEqual(b.hp, 0)                        # 50−50=0 塌楼
        self.assertNotIn(b, w.buildings)                     # 塌楼按身份除名

    def test_zis3_direct_demolition_needs_deployed_path(self):
        # ZiS-3 4000‰（needs_deployed=true → ③ 展开门须 DEPLOYED）：直/曲两档
        # 同炮同值均过 ① 建筑资格门——aim 20、reload 直 60/曲 24。手推（hp128）：
        # t0 双档受令 AIMING(20)→t20 齐射 128−32×2=64（速 6800>程 3000 同拍到达；
        # 曲射 min_range 25000 无手动 min 门照放行）→t44 曲 READY 复令→t64 曲射
        # hp 32→t80 直 READY 复令→t100 直射 hp 0 塌楼除名
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_ZIS3"].unit_template,
                                  0, 0, (100000, 100000)))
        u.deploy_state = DeployState.DEPLOYED                # R-05 展开门
        b = Building(id=1, pos=(103000, 100000), hp=128)
        w.buildings.append(b)
        e = u.elements[0]
        dws = next(x for x in e.weapon_states
                   if x.template.name == "ZiS-3 76mm加农炮（直射）")
        iws = next(x for x in e.weapon_states
                   if x.template.name == "ZiS-3 76mm加农炮（曲射）")
        cmd_attack(w, e, b, CONFIG)
        self.assertIs(dws.state, WState.AIMING)              # 直射 4000‰ 过 ①
        self.assertEqual(dws.timer, 20)
        self.assertIs(iws.state, WState.AIMING)              # 曲射同炮同值过 ①
        for _ in range(20):
            world_tick(w, CONFIG)                            # t20 齐射
        self.assertEqual(b.hp, 64)                           # 8×4000‰×2 档
        self.assertIs(dws.state, WState.RELOADING)
        self.assertEqual((dws.timer, iws.timer), (60, 24))   # reload 直 60/曲 24
        for _ in range(24):
            world_tick(w, CONFIG)                            # t44 曲 READY（直 36）
        cmd_attack(w, e, b, CONFIG)                          # ⑦ 滤 RELOADING 直射
        self.assertIs(iws.state, WState.AIMING)
        self.assertIs(dws.state, WState.RELOADING)
        for _ in range(20):
            world_tick(w, CONFIG)                            # t64 曲射
        self.assertEqual(b.hp, 32)
        for _ in range(16):
            world_tick(w, CONFIG)                            # t80 直 READY
        cmd_attack(w, e, b, CONFIG)
        for _ in range(20):
            world_tick(w, CONFIG)                            # t100 直射
        self.assertLessEqual(b.hp, 0)                        # 32−32=0 塌楼
        self.assertNotIn(b, w.buildings)

    def test_pak40_demolition_three_hits(self):
        # PaK40 3000‰：aim 20/reload 65——hp90 三发（30/发）t20/t105/t190 塌
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["GER_PAK40"].unit_template,
                                  1, 1, (100000, 100000)))
        u.deploy_state = DeployState.DEPLOYED
        b = Building(id=1, pos=(103000, 100000), hp=90)
        w.buildings.append(b)
        e = u.elements[0]
        for _ in range(3):
            cmd_attack(w, e, b, CONFIG)
            self.assertIs(e.weapon_states[0].state, WState.AIMING)
            for _ in range(20):                              # aim 20 → 发射
                world_tick(w, CONFIG)
            self.assertIs(e.weapon_states[0].state, WState.RELOADING)
            for _ in range(65):                              # reload 65 → READY
                world_tick(w, CONFIG)
        self.assertLessEqual(b.hp, 0)                        # 90−30×3=0
        self.assertNotIn(b, w.buildings)

    def test_infantry_weapons_no_siege_qualification(self):
        # 步兵武器维持 1000（ask 字面「无攻坚资格」）：步枪排全武器对楼恒 REJECT
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_RIFLE"].unit_template,
                                  0, 0, (100000, 100000)))
        b = Building(id=1, pos=(103000, 100000), hp=40)
        w.buildings.append(b)
        e = u.elements[0]
        cmd_attack(w, e, b, CONFIG)
        for ws in e.weapon_states:
            self.assertIs(ws.state, WState.READY)            # ① 门滤除


class TestTurnRateCalibration(unittest.TestCase):
    """② turn_rate_deg v1 定标（ask 字面履带 5-10°/t 可用量级；AMB-5 换算 //10）。"""

    @classmethod
    def setUpClass(cls):
        cls.lib = _lib()

    def test_data_pin_three_cards_rest_default_one(self):
        for key, rec in self.lib.items():
            expect = TURN_RATE_V1.get(key, 1)                # 清单外卡缺省 1（含 P-308 死槽）
            self.assertEqual(rec.unit_template.turn_rate_deg, expect, key)

    def test_pak40_rotate_step_five_deg_per_tick(self):
        # 50 deg/s → 5°/tick；180° 转向 36 拍（3.6s＝ask 可用窗下限；人力转炮慢于履带）
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["GER_PAK40"].unit_template,
                                  1, 1, (100000, 100000)))
        e = u.elements[0]
        e.facing = 0
        rotate_step(e, 180)
        self.assertEqual(e.facing, 5)                        # 首步 5°
        self.assertTrue(e.rotating)                          # |175|>30 弧外
        for _ in range(35):
            rotate_step(e, 180)                              # 余 175°/5=35 步
        self.assertEqual(e.facing, 180)
        self.assertFalse(e.rotating)

    def test_zis3_same_towed_gun_tier(self):
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_ZIS3"].unit_template,
                                  0, 0, (100000, 100000)))
        e = u.elements[0]
        e.facing = 90
        rotate_step(e, 180)
        self.assertEqual(e.facing, 95)                       # 50//10=5 同牵引炮档

    def test_t3485_ten_deg_dead_slot_note(self):
        # 100 deg/s → 10°/tick（履带档上限、180°=18 拍）；现役 arc=360 → 射界门
        # 恒假=自动链不达 rotate_step（死值占位、窄弧 profile 留位），模板读数仍可达
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_T3485"].unit_template,
                                  0, 0, (100000, 100000)))
        e = u.elements[0]
        self.assertEqual(e.template.fire_arc_deg, 360)       # 死值条件在案
        e.facing = 0
        rotate_step(e, 90)
        self.assertEqual(e.facing, 10)                       # 100//10=10°/tick


class TestSelfSmokeRealCards(unittest.TestCase):
    """③ 自卫烟幕真卡配属链（P-121 更新：SU_TRUCK/SU_T34=2；GP-01 M1 扩展德卡车与
    T-34 底盘三卡镜像=2、余卡 0——P-309）。"""

    @classmethod
    def setUpClass(cls):
        cls.lib = _lib()

    def test_data_pin_two_cards_rest_zero(self):
        for key in self.lib:
            expect = SELF_SMOKE_V1.get(key, 0)
            for et in self.lib[key].unit_template.element_templates:
                self.assertEqual(et.self_smoke_charges, expect, key)

    def test_truck_smoke_cmd_full_chain(self):
        # 真卡链：受令耗发 2→1、N32 延迟 20 拍落烟（复用 3000/600 两常数）、
        # 冷却 300 拍窗内拒令、边界拍受令、耗尽发数门拒
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_TRUCK"].unit_template,
                                  0, 0, (100000, 100000)))
        e = u.elements[0]
        self.assertEqual(e.self_smoke_left, 2)               # ← 模板 self_smoke=2
        self.assertTrue(cmd_smoke(w, e, (999999, 999999), CONFIG))  # point 不消费
        self.assertEqual((e.self_smoke_left, e.self_smoke_pop_tick,
                          e.self_smoke_ready_tick), (1, 20, 300))
        for _ in range(19):
            world_tick(w, CONFIG)
        self.assertEqual(w.smoke_zones, [])                  # 延迟窗内无烟
        world_tick(w, CONFIG)                                # t20 到拍落烟
        self.assertEqual(len(w.smoke_zones), 1)
        z = w.smoke_zones[0]
        self.assertEqual(z.center, (100000, 100000))         # 圆心=元素位
        self.assertEqual((z.radius_cm, z.ttl_ticks), (3000, 600))
        self.assertFalse(cmd_smoke(w, e, (0, 0), CONFIG))    # t20<300 冷却拒
        for _ in range(279):
            world_tick(w, CONFIG)                            # t299
        self.assertFalse(cmd_smoke(w, e, (0, 0), CONFIG))    # 299<300
        world_tick(w, CONFIG)                                # t300 边界拍
        self.assertTrue(cmd_smoke(w, e, (0, 0), CONFIG))
        self.assertEqual(e.self_smoke_left, 0)
        for _ in range(300):
            world_tick(w, CONFIG)                            # t600 过冷却
        self.assertFalse(cmd_smoke(w, e, (0, 0), CONFIG))    # 发数门拒（0 发）
        self.assertEqual(e.self_smoke_left, 0)               # 拒令不耗发

    def test_t34_smoke_charges_live(self):
        # 勘察默认配属（史实 BDSh 锚；ask 字面仅点名 SU_TRUCK——可撤销留痕 P-121）
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_T3485"].unit_template,
                                  0, 0, (100000, 100000)))
        e = u.elements[0]
        self.assertEqual(e.self_smoke_left, 2)
        self.assertTrue(cmd_smoke(w, e, (0, 0), CONFIG))

    def test_no_capability_card_rejects(self):
        w = make_world(7)
        u = add_unit(w, make_unit(w, self.lib["SU_RIFLE"].unit_template,
                                  0, 0, (100000, 100000)))
        e = u.elements[0]
        self.assertEqual(e.self_smoke_left, 0)               # 缺省 0=无能力
        self.assertFalse(cmd_smoke(w, e, (0, 0), CONFIG))
        self.assertEqual(w.smoke_zones, [])


class TestSupDecayAdjudication(unittest.TestCase):
    """④ 压制衰减裁处表 pin（GDD-05 B2:127/B4:177 写 5/s vs 现码 10/s——2026-10-07
    数据定标块裁处；登记表士气块留待项④ 就此收口，数值总账 v1 §一已补行）。"""

    def test_table_pin_ten_per_second(self):
        # v1 裁处=维持现码 10/s 转正：5/s=0.5/tick 非整须隔拍衰减复杂化；士气整局
        # 验收手推链全建立在 decay=1/tick；同源 B4 0..150 标尺已随 PB-54 不采——
        # 5/s 随同源规格一并不采自洽（「断箭数值不直接迁移」P-120 先例）
        self.assertEqual(CONFIG.sup_decay_per_tick, 1)       # 1/tick@10Hz=10/s


if __name__ == "__main__":
    unittest.main()
