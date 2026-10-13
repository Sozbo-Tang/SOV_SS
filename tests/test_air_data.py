"""机型数值数据表测试（air_data.py——终检报告规划内增量②）。

四类检查（任务口径）：
① 12 卡字段完备性——§D.1 二十字段无一缺省漏配（CARD_KWARGS 键集==模板字段集，
   构造即完备；另有职能必填矩阵/能力缺位归零矩阵）；
② 苏德镜像卡同型一致——MIRROR_PAIRS 结构性字段逐对相等（数值/阵营特化位排除集成文）；
③ 跨卡合理性——战斗机速度>轰炸机、高度层覆盖 R-23、对空/对地目标域正确、价格与
   GDD 卡面一致、每卡限份（B-24 在空≤2 走真实呼叫门）；
④ 与 air.py 模板构造器签名严格匹配——真实 AircraftTemplate(**kw) 重建逐字段相等
   ＋字段名集==§D.1 权威名单＋真实管线冒烟（cmd_air_call/slot_ok/容量门/装机扣份/
   Il-2M 转对空丢弹）。

数据源引用：GDD-02 v1.9 §6（:292/:312-317/:321-326/:330-335）、GDD-01（:92-99/:168-174）、
GDD-03（:12/:127-142/:209-215）、IMPL v1.4（§D.1 :77-103/§D.3 :136-146/§A :673-705）、
拍板清单（B-21 :48-53/B-24 :91-96）。
"""
import dataclasses
import unittest
from types import SimpleNamespace

from sovs.sim import air_data
from sovs.sim.air import (AirRole, AircraftTemplate, cmd_air_call,
                          cmd_air_engage_air, entry_tier)
from sovs.sim.rng import Channels
from sovs.sim.tables import CONFIG
from sovs.sim.types import AltTier, DamageType, TargetDomain, Trajectory

# §D.1 二十字段权威名单（IMPL v1.4 :79-100，字段名逐字）
D1_FIELDS = (
    "template_id", "name", "role", "cost_body", "hp_max", "armor_aa",
    "speed_cm_tick", "dogfight_power", "maneuver", "alt_ceiling",
    "optics_air_cm", "recon_mark_base_bp", "weapons", "payload_max_bombs",
    "payload_max_supply", "paratroop_seats", "turret_damage",
    "can_engage_air", "has_dive", "payload_price",
    # ── P1 机制块 +3（2026-10-13，GP-01 断箭手册 P1 补建——加力/诱饵/被动对策；
    #    数值/配属手册未给→manual_silent，数据侧 YAML）──
    "can_afterburner", "decoy_charges", "passive_evade_bp",
)

# GDD-02 v1.9 卡面价（:321-326 苏①~⑥ / :330-335 德①~⑥；GDD-01 :94-99/:169-174 同值互证）
GDD_PRICES = {
    "PO2": 20, "PE2": 85, "IL2M": 90, "YAK9": 70, "LI2": 40, "SU_PARATROOP": 60,
    "FW189": 30, "JU88": 95, "JU87D": 75, "FW190A": 80, "JU52": 40, "GER_PARATROOP": 65,
}

# GDD-03 §2.4 对空战力/机动表（:131-140，照抄）
GDD_DOGFIGHT = {
    "PO2": (1, 3), "PE2": (3, 7), "IL2M": (5, 4), "YAK9": (7, 9), "LI2": (2, 5),
    "FW189": (1, 4), "JU88": (3, 5), "JU87D": (4, 5), "FW190A": (9, 8), "JU52": (1, 4),
}

AIRCRAFT_KEYS = [k for k in air_data.AIR_CARD_ORDER
                 if k not in ("SU_PARATROOP", "GER_PARATROOP")]
PARATROOP_KEYS = ["SU_PARATROOP", "GER_PARATROOP"]


def tpl(key):
    return air_data.CARD_OBJECTS[key]


def weapon_names(t):
    return tuple(w.name for w, _n in t.weapons)


