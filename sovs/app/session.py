"""SkirmishSession 会话胶水（FE-T07 → GP-01 §5.3 自 tools/skirmish_shell.py 迁入）。

结论先行：世界生命周期（new_game/advance/pending 展开）、命令通道持有
（CmdBus）、配置页数据（deck_info/card_cost/deck_list）与空呼花名册的全部
仿真驱动收敛在本模块；sovs/ui 渲染件只消费 dict 状态帧与回调（鸭子类型——
shell_window 头注契约）。分层纪律：本模块属 sovs/app 会话胶水层（可 import
sovs.sim/sovs.ai——tests/test_arch_constraints.py ② 守卫只涉 sovs/ui）。

GP-01 增量：卡组泛化——human_deck 不再限 su_min/ger_min 二选一（编辑器产出
data/gen/decks/<key>.json 即时可选，§7「保存→config 页即时可选」的运行面）；
对手席按人类席卡组阵营镜像（苏↔德）；deck_list/deck_editor 数据面挂本会话。
"""
from __future__ import annotations

import os

from sovs.ai import KevPlayer, LocalKevEngine
from sovs.ai.kev_client import KevUnavailableError
from sovs.app import air_roster as air_roster_mod
from sovs.sim import card_loader
from sovs.sim.air import (PHASE_COMBAT, PHASE_DEPLOY, PHASE_SETTLE)
from sovs.sim.map_loader import apply_map, load_demo_map
from sovs.sim.state_frame import state_frame
from sovs.sim.tables import CONFIG
from sovs.sim.tick import DeckSlot, Objective, make_world, world_tick
from sovs.ui.cmd_bus import CmdBus

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_PATH = os.path.join(_ROOT, "data", "gen", "cards_ground.v1.json")
DECK_DIR = os.path.join(_ROOT, "data", "gen", "decks")
GEN_DECK_DIR = DECK_DIR
DECKS = ("su_min", "ger_min")        # 内置两卡组（兼容面——new_game 不再限此域）
HUMAN_INDEX = 0                      # 人类席恒 player0（team0=南；见头注简化注）
KEV_INDEX = 1
# 中央占点（kev_game_demo.CENTER_OBJ 同锚：2km 图中央 50m 半径）
_OBJECTIVE = Objective(id=1, pos=(100000, 50000), radius_cm=5000)
_OBJECTIVE_RADIUS_CM = 5000
_KEV_ANCHORS = ((100000, 0), (100000, 100000))     # KevPlayer anchors（南北中点）


def deck_faction(deck_key: str) -> str:
    """卡组阵营（"SOVIET"/"GERMAN"——读编译产物；缺文件 raise CardLoaderError）。"""
    return card_loader.load_deck(os.path.join(DECK_DIR, deck_key + ".json")).faction


def opponent_deck_for(human_deck: str) -> str:
    """对手席卡组：按人类席阵营镜像（苏↔德——缺省/未知阵营回德军面）。"""
    try:
        return "su_min" if deck_faction(human_deck) == "GERMAN" else "ger_min"
    except Exception:                                   # noqa: BLE001（缺产物回内置面）
        return "ger_min"


def build_world(seed: int, human_deck: str):
    """遭遇战世界装配（真实数据卡）：2km 演示图+中央占点+双方现役卡组。

    人类席 player0 挂所选卡组（data/gen/decks 下任意编译产物——GP-01 §7 泛化）、
    KEV 席 player1 挂阵营镜像内置卡组。
    """
    lib = card_loader.load_library(LIB_PATH)
    w = make_world(seed, phase=PHASE_DEPLOY, size_cm=(200000, 100000))
    apply_map(w, load_demo_map())
    w.objectives.append(Objective(id=_OBJECTIVE.id, pos=_OBJECTIVE.pos,
                                  radius_cm=_OBJECTIVE_RADIUS_CM))
    kev_deck = opponent_deck_for(human_deck)
    for index, deck_key in ((HUMAN_INDEX, human_deck), (KEV_INDEX, kev_deck)):
        deck = card_loader.load_deck(os.path.join(DECK_DIR, deck_key + ".json"))
        w.players[index].deck_slots = [
            DeckSlot(lib[key].unit_template, copies) for key, copies in deck.cards]
    return w


