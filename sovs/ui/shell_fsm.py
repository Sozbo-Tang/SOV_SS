"""四页状态机（FE-T07 → 交互重设计 v2 → GP-01 §4/§3/§7）：纯逻辑，pytest 可测零 arcade。

结论先行：可玩壳的页面流转/盲部署计时/选区（单位+飞机双通道）/编组（含取组
剪尸）/待令/炮击参数态/页面门/toast 队列（含引擎拒绝回执消费）/退出确认态/
deck_edit 编辑器页/命令分发语义全部收敛在本模块（零渲染依赖、零仿真依赖
——不 import arcade/sovs.sim，tests/test_arch_constraints.py ② 守卫）；
sovs/ui/shell_window.py 薄壳只做「GL 事件 → fsm 语义调用」与帧呈现，
sovs/app/session.py 会话胶水持有全部仿真驱动（含购卡→入场后自动展开的
pending 队列）。命令对象一律经注入的 cmd 鸭子（CmdBus）发出——本模块不构造
命令、不做引擎门预判之外的裁决（引擎门拒绝的反馈=rejections→toast 记事，
不替代引擎裁决）。

口径：
- 页序 CONFIG→DEPLOY→BATTLE→SETTLE（＋CONFIG↔DECK_EDIT 编辑器往返，GP-01
  §7——deck_edit 战斗键全拦同 config，ESC 返回）；游戏内三页迁移由**状态帧
  phase 字段**驱动（state_frame.py phase ∈ deploy/combat/settle——fsm 不看
  World 只看帧，迷雾/相位语义全部继承帧契约，不在 UI 层重复实现）；
- 盲部署计时 600t＝60s（tables.py:266 实现现值——**勿抄 GDD-00 D007 旧 90s**）；
- 框选=帧内**己方队**单位∪飞机落框筛选（GP-01 §4 ②段双通道选区——断箭
  框选含飞机，〔调研·路1#3〕；敌实体迷雾已由帧视角裁剪）；
- 编组 Ctrl+1..9 存 **(unit_ids, air_ids) 二元组**（§4 ②段——单位/飞机 id
  是两个独立计数器空间（tick.py next_unit_id/next_aircraft_id），并存必须
  二元组；取组剪尸跨两池同款）；
- 待令组登记面：首批五组＋reverse/strike/drop（交互重设计）＋march/unload/
  sniper/supply（GP-01 §6 「sim 有 UI 无入口」补齐）；
- 炮击三段式（GP-01 §3 UI 段）：T 待令→fm_params 参数态（模式/弹药/时长/
  齐射/徐进速度——fm_panel 呈现）→点地（POINT）/拖拽画线（LINE/CREEP）；
- 页面门键位完备性纪律：每页 inputMap 对全部战斗键给出可用/拦截二归属，
  不留悬空键——config/deck_edit 拦全部、deploy 可用 S/E/R/Z/F+数字编组、
  拦 Q/T/K/O/H/X/G/U/N/V/B/J/Y、battle 全开、settle 全拦静默；
  （P0 键位纠偏块 2026-10-13：Q=Attack Move 替 A——手册 HOTKEYS
  manual.txt:560-562；A 退役归相机 WASD 平移，manual.txt:579-580。）
- SHIFT=通用命令排队（P0 键位纠偏块——手册 General Hotkeys「SHIFT Queue
  orders」manual.txt:551）：待令态 Shift+确认=入队不清待令、连续下令排队执行
  （引擎位：MoveCmd/AttackCmd/FireMissionCmd/DismountCmd(+GarrisonCmd)
  queue 字段+consume_unit_commands 每拍一条消费；右键 Shift+移动=追加航点
  既有行为保留）；飞机令（K 空袭/O 空投）无单位级队列不入队——留痕；
- U 双击=就地立即卸载（手册「(Press U twice to unload immediately)」
  manual.txt:566-568——首按待令、待令中再按 cmd.unload(sel) 无 cm 即地旁落）；
- ESC 分层链：F1 面板→待令→待放卡→选区（含空选区）→退出确认（第二次 ESC
  才退出）；
- 取组自动剪尸：groups 保留死 id 供 HUD 灰显，取组时按当前帧活实体过滤，
  组全灭 toast『编组 N 已全灭』且不清组号（防死 id 恢复后 cmd_bus 查活落空
  的静默失败复发路径）。

飞机键位（GP-01 §4 ③段＋通用指令三态出清表）：右键=盘旋待命（AirPatrolCmd
CAP 等效=Q 映射）/Shift+右键=直飞航路/V=高度两态 toggle（P1：LOW⇄出场层——
manual.txt:421-428，三档循环退役留痕）/B=RTB（飞机通道不可逆 toast；地面通道
=P1 地面回基地退款，双通道并存）/J=对空开关/Y=缠斗脱离/K=空袭（点目标/拖拽画
攻击轴）/O=空投（选中机优先，空选区时自动代选+toast；按住左键拖拽画矩形区=
区心投放——P0 键位纠偏块 2026-10-13，单击仍=点投）/E=原地重置（中断 INGRESS
段任务）；F=快速移动（对飞机不做——aircraft_move_step 恒速，§4 三态出清表）。
P1 机制块键位（2026-10-13，断箭手册 P1 补建）：C=诱饵（manual.txt:505-509）/
Z 按单位分派=飞机加力·地面雷达·冲刺（manual HOTKEYS「Z Sprint (infantry)/
Afterburner (fighters)」+Radar 同键）/N=激光照射（原狙击观测挪 L——手册 N 键
让位留痕）/M=登车/P=精密打击（近激光位）/TAB 子选后命令面=仅焦点单位
（basics:59-60）。

键位证据纪律（三档溯源）：〔档〕FE-01 已落档实证／〔研〕FE-03 输入调研落档
（Edge Scroll/方向键平移/Shift 减选/右键=移动/两段式确认/K 空袭键族）／
〔例〕主流 RTS 惯例——不发明新交互范式。
"""
from __future__ import annotations

# 盲部署时长（tick，10Hz）——实现现值锚 tables.py:266 phase_ticks=(600,13200)；
# 引入处请勿硬编码别处（FE-01 §2.7：GDD-00 D007 旧 90s 已废止）。
DEPLOY_TICKS_IMPL = 600

# 首批五组命令（id, 中文标签）——窗口按钮与门禁证据共用登记面（FE-T07 口径）。
ORDER_GROUPS_FIRST_BATCH: tuple[tuple[str, str], ...] = (
    ("move", "移动族"),
    ("attack", "攻击"),
    ("fire_mission", "炮击任务"),
    ("air", "空军呼叫"),
    ("smoke_sprint", "烟幕冲刺"),
)