def legal_payload(t):
    """各职能合法载荷（§F1 slot_ok 门口径；2026-10-03 拍板：补给一池为重量）——
    真实门冒烟用。"""
    if t.role in (AirRole.BOMBER, AirRole.ATTACK):
        return {"BOMB": t.payload_max_bombs}
    if t.role is AirRole.TRANSPORT:
        return {"SUPPLY": 10}
    return {}  # FIGHTER/RECON 空载荷


def mkworld(phase=1, tick=0):  # 默认 PHASE_COMBAT（2026-10-03 禁火删除后 0=DEPLOY/1=COMBAT/2=SETTLE）
    """§D.4 world 最小 mock（同 tests/test_air_behavior.py:42-55 既有模式）。"""
    w = SimpleNamespace(
        aircraft=[], projectiles=[], units=[], players=[], tick=tick, phase=phase,
        map_center=(500000, 500000), beacon_by_unit={}, cloud_tier=0,
        next_aircraft_id=1, rng=Channels(42),
        spawn_paratroop=lambda *a: setattr(
            w, "paratroop_calls", getattr(w, "paratroop_calls", []) + [a]),
        spawn_airdrop_crate=lambda *a: setattr(
            w, "crate_calls", getattr(w, "crate_calls", []) + [a]),
    )
    w.air_entry_point = lambda team: (500000, -40000 if team == 0 else 1040000)
    w.rtb_exit_point = lambda team: (500000, -40000 if team == 0 else 1040000)
    p0 = SimpleNamespace(index=0, team=0, air_points=2000,
                         air_cooldowns={}, deck_slots=[])
    p1 = SimpleNamespace(index=1, team=1, air_points=2000,
                         air_cooldowns={}, deck_slots=[])
    w.players = [p0, p1]
    return w


# ════════════════ ① 12 卡字段完备性 ════════════════