def _make_kev_client(kev_level: str):
    """KEV 决策载体：rule=None（纯规则兜底）；local=LocalKevEngine（失败降级）。"""
    if kev_level != "local":
        return None
    try:
        return LocalKevEngine("jaredpalmer/kev-0.5b", dtype="bf16")
    except KevUnavailableError as exc:
        print("⚠ 0.5B 本地不可用（%s）——KEV 回退规则兜底" % str(exc)[:160])
        return None


class SkirmishSession:
    """session 胶水：持有 world/KEV/命令通道，向 ShellWindow 供帧供令。

    鸭子面（sovs/ui/shell_window 头注契约）：frame/advance/cmd/total_ticks/
    world_tick_count/air_roster/deck_info/deck_list/new_game/card_cost/
    pending_expands/queue_expand/deck_editor/cooldown_labels。
    """

    def __init__(self, seed: int = 42, human_deck: str = "su_min",
                 kev_level: str = "rule", kev_beat: int = 10):
        self.seed = int(seed)
        self.human_deck = human_deck
        self.kev_level = kev_level
        self.kev_beat = max(1, int(kev_beat))
        self.total_ticks = sum(CONFIG.phase_ticks)          # 600+13200=13800
        self._kev_client = _make_kev_client(kev_level)       # 构造即定档（降级链）
        self._built_kev_level = kev_level                    # 已装配档（防重复装配）
        self.pending_expands: list[dict] = []                # 待出场展开队列（A4）
        self._deck_editor = None
        self.new_game(human_deck, kev_level, seed)

    # ── 世界生命周期 ──

    def new_game(self, deck_key: str, kev_level: str, seed: int) -> None:
        """按配置重建整局（config 页「开始部署」与「再来一局」共用）。

        deck_key=data/gen/decks 下任意编译产物（GP-01 §7 泛化）；缺文件
        raise（fail-fast——编辑器保存后即时可选，删除后不可选）。
        """
        deck_path = os.path.join(DECK_DIR, deck_key + ".json")
        if not os.path.isfile(deck_path):
            raise ValueError("卡组产物不存在：%s（先经编辑器保存/编译）" % deck_path)
        self.human_deck = deck_key
        self.kev_level = kev_level
        self.seed = int(seed)
        if self.kev_level != getattr(self, "_built_kev_level", None):
            self._kev_client = _make_kev_client(self.kev_level)
            self._built_kev_level = self.kev_level
        self.world = build_world(self.seed, self.human_deck)
        self.cmd = CmdBus(self.world, HUMAN_INDEX)
        self.pending_expands = []
        beat = self.kev_beat
        self.kev = KevPlayer(
            KEV_INDEX, self._kev_client, anchors=_KEV_ANCHORS,
            purchase_every=beat, decide_every=beat, air_every=beat * 3,
            label="kev")

    # ── 驱动面（窗口/门禁消费）──

    def frame(self) -> dict:
        """人类视角状态帧（迷雾裁剪——渲染层唯一取数口）。"""
        return state_frame(self.world, HUMAN_INDEX)

    @property
    def world_tick_count(self) -> int:
        return self.world.tick

    def advance(self, n: int) -> int:
        """推进 n 拍（每拍 KEV 决策→world_tick；结算相位停推）。

        有待出场展开意图时逐拍快照单位 id 集，spawn_step 落新单位即按
        pending_expands FIFO 匹配模板自动 move 到购卡点击点（A4：位置意图
        经既有 MoveCmd 实现，人机同管线 queue_command）。
        """
        for _ in range(int(n)):
            if self.world.phase == PHASE_SETTLE:
                break
            before = ({u.id for u in self.world.units}
                      if self.pending_expands else None)
            self.kev.step(self.world)
            world_tick(self.world)
            if before is not None:
                self._expand_spawned(before)
        return self.world.tick

    def queue_expand(self, template_id: int, dest_cm) -> None:
        """登记「购卡→出场后自动开进到 dest」的展开意图（窗口点地放卡确认调用）。"""
        self.pending_expands.append({"template_id": int(template_id),
                                     "dest": (int(dest_cm[0]), int(dest_cm[1]))})

    def _expand_spawned(self, before_ids: set) -> None:
        my_team = self.world.players[HUMAN_INDEX].team
        for u in self.world.units:
            if u.id in before_ids or u.team != my_team:
                continue
            for i, entry in enumerate(self.pending_expands):
                if entry["template_id"] == u.template.template_id:
                    del self.pending_expands[i]
                    dx = abs(u.pos[0] - entry["dest"][0])
                    dy = abs(u.pos[1] - entry["dest"][1])
                    if dx > 500 or dy > 500:         # 已在场（直接出场仅差条带
                        self.cmd.move([u.id], entry["dest"])   # 钳位）则免空令
                    break

    # ── 配置页/编辑器数据 ──

    def deck_list(self) -> list[str]:
        """卡组清单（data/gen/decks 编译产物——编辑器保存后即时出现的运行面）。"""
        if not os.path.isdir(DECK_DIR):
            return list(DECKS)
        keys = sorted(p[:-5] for p in os.listdir(DECK_DIR) if p.endswith(".json"))
        return keys or list(DECKS)

    def deck_info(self, deck_key: str) -> list[dict]:
        """卡组现役卡清单（配置页列 data/gen 卡——名/价/份）。"""
        deck = card_loader.load_deck(os.path.join(DECK_DIR, deck_key + ".json"))
        lib = card_loader.load_library(LIB_PATH)
        return [{"name": lib[k].unit_template.name,
                 "cost": lib[k].unit_template.cost, "copies": n}
                for k, n in deck.cards]

    def card_cost(self, template_id: int) -> int:
        """购卡价（窗口三池预检 toast 用——引擎门仍为最终权威）。"""
        for slot in self.world.players[HUMAN_INDEX].deck_slots:
            if slot.template.template_id == int(template_id):
                return slot.template.cost
        return 0

    @property
    def deck_editor(self):
        """编辑器后端（惰性单例——pyyaml/pydantic 构建面不进无编辑器路径）。"""
        if self._deck_editor is None:
            from sovs.app.deck_editor import DeckEditor
            self._deck_editor = DeckEditor()
        return self._deck_editor

    # ── 空呼花名册（GP-01 §4：增冷却/在空态）──

    def air_roster(self) -> list[dict]:
        return air_roster_mod.build_air_roster(self.world, HUMAN_INDEX,
                                               self.human_deck)

    def deck_slot_meta(self) -> dict[int, dict]:
        """呼援轨六页签分类面（2026-10-14 呼援轨页签块）：template_id→
        {category:int, supply:bool}——帧 deck 槽无类目字段，经本 glue 面
        取 sim 模板类目（ui 层不 import sim）。"""
        from sovs.sim.types import UnitFlag
        out: dict[int, dict] = {}
        for p in self.world.players:
            for s in p.deck_slots:
                t = s.template
                if t.template_id not in out:
                    out[t.template_id] = {
                        "category": t.category,
                        "supply": bool(t.flags & UnitFlag.HAS_SUPPLY)}
        return out

    def air_bomb_price(self, template_id: int) -> int:
        """空袭按用计费呈现面（2026-10-14 计费块）：机型炸弹单价查询
        （空中选中卡「余弹价值」行用——ui 层不 import sim）。
        〔2026-10-15 勘正：CARD_OBJECTS 实址=sovs.sim.air_data（原误引
        air_roster 模块属性——纯空中路径未触、在空列表路径首跑即炸）。〕"""
        from sovs.sim.air_data import CARD_OBJECTS
        for t in CARD_OBJECTS.values():
            if t.template_id == template_id:
                return t.payload_price.get("BOMB", 0)
        return 0

    def cooldown_labels(self) -> list[tuple]:
        """冷却段数据（顶栏 HUD——[(机型名, 剩余秒)]）。"""
        return air_roster_mod.cooldown_labels(self.world, HUMAN_INDEX,
                                              self.air_roster())