# 待令组登记面扩容（交互重设计 P0-2＋GP-01 §6）：reverse/strike/drop＋
# march（F 行军）/unload（U 卸载）/sniper（狙击观测）/supply（补给停靠）——
# 未登记即 ValueError 一按杀进程（会诊 P0）；首批五组常量保持不变供既有口径引用。
# 〔P1 机制块 2026-10-13（GP-01 断箭手册 P1 补建）+3 组：laser（N 激光照射——
# manual.txt:517-522；原 N 狙击观测挪 L 键留痕：狙击观测系 SOV_SS §6 自设命令
# 无手册键位，让位给手册 N=照射键）、mount（M 登车——basics:181-193 战斗期
# 组运输的 UI 入口，复用 supply 同款点己方载具交互）、precision（P 精密打击
# ——manual.txt:528-532 靠近激光位的精确弹药任务，Shift 可排队）。〕
ORDER_GROUPS_ARMABLE: tuple[tuple[str, str], ...] = ORDER_GROUPS_FIRST_BATCH + (
    ("reverse", "倒车"),
    ("strike", "空袭"),
    ("drop", "空投"),
    ("march", "行军"),
    ("unload", "卸载"),
    ("sniper", "狙击观测"),
    ("supply", "补给停靠"),
    ("laser", "激光照射"),
    ("mount", "登车"),
    ("precision", "精密打击"),
)

_ORDER_IDS = frozenset(g[0] for g in ORDER_GROUPS_ARMABLE)

# ── 页面门（键位完备性纪律：每键可用/拦截二归属，不留悬空）──
# 全部战斗键（字母键名大写；TAB/数字键另行处理）。V/B/J/Y=飞机令（GP-01 §4）；
# F/U/N=§6 移动族/支援族扩容。Q=攻击移动（P0 键位纠偏块 2026-10-13：断箭手册
# HOTKEYS「Q Attack Move」manual.txt:560-562——A 键退役：手册 W,A,S,D=相机移动
# （manual.txt:579-580）占用 A 且全文无 A 战斗令，故不留别名、A 归相机平移）。
# 〔P1 机制块 2026-10-13 +4 键：C=诱饵（manual.txt:505-509）、L=狙击观测（原 N
# 挪键——N 让位给手册激光照射键，留痕见 ORDER_GROUPS_ARMABLE 注）、M=登车
# （basics:181-193）、P=精密打击（manual.txt:528-532）。〕
COMBAT_KEYS: tuple[str, ...] = ("Q", "S", "E", "Z", "X", "R", "T", "G", "H",
                                "K", "O", "F", "U", "N", "V", "B", "J", "Y",
                                "C", "L", "M", "P")
# deploy 页可用移动族（部署期展开是既有玩法，smoke _deploy_beat 同款；F 行军
# 属移动族）；Q/T/K/O/H/X/G/U/N/V/B/J/Y/C/L/M/P 归拦截（攻击/姿态/支援/航空类
# 无部署期语义）。
DEPLOY_ALLOWED_KEYS = frozenset({"S", "E", "Z", "R", "F"})

# 待令键 → 待令组（两段式：热键待令+左键确认——〔研·FE-03〕两段式，〔例〕普世）。
# Q=attack（手册 HOTKEYS 键位；A 退役拍板见 COMBAT_KEYS 注）。〔P1 机制块
# 2026-10-13：N=laser（手册照射键）、L=sniper（原 N 挪键留痕）、M=mount、
# P=precision。〕
_ARM_BY_KEY = {"Q": "attack", "T": "fire_mission", "R": "reverse",
               "K": "strike", "O": "drop", "F": "march", "U": "unload",
               "N": "laser", "L": "sniper", "M": "mount", "P": "precision"}

# 高度档位（V 键两态 toggle 的基准面——P1 机制块 2026-10-13：manual.txt:421-428
# 「Press V to reduce altitude. Press V again to regain altitude」为高低两态，
# 原 LOW→MID→HIGH 三档循环退役；「regain」=回到机型出场层（entry_tier 按角色——
# 战斗机 HIGH/其余 MID，air.py），LOW 为唯一压低档）。
ALT_LOW, ALT_REGAIN = "LOW", "MID"

# 徐进弹幕速度三档（cm/tick @10Hz——GP-01 §3 UI 速度档；1/2.5/5 m 每秒，
# 步兵徒步跟随弹幕推进的量级。UI 档位非平衡常量，不入 tables）。
CREEP_SPEEDS_CM: tuple[int, ...] = (10, 25, 50)

TOAST_TTL = 2.5                       # toast 常显时长（秒——窗口层按 dt 泵衰减）

# 共享中文词面（selection_panel/hud 消费——飞机状态/任务摘要的人读名）。
STATE_CN: dict[str, str] = {
    "inbound": "进场", "patrol": "盘旋", "strike": "攻击", "rtb": "返航",
    "dogfight": "缠斗",
    "patrol_task": "盘旋待命", "strike_task": "对地攻击", "airdrop_task": "空投",
    "low": "低空", "mid": "中空", "high": "高空",
    "deploy": "盲部署", "combat": "实战", "settle": "结算",
}

# 引擎拒绝 → toast 短语（rejections[].cmd 名 → 人读原因；未列命令回退英文类名
# 截短——「静默拒绝」首次对玩家可见，GP-01 §4 ④段）。
_REJ_TIPS: dict[str, str] = {
    "AirAltCmd": "高度层变更被拒（超机型上限/缠斗中）",
    "AirMoveCmd": "航路改航被拒（RUN/EGRESS 段不可转向 GAP-28）",
    "AirPatrolCmd": "盘旋令被拒（RUN/EGRESS 段不可中断 GAP-28）",
    "AirStrikeCmd": "空袭令被拒（弹药/状态机门）",
    "AirEngageAirCmd": "对空开关被拒（无对空槽 B-21/返航中）",
    "FireMissionCmd": "炮击任务被拒（曲射资格/烟弹档/精密激光位/值域门）",
    "MoveCmd": "移动令被拒（状态机门）",
    "PurchaseCmd": "购卡被拒（点数/余量/相位门）",
    "MountCmd": "登车被拒（座位/资格门）",
    "SprintCmd": "冲刺被拒（冷却门）",
    "SmokeCmd": "烟幕被拒（发数/冷却门）",
    # ── P1 机制块（2026-10-13）──
    "GroundRTBCmd": "地面 RTB 被拒（车载/溃逃/收装中——先下车再撤）",
    "LaserDesignateCmd": "激光照射被拒（资格/敌方/视线门）",
    "RadarCmd": "雷达令被拒（无对空资格）",
    "SupplySwitchCmd": "补给开关被拒（非补给载具）",
    "AirAfterburnerCmd": "加力被拒（机型无加力/缠斗返航中/燃油尽）",
    "AirDecoyCmd": "诱饵被拒（机型无诱饵/发数尽）",
}
_REJ_SEEN_CAP = 64                     # 已播拒绝条目去重环（帧尾 8 条×8 帧窗）