class TestFieldCompleteness(unittest.TestCase):
    """§D.1 二十字段无一缺省漏配（构造级完备＋职能必填矩阵＋缺位归零矩阵）。"""

    def test_template_has_exactly_twenty_d1_fields(self):
        # §D.1 静态 20（IMPL v1.4 :77/§D.6 :176）——字段数与字段名双检
        # 〔P1 机制块 2026-10-13：+3 能力位（加力/诱饵/被动对策）→23。〕
        names = tuple(f.name for f in dataclasses.fields(AircraftTemplate))
        self.assertEqual(len(names), 23)
        self.assertEqual(names, D1_FIELDS)

    def test_every_aircraft_card_passes_all_twenty_kwargs(self):
        # 构造级完备：每卡 kwargs 键集==§D.1 字段全集——缺一键即无法进入本表
        for k in AIRCRAFT_KEYS:
            self.assertEqual(set(air_data.CARD_KWARGS[k]), set(D1_FIELDS), k)

    def test_twelve_cards_registered_in_gdd_order(self):
        # 12 卡=GDD §6.1①~⑥/§6.2①~⑥ 顺序（v1.9 :321-326/:330-335）
        self.assertEqual(len(air_data.AIR_CARD_ORDER), 12)
        self.assertEqual(air_data.AIR_CARD_ORDER, (
            "PO2", "PE2", "IL2M", "YAK9", "LI2", "SU_PARATROOP",
            "FW189", "JU88", "JU87D", "FW190A", "JU52", "GER_PARATROOP"))
        self.assertEqual(len(air_data.AIRCRAFT_TEMPLATES), 10)
        self.assertEqual(len(air_data.PARATROOP_CARDS), 2)

    def test_template_ids_unique(self):
        ids = [t.template_id for t in air_data.AIRCRAFT_TEMPLATES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_role_mandatory_matrix(self):
        # 职能必填：漏配即对应职能静默失效（§D.3 :144 硬要求①~⑤原话）
        for t in air_data.AIRCRAFT_TEMPLATES:
            r = t.role
            if r is AirRole.RECON:
                self.assertGreater(t.optics_air_cm, 0, t.name)
                self.assertGreater(t.recon_mark_base_bp, 0, t.name)
                self.assertEqual(t.weapons, (), t.name)
            elif r is AirRole.BOMBER:
                self.assertEqual(weapon_names(t), ("BOMB",), t.name)
                self.assertGreater(t.payload_max_bombs, 0, t.name)
                self.assertIn("BOMB", t.payload_price, t.name)
                self.assertGreater(t.turret_damage, 0, t.name)  # §D.1 #17
            elif r is AirRole.ATTACK:
                self.assertIn("BOMB", weapon_names(t), t.name)
                self.assertGreater(t.payload_max_bombs, 0, t.name)
                self.assertIn("BOMB", t.payload_price, t.name)
            elif r is AirRole.FIGHTER:
                self.assertEqual(weapon_names(t), ("STRAFE",), t.name)
                self.assertTrue(t.can_engage_air, t.name)      # 硬要求⑦
            elif r is AirRole.TRANSPORT:
                self.assertEqual(t.weapons, (), t.name)        # 硬要求⑤
                self.assertEqual(t.paratroop_seats, 1, t.name)  # §D.1 #16"TRANSPORT=1"
                self.assertGreater(t.payload_max_supply, 0, t.name)
                self.assertIn("SUPPLY", t.payload_price, t.name)  # 2026-10-03 拍板：载荷一池化
                self.assertGreater(t.turret_damage, 0, t.name)  # §D.1 #17
            else:
                self.fail(f"未知职能 {r!r}")

    def test_capability_absence_zero_matrix(self):
        # 能力缺位归零：未分配能力的槽必须显式 0/空（条件槽语义，types.py 头注）
        for t in air_data.AIRCRAFT_TEMPLATES:
            if t.role is not AirRole.RECON:
                self.assertEqual(t.optics_air_cm, 0, t.name)
                self.assertEqual(t.recon_mark_base_bp, 0, t.name)
            if t.role is not AirRole.TRANSPORT:
                self.assertEqual(t.paratroop_seats, 0, t.name)
                self.assertEqual(t.payload_max_supply, 0, t.name)
            if t.role not in (AirRole.BOMBER, AirRole.TRANSPORT):
                self.assertEqual(t.turret_damage, 0, t.name)  # §D.1 #17 反向
            if "BOMB" not in weapon_names(t):
                self.assertEqual(t.payload_max_bombs, 0, t.name)
                self.assertNotIn("BOMB", t.payload_price, t.name)

    def test_weapon_entries_have_positive_ammo(self):
        # §D.1 #13 (WeaponTemplate, 弹量)：弹量≥1——0 弹武器=挂档即死档
        for t in air_data.AIRCRAFT_TEMPLATES:
            for w, n in t.weapons:
                self.assertGreaterEqual(n, 1, f"{t.name}:{w.name}")
                self.assertGreaterEqual(n, w.salvo, f"{t.name}:{w.name}（弹量≥单次 salvo）")

    def test_bomb_tuple_matches_payload_capacity(self):
        # BOMB 档弹量元组=档案满载数（运行时以 payload 购买数为准——§F1/GAP2-04 成文口径）
        for t in air_data.AIRCRAFT_TEMPLATES:
            for w, n in t.weapons:
                if w.name == "BOMB":
                    self.assertEqual(n, t.payload_max_bombs, t.name)

    def test_d3_hard_requirements(self):
        # §D.3 硬要求①~⑤逐条（v1.4 :144）
        self.assertEqual(set(weapon_names(air_data.IL2M)), {"BOMB", "STRAFE"})   # ①
        for k in ("YAK9", "FW190A"):                                              # ②
            self.assertEqual(weapon_names(tpl(k)), ("STRAFE",))
        for k in ("PE2", "JU88"):                                                 # ③
            self.assertEqual(weapon_names(tpl(k)), ("BOMB",))
        self.assertEqual(weapon_names(air_data.JU87D), ("BOMB",))                 # ④
        self.assertTrue(air_data.JU87D.has_dive)                                  # ④
        for k in ("LI2", "JU52"):                                                 # ⑤
            self.assertEqual(tpl(k).weapons, ())
        # ⑥ crit_mod_permille=0 全空射武器
        for t in air_data.AIRCRAFT_TEMPLATES:
            for w, _n in t.weapons:
                self.assertEqual(w.crit_mod_permille, 0, f"{t.name}:{w.name}")
        # ⑦ FIGHTER.can_engage_air=TRUE
        for k in ("YAK9", "FW190A"):
            self.assertTrue(tpl(k).can_engage_air)

    def test_b21_stuka_cannot_engage_air_but_il2m_can(self):
        # 〔拍板〕B-21：Ju 87D 不置位；§D.1 #18：Il-2M 置位
        self.assertFalse(air_data.JU87D.can_engage_air)
        self.assertTrue(air_data.IL2M.can_engage_air)

    def test_paratroop_card_fields(self):
        # 空降两卡：GDD 卡面字段（价/池/投送限定）齐全——地面侧字段属地面管线增量（P-13）
        for k, name, cost, delivery in (
                ("SU_PARATROOP", "空降近卫步枪排", 60, air_data.LI2),
                ("GER_PARATROOP", "空降猎兵排", 65, air_data.JU52)):
            c = air_data.CARD_OBJECTS[k]
            self.assertEqual((c.card_key, c.name, c.cost_points, c.delivery),
                             (k, name, cost, delivery))
            self.assertEqual(c.pool, "RESERVE")  # D017 预备队池


# ════════════════ ② 苏德镜像卡同型一致 ════════════════

class TestMirrorConsistency(unittest.TestCase):
    """六对镜像：结构性字段一致（数值/阵营特化位排除集——air_data.MIRROR_PAIRS 注成文）。"""

    def test_mirror_pairs_declared_for_all_six_roles(self):
        self.assertEqual(air_data.MIRROR_PAIRS, (
            ("PO2", "FW189"), ("PE2", "JU88"), ("IL2M", "JU87D"),
            ("YAK9", "FW190A"), ("LI2", "JU52"),
            ("SU_PARATROOP", "GER_PARATROOP")))

    def test_aircraft_mirror_structural_identity(self):
        for ka, kb in air_data.MIRROR_PAIRS[:-1]:
            a, b = tpl(ka), tpl(kb)
            self.assertEqual(a.role, b.role, (ka, kb))                       # 同职能
            if a.role is AirRole.ATTACK:
                # 攻击机对武器档刻意不对称（硬要求①"Il-2M 配 STRAFE+BOMB"vs ④
                # "Ju 87D 配 BOMB"最小配置）——共同档=BOMB 须同有，另档成文断言
                self.assertIn("BOMB", weapon_names(a), (ka, kb))
                self.assertIn("BOMB", weapon_names(b), (ka, kb))
                self.assertEqual(set(weapon_names(a)) - set(weapon_names(b)),
                                 {"STRAFE"}, (ka, kb))
                # 〔拍板〕B-21：Il-2M 置位 / Ju 87D 不置（can_engage_air 刻意不对称）
                self.assertNotEqual(a.can_engage_air, b.can_engage_air, (ka, kb))
            else:
                self.assertEqual(weapon_names(a), weapon_names(b), (ka, kb))  # 同武器档名集
                self.assertEqual(a.can_engage_air, b.can_engage_air, (ka, kb))
            self.assertEqual(a.paratroop_seats, b.paratroop_seats, (ka, kb))
            self.assertEqual(set(a.payload_price), set(b.payload_price), (ka, kb))
            self.assertEqual(a.payload_max_supply > 0, b.payload_max_supply > 0, (ka, kb))
            if a.role is AirRole.ATTACK:
                # 俯冲位为 Ju 87D 专属（硬要求④＋§D.1 #19"has_dive（Ju 87D 置位）"）——
                # 攻击机对刻意不对称：德俯冲精轰 vs 苏低空强袭
                self.assertNotEqual(a.has_dive, b.has_dive, (ka, kb))
            else:
                self.assertEqual(a.has_dive, b.has_dive, (ka, kb))

    def test_mirror_faction_asymmetry_documented(self):
        # 镜像≠同值：阵营差分位（v1.9 :339 苏皮厚消耗/德精准精密）须有实差——
        # 数值五件（价/HP/甲/速/战力机动）不许全等（全等=镜像表失职）
        for ka, kb in air_data.MIRROR_PAIRS[:-1]:
            a, b = tpl(ka), tpl(kb)
            diffs = [(f, getattr(a, f), getattr(b, f)) for f in
                     ("cost_body", "hp_max", "armor_aa", "speed_cm_tick",
                      "dogfight_power", "maneuver")
                     if getattr(a, f) != getattr(b, f)]
            self.assertTrue(diffs, (ka, kb, "镜像对数值五件全等——阵营差分缺失"))

    def test_transport_pair_same_price_and_spec(self):
        # 〔GDD〕v1.9 :334"⑤ Ju 52运输机 · 40分 — 同Li-2"——价/载荷/舱位/价表同构
        # （2026-10-03 拍板：payload_price 一池化为 {"SUPPLY": 每重量单位单价}）
        a, b = air_data.LI2, air_data.JU52
        self.assertEqual((a.cost_body, a.paratroop_seats, a.payload_max_supply,
                          a.payload_price["SUPPLY"]),
                         (b.cost_body, b.paratroop_seats, b.payload_max_supply,
                          b.payload_price["SUPPLY"]))

    def test_paratroop_mirror_structural_identity(self):
        a = air_data.CARD_OBJECTS["SU_PARATROOP"]
        b = air_data.CARD_OBJECTS["GER_PARATROOP"]
        self.assertEqual(a.pool, b.pool)
        for c in (a, b):  # 投送限定：己方 TRANSPORT 且配舱
            self.assertIs(c.delivery.role, AirRole.TRANSPORT)
            self.assertEqual(c.delivery.paratroop_seats, 1)


# ════════════════ ③ 跨卡合理性 ════════════════

class TestCrossCardSanity(unittest.TestCase):

    def test_fighter_faster_than_bomber(self):
        # 任务口径：战斗机速度档>轰炸机（同阵营；跨阵营亦然）
        for fk, bk in (("YAK9", "PE2"), ("FW190A", "JU88"),
                       ("YAK9", "JU88"), ("FW190A", "PE2")):
            self.assertGreater(tpl(fk).speed_cm_tick, tpl(bk).speed_cm_tick,
                               (fk, bk))

    def test_fighters_fastest_within_faction(self):
        for keys in (air_data.SOVIET_AIR, air_data.GERMAN_AIR):
            fighters = [t.speed_cm_tick for t in keys if t.role is AirRole.FIGHTER]
            others = [t.speed_cm_tick for t in keys if t.role is not AirRole.FIGHTER]
            self.assertGreater(min(fighters), max(others))

    def test_speed_matches_gdd03_km_h_ordering(self):
        # 〔数锚〕GDD-03 §2.4 速度序（:131-140）保持：Fw190A>Yak9>Pe-2>Ju88>Il2M=Ju87D
        # >Fw189>Li-2>Ju52>Po-2
        order = ("FW190A", "YAK9", "PE2", "JU88", "IL2M", "JU87D",
                 "FW189", "LI2", "JU52", "PO2")
        speeds = [tpl(k).speed_cm_tick for k in order]
        self.assertEqual(speeds, sorted(speeds, reverse=True))
        # Il-2M 与 Ju 87D 同为 400km/h 档
        self.assertEqual(tpl("IL2M").speed_cm_tick, tpl("JU87D").speed_cm_tick)

    def test_alt_tiers_cover_r23(self):
        # 高度层覆盖 R-23 三层（v1.9 :312-317）：低/中/高各有可及机型
        ceilings = {int(t.alt_ceiling) for t in air_data.AIRCRAFT_TEMPLATES}
        self.assertEqual(ceilings, {int(AltTier.LOW), int(AltTier.MID), int(AltTier.HIGH)})
        self.assertIs(air_data.PO2.alt_ceiling, AltTier.LOW)      # §A :677
        self.assertIs(air_data.FW189.alt_ceiling, AltTier.HIGH)   # §A :689

    def test_fighters_reach_every_tier(self):
        # R-20/R-23：战斗机可及高空——全卡 ceiling ≤ 战斗机 ceiling（缠斗互在可及层可达）
        fighter_ceiling = max(int(t.alt_ceiling) for t in air_data.AIRCRAFT_TEMPLATES
                              if t.role is AirRole.FIGHTER)
        for t in air_data.AIRCRAFT_TEMPLATES:
            self.assertLessEqual(int(t.alt_ceiling), fighter_ceiling, t.name)
        # 进场派生式（AMB-03）：真实 entry_tier 抽查
        self.assertIs(entry_tier(air_data.PO2.alt_ceiling), AltTier.LOW)
        self.assertIs(entry_tier(air_data.YAK9.alt_ceiling), AltTier.MID)

    def test_weapon_target_domains(self):
        # §D.3：空射武器 target_mask=GROUND；无对空武器档案（R-20 缠斗走模板掷骰）
        for t in air_data.AIRCRAFT_TEMPLATES:
            for w, _n in t.weapons:
                self.assertEqual(int(w.target_mask), int(TargetDomain.GROUND),
                                 f"{t.name}:{w.name}")
                self.assertEqual(w.target_mask & TargetDomain.AIR, 0,
                                 f"{t.name}:{w.name} 禁对空域")
                if w.name == "BOMB":
                    self.assertIs(w.damage_type, DamageType.HE)
                    self.assertIs(w.trajectory, Trajectory.BALLISTIC)
                if w.name == "STRAFE":
                    self.assertIs(w.damage_type, DamageType.KE)      # air.py:399 判据
                    self.assertIs(w.trajectory, Trajectory.DIRECT)  # air.py:398 判据

    def test_prices_match_gdd_card_faces(self):
        # 〔GDD〕价格逐卡对表（v1.9 :321-326/:330-335）
        for k, price in GDD_PRICES.items():
            obj = air_data.CARD_OBJECTS[k]
            got = obj.cost_body if isinstance(obj, AircraftTemplate) else obj.cost_points
            self.assertEqual(got, price, k)

    def test_per_card_limit_is_two_in_air(self):
        # 〔拍板〕B-24/D032"每机型限2"=同型在空≤2（§D.1 无每卡限份字段——
        # 全局 air_per_type_max 单轨承载，v1.9 :293 运行时口径）
        self.assertEqual(CONFIG.air_per_type_max, 2)
        for f in dataclasses.fields(AircraftTemplate):
            self.assertNotIn("limit", f.name)
        # 真实门冒烟：第三架同型被拒（B-24 呼叫门——air.py:370-373）
        w = mkworld()
        for _ in range(2):
            self.assertIsNotNone(cmd_air_call(w, w.players[0], air_data.YAK9, {}))
        self.assertIsNone(cmd_air_call(w, w.players[0], air_data.YAK9, {}))

    def test_dogfight_stats_match_gdd03_table(self):
        # 〔数锚〕GDD-03 §2.4（:131-140）对空战力/机动照抄对表
        for k, (p, m) in GDD_DOGFIGHT.items():
            self.assertEqual((tpl(k).dogfight_power, tpl(k).maneuver), (p, m), k)

    def test_hp_band_and_il2m_anchor(self):
        # 〔数锚〕GDD-03 :12"飞机60~80、Il-2=130"＋:211
        self.assertEqual(air_data.IL2M.hp_max, 130)
        for t in air_data.AIRCRAFT_TEMPLATES:
            if t is not air_data.IL2M:
                self.assertTrue(60 <= t.hp_max <= 80, t.name)

    def test_po2_speed_at_recon_ref_anchor(self):
        # air.py:137 锚点："慢速(Po-2)速度因子=10000"——Po-2 ≤ air_recon_speed_ref
        self.assertLessEqual(air_data.PO2.speed_cm_tick, CONFIG.air_recon_speed_ref)

    def test_faction_flavor_orderings(self):
        # v1.9 :339 阵营差异：苏=皮厚（Il-2 甲/HP 顶）、德=精准（斯图卡散布最低、
        # Fw 190 战力最高）
        self.assertEqual(max(t.armor_aa for t in air_data.AIRCRAFT_TEMPLATES),
                         air_data.IL2M.armor_aa)
        self.assertEqual(max(t.dogfight_power for t in air_data.AIRCRAFT_TEMPLATES),
                         air_data.FW190A.dogfight_power)
        bombs = [(t.name, w.dispersion_cm) for t in air_data.AIRCRAFT_TEMPLATES
                 for w, _n in t.weapons if w.name == "BOMB"]
        self.assertEqual(min(bombs, key=lambda x: x[1])[0], "Ju 87D斯图卡")
        # Ju 88"载弹多"（v1.9 :331）——BOMB 载荷上限全场第一
        self.assertEqual(max(t.payload_max_bombs for t in air_data.AIRCRAFT_TEMPLATES),
                         air_data.JU88.payload_max_bombs)


# ════════════════ ④ 与 air.py 构造器签名严格匹配 ════════════════

class TestConstructorSignatureMatch(unittest.TestCase):

    def test_rebuild_through_real_constructor_equals_declared(self):
        # 真实构造器重建逐字段相等（frozen dataclass eq）——不造假结构
        for k in AIRCRAFT_KEYS:
            rebuilt = AircraftTemplate(**air_data.CARD_KWARGS[k])
            self.assertEqual(rebuilt, tpl(k), k)

    def test_all_templates_are_real_frozen_instances(self):
        for t in air_data.AIRCRAFT_TEMPLATES:
            self.assertIsInstance(t, AircraftTemplate)
            self.assertTrue(dataclasses.is_dataclass(t))
        # slots+ frozen 构造拒未知键（签名严格性）
        with self.assertRaises(TypeError):
            AircraftTemplate(template_id=99, name="X", role=AirRole.RECON,
                             cost_body=1, hp_max=1, armor_aa=0, speed_cm_tick=1,
                             dogfight_power=1, maneuver=1, alt_ceiling=AltTier.LOW,
                             bogus_field=1)

    def test_real_pipeline_call_gate_smoke(self):
        # §F1 真实门冒烟：十卡合法载荷全部可呼叫，弹药初始化按 GAP2-04 口径
        for k in AIRCRAFT_KEYS:
            t = tpl(k)
            for team in (0, 1):
                w = mkworld()
                a = cmd_air_call(w, w.players[team], t, legal_payload(t))
                self.assertIsNotNone(a, k)
                self.assertEqual(a.ammo_left["BOMB"], legal_payload(t).get("BOMB", 0), k)
                self.assertEqual(a.ammo_left["SUPPLY"],
                                 legal_payload(t).get("SUPPLY", 0), k)
                strafe = sum(n for wp, n in t.weapons if wp.name == "STRAFE")
                self.assertEqual(a.ammo_left["STRAFE"], strafe, k)
                self.assertEqual(a.hp_current, t.hp_max, k)  # GAP3-04 满血进场
                # AMB-03〔P1 2026-10-13 批注：entry_tier 按角色（FIGHTER=HIGH——
                # manual.txt:426-428「fighters will be high」）〕
                self.assertEqual(a.alt_tier, entry_tier(t.alt_ceiling, t.role), k)

    def test_real_pipeline_slot_and_capacity_gates(self):
        # GAP2-26 slot_ok：FIGHTER/RECON 拒弹、TRANSPORT 拒弹、ATTACK 拒补给
        w = mkworld()
        self.assertIsNone(cmd_air_call(w, w.players[0], air_data.YAK9, {"BOMB": 1}))
        self.assertIsNone(cmd_air_call(w, w.players[0], air_data.PO2, {"SUPPLY": 1}))
        self.assertIsNone(cmd_air_call(w, w.players[0], air_data.LI2, {"BOMB": 1}))
        self.assertIsNone(cmd_air_call(w, w.players[0],
                                       air_data.IL2M, {"SUPPLY": 1}))
        # GAP2-13 容量门：超 payload_max_bombs 拒
        self.assertIsNone(cmd_air_call(w, w.players[0], air_data.IL2M,
                                       {"BOMB": air_data.IL2M.payload_max_bombs + 1}))
        self.assertIsNone(cmd_air_call(w, w.players[0], air_data.JU88,
                                       {"BOMB": air_data.JU88.payload_max_bombs + 1}))
        # 满载荷可呼叫且价=本体+弹药价（payload_price 消费）
        p = w.players[0]
        before = p.air_points
        a = cmd_air_call(w, p, air_data.JU88, {"BOMB": air_data.JU88.payload_max_bombs})
        self.assertIsNotNone(a)
        self.assertEqual(before - p.air_points,
                         air_data.JU88.cost_body
                         + air_data.JU88.payload_price["BOMB"] * air_data.JU88.payload_max_bombs)

    def test_real_pipeline_paratroop_embark_deducts_deck_copy(self):
        # B-06/B-12：装机即扣份（真实门＋deck 槽 mock）
        w = mkworld()
        slot = SimpleNamespace(template=air_data.SU_PARATROOP, copies_left=1)
        w.players[0].deck_slots = [slot]
        a = cmd_air_call(w, w.players[0], air_data.LI2,
                         {"PARATROOP": air_data.SU_PARATROOP,
                          "SUPPLY": 0})
        self.assertIsNotNone(a)
        self.assertEqual(slot.copies_left, 0)          # 装机即扣
        self.assertIs(a.paratroop_cargo, air_data.SU_PARATROOP)
        # 份尽拒呼（B-12）
        self.assertIsNone(cmd_air_call(w, w.players[0], air_data.LI2,
                                       {"PARATROOP": air_data.SU_PARATROOP}))

    def test_real_pipeline_il2m_engage_air_dumps_bombs(self):
        # D015/§D.1 #18：Il-2M 开拨转对空→dump_bombs 丢弹（真实 BOMB 档走通）
        w = mkworld()
        a = cmd_air_call(w, w.players[0], air_data.IL2M, {"BOMB": 4})
        self.assertEqual(a.ammo_left["BOMB"], 4)
        self.assertTrue(cmd_air_engage_air(w, a, True))
        self.assertEqual(a.ammo_left["BOMB"], 0)       # 弹尽抛弃
        self.assertEqual(len(w.projectiles), 4)        # 4 发 BALLISTIC 落点弹
        # B-21 反证：Ju 87D 无资格开拨（真实门）
        w2 = mkworld()
        b = cmd_air_call(w2, w.players[1], air_data.JU87D, {"BOMB": 1})
        self.assertFalse(cmd_air_engage_air(w2, b, True))


# ════════════════ 待定清单同步 ════════════════

class TestPendingListSync(unittest.TestCase):

    def test_pending_items_wellformed(self):
        self.assertGreaterEqual(len(air_data.PENDING_NUMERIC_ITEMS), 1)
        pids = [p[0] for p in air_data.PENDING_NUMERIC_ITEMS]
        self.assertEqual(len(pids), len(set(pids)))    # 编号唯一
        for pid, scope, field, value, source in air_data.PENDING_NUMERIC_ITEMS:
            self.assertRegex(pid, r"^P-\d{2}$")
            self.assertTrue(scope and field and value and source,
                            f"{pid} 四要素齐全（含建议定标来源）")

    def test_pending_list_synced_with_module_header(self):
        # 文件头『数值待定清单』与结构表逐条同步（P-xx 标记集相等）
        header = air_data.__doc__
        in_header = {p[0] for p in air_data.PENDING_NUMERIC_ITEMS
                     if p[0] in header}
        self.assertEqual(in_header, {p[0] for p in air_data.PENDING_NUMERIC_ITEMS},
                         "结构表有条目未入文件头清单——两处须同步")
        self.assertIn("数值待定清单", header)


if __name__ == "__main__":
    unittest.main()
