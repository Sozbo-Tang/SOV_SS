"""空裁8 空降卡购买门限定锚（2026-10-07 发起人拍板 A 案）：GDD-01 :99/:174 卡面
「仅可经Li-2/Ju 52空投（D017）」由 cmd_purchase 第四门强制——模板带
DELIVERY_AIRDROP_ONLY 位即 REJECT（不扣点不扣 deck 份不入队）。

覆盖四面（ask 验收口径）：
① 卡数据锚（test_card_data_first_batch 风格——真卡经 card_loader.load_library
   加载）：SU/GER_PARATROOP 两卡 flags=CAN_GARRISON|CAN_INFILTRATE|
   DELIVERY_AIRDROP_ONLY（int 16394=2+8+16384），余 8 真卡不带该位；
   raw JSON int 表示＋ground_provenance 空裁8 两行留痕对表；
② 真卡购买 REJECT：deck 份/点数充分（判别「限定门拒」而非资源门拒——三门全过
   旧实现会 ACCEPT）且点数/deck 份/队列/八通道 PCG32 state 四不动；
③ 非空降真卡（SU_RIFLE/GER_GRENADIER 两阵营）购买照常 ACCEPT 扣点扣份；
④ AirCallCmd PARATROOP 投送链回归：空降两卡经命令流（queue_command→
   consume_commands）呼叫 LI2/JU52 装机扣份照常（B-06/B-12——扣份不经购买门），
   air_points 扣本体价 40、paratroop_cargo 身份对表。

数据源＝仓库 data/gen/cards_ground.v1.json（重建由 build_cards 落地，字节稳定锚
test_card_pipeline/test_card_data_first_batch 在库）。仅本文件自检，不跑全量。
"""
import json
import unittest
from pathlib import Path

from sovs.sim import card_loader as cl
from sovs.sim.air import AirState, PHASE_DEPLOY
from sovs.sim.air_data import JU52, LI2
from sovs.sim.tick import (AirCallCmd, DeckSlot, PurchaseCmd, cmd_purchase,
                           consume_commands, make_world, queue_command,
                           world_tick)
from sovs.sim.types import UnitFlag

REPO_ROOT = Path(__file__).resolve().parents[1]
GEN_LIBRARY = REPO_ROOT / "data" / "gen" / "cards_ground.v1.json"

#: 首批 10 卡全集（test_card_data_first_batch.FIRST_BATCH 同款——批量负扫描用）
ALL_CARDS = (
    "SU_RECON", "SU_RIFLE", "SU_PARATROOP", "SU_COMMISSAR", "SU_T3485",
    "SU_ZIS3", "SU_TRUCK", "GER_GRENADIER", "GER_PARATROOP", "GER_PAK40",
)
PARATROOP_KEYS = ("SU_PARATROOP", "GER_PARATROOP")
#: 空降两卡 flags 期望值：CAN_GARRISON(1<<1)|CAN_INFILTRATE(1<<3)|新位(1<<14)
#: 〔评审勘正 2026-10-07：原注释两令牌名写反——实值 CAN_GARRISON=1<<1、
#:  CAN_INFILTRATE=1<<3（types.py UnitFlag）；数值式与枚举断言原本即正确〕
PARA_FLAGS_INT = (1 << 1) | (1 << 3) | (1 << 14)

_LIB = None


def library():
    """卡库惰性加载（data/gen 首批产物——空降两卡在库）。"""
    global _LIB
    if _LIB is None:
        _LIB = cl.load_library(GEN_LIBRARY)
    return _LIB


def channels(w):
    """八通道 PCG32 内部 state 快照（test_airdrop_spawn.channels 同源口径）。"""
    return [r.state for r in w.rng._rngs]


class TestAirdropOnlyCardData(unittest.TestCase):
    """卡数据锚：两卡带 token（值位或）、余 8 卡不带、JSON int 表示、provenance。"""

    def test_paratroop_cards_carry_airdrop_only_flag(self):
        # PB-31（CAN_INFILTRATE）+PB-57（CAN_GARRISON）+空裁8（DELIVERY_AIRDROP_ONLY）
        for key in PARATROOP_KEYS:
            ut = library()[key].unit_template
            self.assertEqual(int(ut.flags), PARA_FLAGS_INT, key)
            self.assertEqual(ut.flags, UnitFlag(
                UnitFlag.CAN_INFILTRATE | UnitFlag.CAN_GARRISON
                | UnitFlag.DELIVERY_AIRDROP_ONLY))
            self.assertTrue(ut.flags & UnitFlag.DELIVERY_AIRDROP_ONLY, key)

    def test_other_cards_do_not_carry_the_bit(self):
        # 批量负扫描：余 8 真卡不带该位（购买门不扰非空降卡的判据面）
        for key in ALL_CARDS:
            if key in PARATROOP_KEYS:
                continue
            self.assertEqual(
                int(library()[key].unit_template.flags)
                & int(UnitFlag.DELIVERY_AIRDROP_ONLY), 0, key)

    def test_json_int_representation_and_token_value(self):
        # DATA-01 §2.4：JSON 一律落 int——2|8|16384=16394；TOKEN_VALUE 单点映射自 UnitFlag
        doc = json.loads(GEN_LIBRARY.read_text(encoding="utf-8"))
        by_key = {c["card_key"]: c for c in doc["cards"]}
        for key in PARATROOP_KEYS:
            self.assertEqual(by_key[key]["flags"], PARA_FLAGS_INT, key)
        from sovs.sim import card_schema as cs
        self.assertEqual(cs.TOKEN_VALUE["flags"]["DELIVERY_AIRDROP_ONLY"],
                         1 << 14)

    def test_provenance_airdrop_only_rows_present(self):
        # ground_provenance.csv 空裁8 两行留痕随库内嵌（GDD-01 卡面/D017）
        doc = json.loads(GEN_LIBRARY.read_text(encoding="utf-8"))
        prov = {(e["card_key"], e["source_ref"][:3])
                for c in doc["cards"] for e in c["_provenance"]}
        for key in PARATROOP_KEYS:
            self.assertIn((key, "空裁8"), prov)