class ShellFsm:
    """可玩壳页面状态机（窗口层每帧调 on_frame(frame) 同步；命令只经注入 cmd 鸭子发）。

    frame 为 FE-T02 公共状态帧 dict（本模块消费面：phase/tick/view/units[].id/
    team/pos_cm/stance/aircraft[].id/team/state/ammo/paratroop/alt_tier/
    engage_air/task/players/rejections/result——字段契约见 sovs/sim/state_frame.py）。
    """

    def __init__(self, *, deploy_ticks: int = DEPLOY_TICKS_IMPL):
        self.deploy_ticks = int(deploy_ticks)
        self.page = "config"            # config|deck_edit|settings|deploy|battle|settle
        # 战前配置态（config 页可改；start_deploy 后冻结为本局配置）
        self.deck_key = "su_min"        # 卡组键（data/gen/decks 下任意——编辑器产出即时可选）
        self.kev_level = "rule"         # KEV 档位：rule=规则兜底（缺省零依赖）|local=0.5B
        self.seed = 42
        # 游戏内态
        self.frame: dict | None = None
        self.selected: tuple[int, ...] = ()      # 己方选中单位 id（框选/点选并集序）
        self.selected_air: tuple[int, ...] = ()  # 己方选中飞机 id（GP-01 §4 双通道）
        self.armed_order: str | None = None      # 待令命令组（点击地图/单位即执行）
        # ── 交互重设计 v2 增量态（全部纯逻辑，无显示环境可测）──
        self.groups: dict[int, tuple] = {}   # 编组 1..9 → (unit_ids, air_ids) 二元组（死 id 保留供灰显）
        self.notifications: list[dict] = []      # toast 队列（{"text","tone","ttl"}）
        self.rejected_count: int = 0             # 无效操作累计（结算页复盘统计）
        self.armed_purchase: tuple[int, str] | None = None   # (template_id, name) 待放卡
        self.help_open: bool = False             # F1 帮助/键位面板
        self.exit_confirm: bool = False          # ESC 退出确认态（二次 ESC 才退出）
        self.tab_focus: int = 0                  # 选区内循环子选游标（TAB——跨单位/飞机两池）
        self._tab_focus_armed: bool = False       # P1：TAB 已按过（子选生效位——
                                                  # 未按 TAB=无子选，命令面走全选区；
                                                  # 选区变更复位）
        # ── GP-01 §3 炮击参数态（三段式第二段）──
        self.fm_params: dict = {"form": "POINT", "ammo": "HE", "ammo_mult": 1,
                                "salvo": "FULL", "creep_idx": 0}
        # ── GP-01 §7 deck_edit 编辑器页态（后端数据经 sovs/app/deck_editor 注入）──
        self.deck_edit: dict | None = None
        # 引擎拒绝已播去重环（(tick, cmd, ref_id) FIFO）
        self._seen_rej: list[tuple] = []

    # ── 页面迁移 ──

    def start_deploy(self) -> None:
        """config→deploy（唯一入口；游戏内页不允许——防中途重开丢局）。"""
        assert self.page == "config", "起局只允许自 config 页（当前 %s）" % self.page
        self.page = "deploy"
        self._clear_gameplay_state()

    def on_frame(self, frame: dict) -> None:
        """喂状态帧：同步游戏内三页（phase 字段驱动）、结算数据与拒绝回执。

        config/deck_edit/settle 页不吃帧（尚无世界/停驻）。
        """
        if self.page in ("config", "deck_edit", "settings", "settle"):
            return
        self.frame = frame
        phase = frame.get("phase")
        if phase == "deploy":
            self.page = "deploy"
        elif phase == "combat":
            self.page = "battle"
        elif phase == "settle":
            self.page = "settle"
        self._consume_rejections(frame)
        self._consume_refunds(frame)

    def _consume_refunds(self, frame: dict) -> None:
        """P1 RTB 退款事件→toast（manual.txt:397「immediately reimbursed」的可见
        化——帧顶层 refunds 尾 8 条，(tick, unit_id) 去重环防逐帧重播）。"""
        refunds = frame.get("refunds") or ()
        if not refunds:
            return
        for r in refunds:
            key = (r.get("tick"), r.get("unit_id"))
            if key in self._seen_rej:                  # 复用去重环（容量口径同款）
                continue
            self._seen_rej.append(key)
            if len(self._seen_rej) > _REJ_SEEN_CAP:
                del self._seen_rej[: len(self._seen_rej) - _REJ_SEEN_CAP]
            self.notify("单位 #%d 回基地退款 +%d 点（≥20%% 下限已保）"
                        % (r.get("unit_id", 0), r.get("amount", 0)))

    def _consume_rejections(self, frame: dict) -> None:
        """引擎拒绝回执→toast（GP-01 §4 ④段——「静默拒绝」可见化）。

        只播 ref_id 命中己方实体的条目（敌实体拒绝=对方操作情报噪音；玩家级
        命令 purchase/air_call 的拒绝已有 UI 预检 toast 面，不重复播）。
        帧尾 8 条窗口内同 (tick,cmd,ref_id) 去重防逐帧重播。
        """
        rejections = frame.get("rejections") or ()
        if not rejections:
            return
        own = self._alive_own_ids() | self._alive_own_air_ids()
        for r in rejections:
            key = (r.get("tick"), r.get("cmd"), r.get("ref_id"))
            if key in self._seen_rej:
                continue
            self._seen_rej.append(key)
            if len(self._seen_rej) > _REJ_SEEN_CAP:
                del self._seen_rej[: len(self._seen_rej) - _REJ_SEEN_CAP]
            if r.get("ref_id") in own:
                tip = _REJ_TIPS.get(r.get("cmd", ""),
                                    "命令 %s 被引擎拒绝" % r.get("cmd", "?"))
                self.notify(tip, tone="error", ttl=1.8)

    def reset(self) -> None:
        """结算屏「再来一局」→ 回 config（选区/待令/编组/toast 一并复位）。"""
        self.page = "config"
        self._clear_gameplay_state()
        self.frame = None

    def _clear_gameplay_state(self) -> None:
        self.selected = ()
        self.selected_air = ()
        self.armed_order = None
        self.groups = {}
        self.notifications = []
        self.armed_purchase = None
        self.help_open = False
        self.exit_confirm = False
        self.tab_focus = 0
        self.rejected_count = 0
        self.fm_params = {"form": "POINT", "ammo": "HE", "ammo_mult": 1,
                          "salvo": "FULL", "creep_idx": 0}
        self._seen_rej = []

    # ── 盲部署计时（60s/600t 实现现值）──

    @property
    def deploy_ticks_left(self) -> int:
        if self.page != "deploy" or self.frame is None:
            return 0
        return max(0, self.deploy_ticks - int(self.frame.get("tick", 0)))

    @property
    def deploy_seconds_left(self) -> float:
        return self.deploy_ticks_left / 10.0          # 10Hz（TICK_HZ 全局口径）

    # ── 选区（双通道：框选=帧内己方队几何筛选；迷雾由帧视角先行裁剪）──

    def select_units(self, ids) -> None:
        self.selected = tuple(dict.fromkeys(ids))     # 去重保序
        self.tab_focus = 0
        self._tab_focus_armed = False                 # P1：新选区=无子选

    def select_aircraft(self, ids) -> None:
        """飞机通道选区（GP-01 §4 ②段——去重保序，TAB 游标归零）。"""
        self.selected_air = tuple(dict.fromkeys(ids))
        self.tab_focus = 0
        self._tab_focus_armed = False                 # P1：新选区=无子选

    def clear_selection(self) -> None:
        self.selected = ()
        self.selected_air = ()

    def box_select(self, p0, p1) -> tuple[int, ...]:
        """框选（cm 坐标两点，方向任意）：己方队单位∪飞机、落框即选；写双通道
        选区并返回单位选区（既有调用面口径不变——飞机并集见 selected_air）。"""
        if self.frame is None:
            return ()
        x0, x1 = sorted((int(p0[0]), int(p1[0])))
        y0, y1 = sorted((int(p0[1]), int(p1[1])))
        team = self.frame.get("view")
        picked = [u["id"] for u in self.frame.get("units", ())
                  if (team is None or u.get("team") == team)
                  and x0 <= u["pos_cm"][0] <= x1 and y0 <= u["pos_cm"][1] <= y1]
        picked_air = [a["id"] for a in self.frame.get("aircraft", ())
                      if (team is None or a.get("team") == team)
                      and x0 <= a["pos_cm"][0] <= x1 and y0 <= a["pos_cm"][1] <= y1]
        self.select_units(picked)
        self.select_aircraft(picked_air)
        return self.selected

    def click_unit(self, uid: int, *, shift: bool = False) -> tuple[int, ...]:
        """左键点选己方单位：Shift=切换加减选（在选区内=移除，不在=加选——
        〔研·FE-03〕断箭 Shift-click removes + RTS 并集惯例合并语义）。
        非Shift 点选=新选区（飞机通道同步清空）。"""
        ids = list(self.selected)
        if shift:
            if uid in ids:
                ids.remove(uid)
            else:
                ids.append(uid)
            self.select_units(ids)
        else:
            self.select_units([uid])
            self.selected_air = ()
        return self.selected

    def click_aircraft(self, aid: int, *, shift: bool = False) -> tuple[int, ...]:
        """左键点选己方飞机（GP-01 §4 ②段——镜像 click_unit 语义跨通道）。"""
        ids = list(self.selected_air)
        if shift:
            if aid in ids:
                ids.remove(aid)
            else:
                ids.append(aid)
            self.select_aircraft(ids)
        else:
            self.select_aircraft([aid])
            self.selected = ()
        return self.selected_air

    @property
    def has_selection(self) -> bool:
        """任一通道有选区（ESC 分层链/右键语义的判据）。"""
        return bool(self.selected or self.selected_air)

    # ── 编组（Ctrl+1..9 建组 / 数字取组——〔档〕FE-01 §1.3.2；GP-01 §4 扩飞机）──

    def assign_group(self, n: int) -> tuple[int, ...] | None:
        """建组：当前双通道选区快照入册 (unit_ids, air_ids)（死 id 不在此产生
        ——选区来自当前帧）；两通道皆空=无操作。"""
        if not (1 <= int(n) <= 9):
            return None
        if not (self.selected or self.selected_air):
            return None                      # 空选区建组=无操作（RTS 惯例）
        self.groups[int(n)] = (tuple(self.selected), tuple(self.selected_air))
        return self.groups[int(n)]

    def recall_group(self, n: int) -> tuple[int, ...]:
        """取组：按当前帧活实体剪尸（单位∪飞机两池——星际/帝国惯例）；组全灭
        toast 不清号（HUD 灰显数据源=groups 原值）。返回单位选区（兼容面）。"""
        entry = self.groups.get(int(n))
        if not entry:
            return ()
        unit_ids, air_ids = entry
        alive_u = self._alive_own_ids()
        alive_a = self._alive_own_air_ids()
        picked_u = tuple(i for i in unit_ids if i in alive_u)
        picked_a = tuple(i for i in air_ids if i in alive_a)
        if not (picked_u or picked_a):
            self.clear_selection()               # 不留陈旧选区（组内无活实体）
            self.notify("编组 %d 已全灭" % int(n), tone="error")
            return ()
        self.select_units(picked_u)
        self.select_aircraft(picked_a)
        return picked_u

    def group_alive_count(self, n: int) -> int:
        """编组栏角标数据：组内当前帧活实体数（0 且有组=全灭灰显）。"""
        entry = self.groups.get(int(n))
        if not entry:
            return 0
        unit_ids, air_ids = entry
        alive = self._alive_own_ids() | self._alive_own_air_ids()
        return sum(1 for i in tuple(unit_ids) + tuple(air_ids) if i in alive)

    def _alive_own_ids(self) -> frozenset:
        if self.frame is None:
            return frozenset()
        view = self.frame.get("view")
        return frozenset(u["id"] for u in self.frame.get("units", ())
                         if view is None or u.get("team") == view)

    def _alive_own_air_ids(self) -> frozenset:
        if self.frame is None:
            return frozenset()
        view = self.frame.get("view")
        return frozenset(a["id"] for a in self.frame.get("aircraft", ())
                         if view is None or a.get("team") == view)

    def _own_ids(self) -> list[int]:
        if self.frame is None:
            return []
        view = self.frame.get("view")
        return [u["id"] for u in self.frame.get("units", ())
                if view is None or u.get("team") == view]

    # ── 待令态（首批五组+扩容七组）──

    def arm_order(self, group: str) -> None:
        if group not in _ORDER_IDS:
            raise ValueError("未知命令组 %r（待令组：%s）"
                             % (group, [g[0] for g in ORDER_GROUPS_ARMABLE]))
        self.armed_order = group

    def clear_order(self) -> None:
        self.armed_order = None

    # ── 炮击参数态（GP-01 §3 三段式第二段——fm_panel 呈现/调参）──

    def set_fm_param(self, key: str, value) -> None:
        """参数值域门（表单面收口——越域 ValueError 即刻暴露而非静默吞）。"""
        p = self.fm_params
        if key == "form":
            if value not in ("POINT", "LINE", "CREEP"):
                raise ValueError("弹幕模式 %r（POINT|LINE|CREEP）" % (value,))
            p["form"] = value
        elif key == "ammo":
            if value not in ("HE", "SMOKE", "PRECISION"):
                raise ValueError("弹药 %r（HE|SMOKE|PRECISION——P1 第三弹药位）"
                                 % (value,))
            p["ammo"] = value
        elif key == "ammo_mult":
            if int(value) not in (1, 2, 3):
                raise ValueError("时长档 %r（1..3）" % (value,))
            p["ammo_mult"] = int(value)
        elif key == "salvo":
            if value not in ("FULL", "HALF"):
                raise ValueError("齐射 %r（FULL|HALF）" % (value,))
            p["salvo"] = value
        elif key == "creep_idx":
            if not (0 <= int(value) < len(CREEP_SPEEDS_CM)):
                raise ValueError("徐进速度档 %r（0..%d）"
                                 % (value, len(CREEP_SPEEDS_CM) - 1))
            p["creep_idx"] = int(value)
        else:
            raise ValueError("未知炮击参数 %r" % key)

    def fm_kwargs(self) -> dict:
        """当前参数态 → cmd_bus.fire_mission 关键字（徐进速度仅 CREEP 形态携带）。"""
        p = self.fm_params
        return {"form": p["form"], "ammo": p["ammo"],
                "ammo_mult": p["ammo_mult"], "salvo_mode": p["salvo"],
                "creep_speed": (CREEP_SPEEDS_CM[p["creep_idx"]]
                                if p["form"] == "CREEP" else 0)}

    # ── 待放卡（部署页购卡两段式：点槽装弹→点地确认）──

    def arm_purchase(self, template_id: int, name: str) -> None:
        self.armed_purchase = (int(template_id), str(name))

    def cancel_purchase(self) -> None:
        self.armed_purchase = None

    # ── deck_edit 编辑器页（GP-01 §7——数据经 sovs/app/deck_editor 后端注入）──

    def open_settings(self) -> None:
        """设置页（改键——2026-10-14 设置改键块）：只允许自 config 进入。"""
        assert self.page == "config", "设置页只允许自 config 页进入（当前 %s)" \
            % self.page
        self.page = "settings"

    def close_settings(self) -> None:
        assert self.page == "settings", "设置页未开（当前 %s）" % self.page
        self.page = "config"

    def open_deck_edit(self, state: dict) -> None:
        """config→deck_edit（state={deck_key,faction,cards,tab,errors}——窗口层
        自后端装填；fsm 只持纯数据态）。"""
        assert self.page == "config", "编辑器只允许自 config 页进入（当前 %s）" % self.page
        self.page = "deck_edit"
        entry = dict(state)
        entry.setdefault("cards", [])
        entry.setdefault("tab", "")
        entry.setdefault("errors", [])
        entry["cards"] = [(k, int(n)) for k, n in entry["cards"]]
        entry["renaming"] = False
        entry["rename_key"] = ""
        self.deck_edit = entry

    def close_deck_edit(self) -> None:
        """deck_edit→config（ESC/返回按钮——保存与否由窗口层在后端先行裁决）。"""
        assert self.page == "deck_edit", "编辑器页未开（当前 %s）" % self.page
        self.page = "config"

    def deck_edit_add(self, card_key: str) -> None:
        """点卡池条目=加一份（在组即 copies+1）。"""
        cards = list(self.deck_edit["cards"])
        for i, (k, n) in enumerate(cards):
            if k == card_key:
                cards[i] = (k, n + 1)
                break
        else:
            cards.append((card_key, 1))
        self.deck_edit["cards"] = cards

    def deck_edit_delta(self, card_key: str, delta: int) -> None:
        """汇总条目 ±调份数（减到 0=移出卡组）。"""
        cards = list(self.deck_edit["cards"])
        for i, (k, n) in enumerate(cards):
            if k == card_key:
                n += int(delta)
                if n <= 0:
                    cards.pop(i)
                else:
                    cards[i] = (k, n)
                break
        self.deck_edit["cards"] = cards

    def deck_edit_set_tab(self, tab: str) -> None:
        self.deck_edit["tab"] = tab

    def deck_edit_start_rename(self) -> None:
        """改名字态开关（进入=清缓冲逐字符编辑；再进=确认退出）。"""
        if self.deck_edit["renaming"]:
            self.deck_edit["renaming"] = False
        else:
            self.deck_edit["renaming"] = True
            self.deck_edit["rename_key"] = ""

    def deck_edit_rename_key(self, ch: str) -> None:
        if self.deck_edit["renaming"]:
            self.deck_edit["rename_key"] += str(ch)

    def deck_edit_rename_backspace(self) -> None:
        if self.deck_edit["renaming"]:
            self.deck_edit["rename_key"] = self.deck_edit["rename_key"][:-1]

    # ── toast 队列（纯逻辑持有，窗口层绘制；tone=error 计入被拒统计）──

    def notify(self, text: str, *, tone: str = "info",
               ttl: float = TOAST_TTL) -> None:
        """入队 toast；与队尾同文同调的连续重复聚合为「×N」单条（battle.png
        复检②修复：8 连拒不再铺 8 行同文红字；error 计数仍逐条累加——
        rejected_count 是被拒次数统计面，不随显示聚合）。"""
        if tone == "error":
            self.rejected_count += 1
        base = str(text)
        last = self.notifications[-1] if self.notifications else None
        if last is not None and last.get("base") == base \
                and last["tone"] == tone:
            last["count"] = int(last.get("count", 1)) + 1
            last["ttl"] = float(ttl)               # 聚合条目刷新存活窗
            last["text"] = "%s ×%d" % (base, last["count"])
            return
        self.notifications.append({"text": base, "tone": tone,
                                   "ttl": float(ttl), "base": base,
                                   "count": 1})

    def pump_notifications(self, dt: float) -> None:
        """窗口层每帧泵衰减（ttl 秒；过期出队）——确定性，无显示环境可测。"""
        for note in self.notifications:
            note["ttl"] -= float(dt)
        self.notifications = [n for n in self.notifications if n["ttl"] > 0]

    # ── TAB 子选（双通道选区内循环焦点——〔档〕FE-01 §1.3.1 子选择）──

    def cycle_focus(self) -> int | None:
        total = len(self.selected) + len(self.selected_air)
        if not total:
            return None
        self.tab_focus = (self.tab_focus + 1) % total
        self._tab_focus_armed = True                   # P1：TAB 按过=子选生效
        return self.focus_unit if self.focus_unit is not None else self.focus_aircraft

    @property
    def focus_unit(self) -> int | None:
        if not self.selected or self.tab_focus >= len(self.selected):
            return None
        return self.selected[self.tab_focus]

    @property
    def focus_aircraft(self) -> int | None:
        idx = self.tab_focus - len(self.selected)
        if not self.selected_air or not (0 <= idx < len(self.selected_air)):
            return None
        return self.selected_air[idx]

    # ── ESC 分层链（优先级：F1 面板 > 待令 > 待放卡 > 选区 > 退出确认）──

    def esc(self) -> str:
        """分层取消（〔例〕RTS 分层取消惯例；config/deck_edit/deploy/battle 同构
        ——deck_edit 返回与 settle 直接退出由窗口层特例）。返回动作名：
        help_closed/order_cleared/purchase_canceled/selection_cleared/
        exit_confirm/exit（exit=窗口层执行关闭）。"""
        if self.help_open:
            self.help_open = False
            return "help_closed"
        if self.armed_order is not None:
            self.clear_order()
            return "order_cleared"
        if self.armed_purchase is not None:
            self.cancel_purchase()
            return "purchase_canceled"
        if self.has_selection:
            self.clear_selection()
            return "selection_cleared"
        if self.exit_confirm:
            self.exit_confirm = False
            return "exit"
        self.exit_confirm = True
        return "exit_confirm"

    def cancel_exit_confirm(self) -> None:
        self.exit_confirm = False

    # ── 战斗键分发（页面门+立即令+待令；cmd=CmdBus 鸭子，None=只走门不给令）──

    def key(self, name: str, *, ctrl: bool = False, shift: bool = False,
            cmd=None) -> str | None:
        """按键语义分发（字母键大写名/'TAB'/'1'..'9'）。返回动作名（测试断言面），
        页面门拦截返回 "blocked"，未处理返回 None。"""
        if self.exit_confirm:
            self.cancel_exit_confirm()            # 任意键先撤销退出确认
        if self.page == "settle":
            return None                           # 本页无命令通道（拦而静默）
        if self.page in ("config", "deck_edit", "settings"):
            if name in COMBAT_KEYS or name == "TAB":
                self.notify("编辑器页无战斗令（ESC 返回）" if self.page == "deck_edit"
                            else "战斗令在部署/实战页可用", tone="error")
                return "blocked"
            return None                           # Enter/数字（卡组档）归窗口层
        # deploy/battle 页
        if name == "TAB":
            self.cycle_focus()
            return "tab"
        if name.isdigit():
            n = int(name)
            if ctrl:
                self.assign_group(n)
                return "group_assign"
            if 1 <= n <= 9:
                self.recall_group(n)
                return "group_recall"
            return None
        if name not in COMBAT_KEYS:
            return None
        if self.page == "deploy" and name not in DEPLOY_ALLOWED_KEYS:
            self.notify("烟幕/姿态令在实战页可用（部署期冲刺用 Z）" if name == "G"
                        else "战斗令在实战页可用", tone="error")
            return "blocked"
        sel = list(self.selected)
        sel_air = list(self.selected_air)
        if name == "S":
            if cmd is not None and sel:
                cmd.stop(sel)
            return "stop"
        if name == "E":
            if cmd is not None and sel:
                cmd.cancel(sel)
            if cmd is not None and sel_air:
                cmd.air_reset(sel_air)            # §4 三态出清：E=原地重置映射
            return "cancel"
        if name == "Z":
            # P1 机制块（2026-10-13）：Z 按单位类型分派（manual HOTKEYS「Z Sprint
            # (infantry) / Afterburner (fighters)」＋ABILITIES Radar 同键 Z）——
            # 飞机选区优先（加力 toggle）；地面选区再分流：对空资格（帧 radar_on
            # 可见）单位=雷达开关、其余=冲刺。混合选区各自归口。
            if sel_air:
                self._air_afterburner_toggle(cmd)
                return "afterburner"
            self._ground_z_dispatch(cmd, sel)
            return "z_dispatch"
        if name == "X":
            if cmd is not None and sel:
                cmd.smoke(sel)
            return "smoke"
        if name == "C":
            # P1（manual.txt:505-509）：C 诱饵手动投放（自动档切换走命令面板按钮
            # ——basics:351-352 右键语义的面板承载）。
            if cmd is not None and sel_air:
                cmd.air_decoy(sel_air, "POP")
            elif not sel_air:
                self.notify("诱饵为飞机令（先选中飞机）", tone="error")
            return "decoy"
        if name == "H":
            self._toggle_stance(cmd)
            return "stance"
        if name == "G":
            self._smoke_sprint_combo(cmd)
            return "combo"
        # ── 飞机令（GP-01 §4 ③段——空选区为前置，无选区=toast 提示）──
        if name == "V":
            self._air_alt_toggle(cmd)
            return "air_alt"
        if name == "B":
            # P1 机制块（2026-10-13）：B 双通道（manual.txt:394-400 ORDERS/Return
            # to Base 为通用令）——地面选区=地面 RTB（到场退款≥20%，toast 报备）；
            # 飞机选区=AirRTBCmd（B-22 不可逆既有）。两通道并存时各自发令。
            if cmd is not None and sel:
                cmd.ground_rtb(sel)
                self.notify("地面 RTB 已下——快移出生点，到场按损伤/耗弹退款（≥20%）")
            if cmd is not None and sel_air:
                cmd.air_rtb(sel_air)
                self.notify("RTB 返航令已下（不可逆——弹药余量结算见回收）")
            if not (sel or sel_air):
                self.notify("先选中单位或飞机", tone="error")
            return "rtb"
        if name == "J":
            self._air_engage_toggle(cmd)
            return "air_engage"
        if name == "Y":
            if cmd is not None and sel_air:
                cmd.air_disengage(sel_air)
            elif not sel_air:
                self.notify("先选中飞机（点地图上的飞机或右侧在空面板）",
                            tone="error")
            return "air_disengage"
        # ── P0 键位纠偏块（2026-10-13）：U 双击=就地立即卸载（手册 HOTKEYS
        #    「U Unload … (Press U twice to unload immediately)」manual.txt:566-
        #    568）——首按=待令（点地/点楼既有语义），待令中再按=cmd.unload(sel)
        #    无 cm 无楼＝仅 DismountCmd 原地旁落，清待令返 "unload_now"。──
        if name == "U" and self.armed_order == "unload" and sel:
            if cmd is not None:
                cmd.unload(sel)                    # cm=None：就地立即卸载
            self.clear_order()
            return "unload_now"
        self.arm_order(_ARM_BY_KEY[name])
        return "arm:" + _ARM_BY_KEY[name]

    # ── 待令执行（两段式第二段：左键确认——语义层，窗口层只做命中翻译）──

    def execute_armed_ground(self, cm, cmd, *, shift: bool = False) -> bool:
        """待令+点地：Q=攻击移动/R=倒车/T=炮击/K=空袭/O=空投/F=行军/U=卸载。
        返回是否消费该点击（待令在册即消费；引擎门拒绝=toast 反馈，待令保留）。
        P0 键位纠偏块（2026-10-13）+shift：手册 SHIFT=Queue orders（manual.txt:
        551）——待令态 Shift+确认=命令入队排队且**不清待令**（连续下令排队执行
        ；覆盖移动/攻击移动/行军/卸载/炮击五支；reverse 无引擎排队位不入队——
        ReverseCmd 归一化恒 queue=FALSE，留痕）。非 Shift=即发清待令（旧行为）。
        """
        group = self.armed_order
        if group is None:
            return False
        sel = list(self._command_targets(shift=shift))   # P1：TAB 焦点过滤
        if group == "attack":
            if cmd is not None and sel:
                cmd.move(sel, cm, mode="ATTACK", queue=shift)  # Q+点地=攻击移动（A6）
            if not shift:
                self.clear_order()
            return True
        if group == "march":
            if cmd is not None and sel:
                cmd.move(sel, cm, mode="MARCH", queue=shift)   # F+点地=行军（§6）
            if not shift:
                self.clear_order()
            return True
        if group == "reverse":
            if cmd is not None and sel:
                cmd.reverse(sel, cm)
            self.clear_order()                    # reverse 无排队位（见头注留痕）
            return True
        if group == "unload":
            if cmd is not None and sel:
                cmd.unload(sel, cm, queue=shift)  # U+点地=卸载+开进（§6）
            if not shift:
                self.clear_order()
            return True
        if group == "fire_mission":
            kwargs = self.fm_kwargs()
            for uid in self._fire_carriers(sel):
                if cmd is not None and cmd.fire_mission(uid, cm, queue=shift,
                                                        **kwargs):
                    if not shift:
                        self.clear_order()
                    return True
            self.notify("选中单位无曲射火力，炮击被拒", tone="error")
            return True                                 # 消费点击，待令保留
        if group == "precision":
            # P1（manual.txt:528-532）：P+点地=靠近激光位的精确弹药任务（Shift 可
            # 排队——与炮击族同款 queue 位）。弹药位强制 PRECISION，其余参数走
            # 炮击参数态；无激光位在吸附判距内=引擎门拒（toast 反馈）。
            kwargs = dict(self.fm_kwargs())
            kwargs["ammo"] = "PRECISION"
            for uid in self._fire_carriers(sel):
                if cmd is not None and cmd.fire_mission(uid, cm, queue=shift,
                                                        **kwargs):
                    if not shift:
                        self.clear_order()
                    return True
            self.notify("选中单位无曲射火力或附近无本队激光位", tone="error")
            return True                                 # 消费点击，待令保留
        if group == "strike":
            targets = self._strike_targets(cmd)
            if not targets:
                return True                             # toast 已发，待令保留
            for aid, weapon in targets:
                if cmd is not None:
                    cmd.air_strike(aid, cm, weapon=weapon)
            self.clear_order()          # 飞机无单位级队列——空袭族不入队（留痕）
            return True
        if group == "drop":
            aid = self._drop_target(cmd)
            if aid is None:
                return True
            if cmd is not None:
                cmd.air_airdrop(aid, cm)
            self.clear_order()          # 空投族同上：飞机令不排队（单击点投支）
            return True
        return False

    def execute_armed_drop_area(self, p0, p1, cmd) -> bool:
        """O 待令+拖拽画区（P0 键位纠偏块 2026-10-13：按住左键拖拽画矩形区，
        与 T/K 画线态同构——窗口层 _line 拖拽态+fm_panel 收笔分派）。投放点=
        矩形区心（AirAirdropCmd 仅点 API——区投=区心单点，区域语义留给后续
        多点撒投扩展，留痕）。短拖/单击回落 execute_armed_ground 点投。"""
        if self.armed_order != "drop":
            return False
        aid = self._drop_target(cmd)
        if aid is None:
            return True                                 # toast 已发，待令保留
        x0, x1 = sorted((int(p0[0]), int(p1[0])))
        y0, y1 = sorted((int(p0[1]), int(p1[1])))
        center = ((x0 + x1) // 2, (y0 + y1) // 2)
        if cmd is not None:
            cmd.air_airdrop(aid, center)
        self.notify("空投区 %d×%d m——投点取区心"
                    % ((x1 - x0) // 100, (y1 - y0) // 100))
        self.clear_order()
        return True

    def execute_armed_fm_line(self, p0, p1, cmd, *, shift: bool = False) -> bool:
        """待令+拖拽画线（LINE/CREEP 弹幕——GP-01 §3 表行 2/3 UI 拖拽画线；
        shift=排队不清待令，同 execute_armed_ground）。"""
        if self.armed_order != "fire_mission":
            return False
        line = ((int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1])))
        kwargs = self.fm_kwargs()
        for uid in self._fire_carriers(self._command_targets(shift=shift)):
            if cmd is not None and cmd.fire_mission(uid, line, queue=shift,
                                                    **kwargs):
                if not shift:
                    self.clear_order()
                return True
        self.notify("选中单位无曲射火力，炮击被拒", tone="error")
        return True

    def execute_armed_strike_line(self, p0, p1, cmd) -> bool:
        """待令+拖拽画线（K 空袭攻击轴——GP-01 §4 ③段评审②补：axis=(起点,终点)
        位置+朝向，target=线起点）。"""
        if self.armed_order != "strike":
            return False
        targets = self._strike_targets(cmd)
        if not targets:
            return True
        axis = ((int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1])))
        for aid, weapon in targets:
            if cmd is not None:
                cmd.air_strike(aid, (int(p0[0]), int(p0[1])), weapon=weapon,
                               axis=axis)
        self.clear_order()
        return True

    def execute_armed_unit(self, uid: int, cmd, *, enemy: bool,
                           shift: bool = False) -> bool:
        """待令+点单位：Q+点敌=选中全员齐射（逐单位 cmd.attack——trail 每单位一条，
        A5；shift=齐射入队排队不清待令——P0 键位纠偏块，手册 SHIFT=Queue orders）；
        Q+点己方=无效操作（待令保留+toast）；N+点敌=激光照射（P1——manual.txt:
        517-522）；L+点敌=狙击观测（§6，原 N 挪键留痕）；M+点己方载具=登车
        （P1——basics:181-193，复用 supply 同款点己方交互）；supply+点己方卡车=
        补给停靠（§6 车载制映射）。其余待令组点单位按地面处理。

        TAB 焦点过滤（P1，basics:59-60）：非 Shift 时焦点单位在选区内=仅对焦点
        单位下令（选区保留不散）。

        己方分支语义双轨备案（终审小项）：窗口层不达此分支——shell_window.
        _left_click_map 把 Q+点己方翻译成 execute_armed_ground(该单位位)=对
        该位置攻击移动（已定 UX）；本分支是语义层不变量护栏（防直调方把己方
        uid 当齐射目标误开火，tests/test_shell_interaction.py 直接驱动验证），
        非意外死码，与窗口路径并存为「引擎门之上的双保险」。"""
        group = self.armed_order
        if group is None:
            return False
        sel = list(self._command_targets(shift=shift))   # P1：TAB 焦点过滤
        if group == "attack":
            if not enemy:
                self.notify("攻击需要敌方目标（点地=攻击移动）", tone="error")
                return True
            fired = 0
            for sid in sel:
                if cmd is not None and cmd.attack(sid, uid, queue=shift):
                    fired += 1
            if fired and not shift:
                self.clear_order()
            return True
        if group == "laser":
            if not enemy:
                self.notify("激光照射需要敌方目标（N——manual 照射键）", tone="error")
                return True
            if cmd is not None and sel:
                cmd.laser_designate(sel, uid)
            self.clear_order()
            return True
        if group == "sniper":
            if not enemy:
                self.notify("狙击观测需要敌方目标", tone="error")
                return True
            if cmd is not None and sel:
                cmd.sniper_cover(sel, uid)
            self.clear_order()
            return True
        if group == "supply":
            if enemy:
                self.notify("补给停靠需点己方补给卡车", tone="error")
                return True
            if cmd is not None and sel:
                cmd.supply_dock(sel, uid)
            self.clear_order()
            return True
        if group == "mount":
            if enemy:
                self.notify("登车需点己方载具（M）", tone="error")
                return True
            if cmd is not None and sel:
                cmd.mount(sel, uid)
            self.clear_order()
            return True
        return False

    # ── 内部：命令构造辅助（读帧 dict，不碰 World）──

    def _command_targets(self, *, shift: bool = False) -> tuple[int, ...]:
        """TAB 焦点过滤后的地面下令面（P1 机制块 2026-10-13——basics:59-60
        「press TAB to give orders only to one unit without losing your
        selection」）：TAB 按过（_tab_focus_armed）且焦点单位在选区内且非 Shift
        （排队/追加语义走全选区）时仅对焦点单位下令；选区保留不散（不清
        selected——「without losing」字面）。未按 TAB/焦点不在地面选区（焦点在
        飞机通道）=全选区。"""
        sel = tuple(self.selected)
        if not shift and self._tab_focus_armed:
            focus = self.focus_unit
            if focus is not None and focus in sel:
                return (focus,)
        return sel

    def _fire_carriers(self, sel=None) -> list[int]:
        """炮击载体候选：选区内（焦点优先；空选区=全部己方）——资格由
        cmd_bus.fire_mission 的 mode_set 门裁决（引擎门权威，UI 不预判）。
        〔P1：sel 形参=TAB 焦点过滤面透传（_command_targets）；缺省=旧行为。〕"""
        sel = list(self.selected) if sel is None else list(sel)
        if sel:
            focus = self.focus_unit
            if focus is not None and focus in sel:
                sel.remove(focus)
                sel.insert(0, focus)
            return sel
        return self._own_ids()

    def _air_entry(self, aid: int) -> dict | None:
        if self.frame is None:
            return None
        return next((a for a in self.frame.get("aircraft", ())
                     if a["id"] == aid), None)

    def _strike_targets(self, cmd) -> list[tuple[int, str]]:
        """空袭目标机清单：空选区优先（逐机按帧内弹舱选 BOMB/STRAFE）；无空选区
        =_first_aircraft 兜底代选（toast 说明代选对象——§4 ③段 O/K 兜底口径）。"""
        if self.selected_air:
            out = []
            for aid in self.selected_air:
                entry = self._air_entry(aid)
                if entry is None:
                    continue
                out.append((aid, self._air_weapon(entry)))
            return out
        aid = self._first_aircraft(bomber=True)
        if aid is None:
            self.notify("无在空飞机，请先经底栏空呼", tone="error")
            return []
        entry = self._air_entry(aid) or {}
        self.notify("无空选区——已代选 #%d %s 下空袭令"
                    % (aid, entry.get("name", "")))
        return [(aid, self._air_weapon(entry))]

    @staticmethod
    def _air_weapon(entry: dict) -> str:
        """逐机武器档：有炸弹用 BOMB、有扫射弹用 STRAFE，皆无默认 BOMB
        （引擎弹药门拒并经 rejection toast 反馈）。"""
        ammo = entry.get("ammo") or {}
        if ammo.get("BOMB", 0) > 0:
            return "BOMB"
        if ammo.get("STRAFE", 0) > 0:
            return "STRAFE"
        return "BOMB"

    def _drop_target(self, cmd) -> int | None:
        """空投目标机：空选区中首个载伞机；无空选区=_first_aircraft 兜底
        （toast 说明代选对象——§4 ③段 K/O 兜底同口径）。"""
        if self.selected_air:
            for aid in self.selected_air:
                entry = self._air_entry(aid)
                if entry is not None and entry.get("paratroop") is not None:
                    return aid
            self.notify("选中飞机未载伞兵（呼运输机装伞兵后再投）", tone="error")
            return None
        aid = self._first_aircraft(bomber=False)
        if aid is None:
            self.notify("无在空飞机，请先经底栏空呼", tone="error")
        else:
            entry = self._air_entry(aid) or {}
            self.notify("无空选区——已代选 #%d %s 投放"
                        % (aid, entry.get("name", "")))
        return aid

    def _first_aircraft(self, *, bomber: bool) -> int | None:
        """在空飞机首选（兜底代选）：空袭=首个带 BOMB 弹在空我方机（patrol/
        inbound）；空投=首个载伞运输机。帧 dict 数据源（aircraft[].ammo/
        paratroop）。"""
        if self.frame is None:
            return None
        view = self.frame.get("view")
        for a in self.frame.get("aircraft", ()):
            if a.get("team") != view:
                continue
            if bomber:
                if (a.get("ammo", {}).get("BOMB", 0) > 0
                        and a.get("state") in ("patrol", "inbound")):
                    return a["id"]
            elif a.get("paratroop") is not None:
                return a["id"]
        return None

    def _air_alt_toggle(self, cmd) -> None:
        """V 高度两态 toggle（P1 机制块 2026-10-13：manual.txt:426「Press V to
        reduce altitude. Press V again to regain altitude」——LOW ⇄ 出场层；出场层
        按角色（战斗机 HIGH/其余 MID——air.entry_tier，引擎侧承载），UI 侧按帧
        alt_tier 判向：LOW→ALT_REGAIN、非 LOW→ALT_LOW。原三档循环退役留痕。"""
        if cmd is None:
            return
        if not self.selected_air:
            self.notify("先选中飞机（点地图上的飞机或右侧在空面板）", tone="error")
            return
        for aid in self.selected_air:
            entry = self._air_entry(aid)
            current = (entry or {}).get("alt_tier", "mid").upper()
            nxt = ALT_REGAIN if current == "LOW" else ALT_LOW
            cmd.air_alt([aid], nxt)

    def _air_afterburner_toggle(self, cmd) -> None:
        """Z 飞机加力 toggle（P1——manual.txt:496-497「Press Z again to turn it
        off」；按帧 afterburner 位取反，无资格机型引擎门拒）。"""
        if cmd is None:
            return
        if not self.selected_air:
            self.notify("先选中飞机（点地图上的飞机或右侧在空面板）", tone="error")
            return
        for aid in self.selected_air:
            entry = self._air_entry(aid) or {}
            cmd.air_afterburner([aid], not entry.get("afterburner", False))

    def _ground_z_dispatch(self, cmd, sel) -> None:
        """Z 地面分流（P1）：帧内 radar_on 可见=对空资格单位 → 雷达开关取反
        （manual.txt:534-539）；其余 → 冲刺（manual.txt:487-490）。雷达资格判定
        UI 侧不预判（引擎 _aa_eligible 门权威）——按「已开着→关、没开但曾在帧
        见过 radar 键→开」不可行，改双发：对空资格门拒即静默（雷达令 REJECT 计
        拒绝统计）。简化口径：选区内任一单位帧 radar_on=True → 全选区下雷达关；
        否则全选区下雷达开+冲刺各发（雷达令对无资格单位被引擎拒——toast 可见）。
        〔留痕：混合编队下 Z 以雷达优先，冲刺面走 G 组合/S 面板补。〕"""
        if cmd is None or not sel:
            return
        any_radar = any(
            (u or {}).get("radar_on")
            for uid in sel
            for u in [next((x for x in (self.frame or {}).get("units", ())
                            if x["id"] == uid), None)])
        if any_radar:
            cmd.radar(sel, False)
            self.notify("雷达关（即刻生效）")
        else:
            cmd.radar(sel, True)
            cmd.sprint(sel)
            self.notify("雷达开机（5s 启动）+冲刺——无对空资格单位两令按引擎门裁决")

    def _air_engage_toggle(self, cmd) -> None:
        """J 对空开关（逐机按帧内 engage_air 取反；None=无对空槽——跳过并提示，
        不下必拒令）。"""
        if cmd is None:
            return
        if not self.selected_air:
            self.notify("先选中飞机（点地图上的飞机或右侧在空面板）", tone="error")
            return
        no_slot = False
        for aid in self.selected_air:
            entry = self._air_entry(aid) or {}
            current = entry.get("engage_air")
            if current is None:
                no_slot = True
                continue
            cmd.air_engage_air([aid], not current)
        if no_slot:
            self.notify("部分机型无对空槽（J 只对战斗机/带对空武器机型生效）")

    def _toggle_stance(self, cmd) -> None:
        """H 交战纪律切换（weapons_free↔hold_fire——逐单位按帧内当前姿态取反）。"""
        if cmd is None or not self.selected or self.frame is None:
            return
        stance_by_id = {u["id"]: u.get("stance") for u in self.frame.get("units", ())}
        for uid in self.selected:
            current = stance_by_id.get(uid)
            cmd.stance([uid], "HOLD_FIRE" if current != "hold_fire"
                       else "WEAPONS_FREE")

    def _smoke_sprint_combo(self, cmd) -> None:
        """G 烟幕+冲刺+禁火一键（空选区=全己方便捷面——既有行为保留）。"""
        if cmd is None:
            return
        sel = list(self.selected) or self._own_ids()
        if sel:
            cmd.smoke_sprint_stance(sel)

    # ── 结算数据（结算页读帧 result 字段——不直读 World）──

    @property
    def result(self) -> dict | None:
        return None if self.frame is None else self.frame.get("result")