class TestPurchaseGateAirdropOnly(unittest.TestCase):
    """cmd_purchase 第四门：真空降卡 REJECT（三态不动零掷骰）；命令流同口径。"""

    def _deploy_world(self, key, seed=42):
        w = make_world(seed, phase=PHASE_DEPLOY)
        p = w.players[0]
        tpl = library()[key].unit_template
        p.deck_slots = [DeckSlot(template=tpl, copies_left=2)]
        return w, p, tpl

    def test_real_paratroop_cards_rejected_with_resources_sufficient(self):
        # 判别锚：deck 份 2/点数 1000≥cost 60·65——三门全过（旧实现 ACCEPT），
        # 第四门按模板位拒；点数/deck 份/spawn_queue/八通道 state 四不动
        for key in PARATROOP_KEYS:
            w, p, tpl = self._deploy_world(key, seed=42)
            cost = tpl.cost
            rng0 = channels(w)
            self.assertFalse(cmd_purchase(w, p, tpl), key)
            self.assertEqual((p.points, p.deck_slots[0].copies_left,
                              len(p.spawn_queue)), (1000, 2, 0), key)
            self.assertGreaterEqual(p.points, cost)          # 拒因非点数
            self.assertEqual(channels(w), rng0, key)         # 零掷骰

    def test_reject_via_purchase_cmd_command_stream(self):
        # §D.7 PurchaseCmd→cmd_purchase 命令流同拒（tick1 consume 后三态不动）
        w, p, tpl = self._deploy_world("SU_PARATROOP", seed=11)
        queue_command(w, PurchaseCmd(player=p, template=tpl))
        world_tick(w)
        self.assertEqual((w.tick, p.points, p.deck_slots[0].copies_left,
                          len(p.spawn_queue)), (1, 1000, 2, 0))

    def test_non_paratroop_real_cards_purchase_unaffected(self):
        # 对照组：两阵营非空降真卡照常 ACCEPT——扣点（1000−45/1000−50）、扣份、入队
        for key, cost in (("SU_RIFLE", 45), ("GER_GRENADIER", 50)):
            w = make_world(42, phase=PHASE_DEPLOY)
            p = w.players[0]
            tpl = library()[key].unit_template
            p.deck_slots = [DeckSlot(template=tpl, copies_left=2)]
            self.assertTrue(cmd_purchase(w, p, tpl), key)
            self.assertEqual((p.points, p.deck_slots[0].copies_left,
                              len(p.spawn_queue)), (1000 - cost, 1, 1), key)
            self.assertIs(p.spawn_queue[0], tpl)


class TestAirCallParatroopChainRegression(unittest.TestCase):
    """AirCallCmd PARATROOP 投送链回归：装机扣份照常（购买门不触航空链）。"""

    def _call(self, w, player, aircraft, tpl):
        queue_command(w, AirCallCmd(player=player, template=aircraft,
                                    payload={"PARATROOP": tpl}))
        consume_commands(w)
        return w.aircraft[-1] if w.aircraft else None

    def test_airdrop_delivery_chain_with_real_cards(self):
        # B-06/B-12：对表机型 LI2/JU52 装机即扣 deck 份（2→1）、扣本体价 40
        # （PARATROOP 不计价——D017 预备队池已付）、paratroop_cargo 身份对表
        for key, ac in (("SU_PARATROOP", LI2), ("GER_PARATROOP", JU52)):
            w = make_world(42)
            p = w.players[0]
            tpl = library()[key].unit_template
            p.deck_slots = [DeckSlot(template=tpl, copies_left=2)]
            before = p.air_points
            a = self._call(w, p, ac, tpl)
            self.assertIsNotNone(a, key)
            self.assertIs(a.state, AirState.INBOUND, key)
            self.assertIs(a.paratroop_cargo, tpl, key)
            self.assertEqual(p.deck_slots[0].copies_left, 1, key)
            self.assertEqual(p.air_points, before - ac.cost_body, key)


if __name__ == "__main__":
    unittest.main()
