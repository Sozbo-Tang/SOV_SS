"""观战器色板（FE-T06）：队伍色/兵种六类色/相位色/底色——零图片资源的程序化
绘制配色唯一事实源（glyphs.py/viewer_window.py 消费；本模块纯常量零依赖）。

纪律：本阶段零图片资源——一切视觉元素程序化绘制（形状/纯色/线框）。未来贴图
槽位以 TEXTURE_SLOTS 常量占位标注（值恒 None——贴图引入时改此处并同步美术
清单，禁止散落硬编码路径）。

色板口径：
- 队伍色——GDD 通用军演惯例：team0=红方、team1=蓝方（与 record_golden.py
  录制标签 KevPlayer(0,…,label="red")/KevPlayer(1,…,label="blue") 对齐）；
- 兵种六类色——对齐 GDD-01 兵种表六类（侦察/步兵/装甲/火支/防空后勤/指挥；
  文档未定色值，此处为观战 v1 程序化配色占位，美术清单立项时钉死终值）。
  注意 category 字段仅五码（0~4，见 state_frame._unit_entry），指挥班组识别
  走 card_key/标志位联合键——帧 v1 未携带该位（已知缺口，美术需求文档立项
  时钉死），故 COMMAND 色暂无消费者、先行占位。
- 相位色——盲部署=暗黄（信息最少）、实战=橙红（交锋）、结算=灰蓝（收官）。
"""
from __future__ import annotations

# ── 队伍色（RGBA；观战器/UI 全层唯一口径）──
TEAM_COLORS: dict[int, tuple[int, int, int, int]] = {
    0: (214, 64, 64, 255),    # 红方 team0
    1: (72, 118, 214, 255),   # 蓝方 team1
}
TEAM_NAMES: dict[int, str] = {0: "RED", 1: "BLUE"}
UNOWNED_COLOR: tuple[int, int, int, int] = (150, 150, 150, 255)   # 无主占点/中立

# ── 兵种六类色（category 码 → 色；GDD-01 六类口径，观战 v1 占位值）──
CATEGORY_COLORS: dict[int, tuple[int, int, int, int]] = {
    0: (240, 216, 96, 255),   # 侦察——亮黄（快、轻、先见）
    1: (168, 196, 124, 255),  # 步兵——橄榄绿
    2: (140, 156, 170, 255),  # 装甲——钢灰蓝
    3: (208, 128, 76, 255),   # 火力支援——橙
    4: (166, 132, 200, 255),  # 防空/后勤——紫灰
    5: (238, 238, 238, 255),  # 指挥——近白星标（帧 v1 无识别位，占位）
}

# ── 相位色（顶栏相位段着色）──
PHASE_COLORS: dict[str, tuple[int, int, int, int]] = {
    "deploy": (176, 148, 60, 255),   # 盲部署——暗黄
    "combat": (208, 96, 60, 255),    # 实战——橙红
    "settle": (96, 120, 150, 255),   # 结算——灰蓝
}

# ── 底图/HUD 色（§11 断箭式重排：面板改藏青夜色调——断箭实机深蓝半透明面板）──
BACKGROUND: tuple[int, int, int, int] = (26, 30, 26, 255)      # 旷野底色（v1 无地形瓦片）
GRID_LINE: tuple[int, int, int, int] = (44, 50, 44, 255)       # 100m 网格线
MAP_BORDER: tuple[int, int, int, int] = (90, 100, 90, 255)     # 图幅边框
HUD_PANEL: tuple[int, int, int, int] = (14, 18, 28, 228)       # 顶栏底板（断箭藏青半透明）
HUD_TEXT: tuple[int, int, int, int] = (232, 232, 224, 255)     # HUD 文本
TIMELINE_TRACK: tuple[int, int, int, int] = (58, 64, 58, 255)  # 时间轴槽
TIMELINE_FILL: tuple[int, int, int, int] = (120, 176, 120, 255)  # 已播进度
DEPLOY_BAND: tuple[int, int, int, int] = (150, 128, 60, 200)   # 时间轴盲部署段底色
SMOKE_FILL: tuple[int, int, int, int] = (200, 200, 200, 70)    # 烟区（半透明）
PROJECTILE: tuple[int, int, int, int] = (255, 240, 160, 255)   # 弹丸小点
HP_HIGH: tuple[int, int, int, int] = (110, 200, 110, 255)      # HP 条 >50%
HP_LOW: tuple[int, int, int, int] = (214, 96, 72, 255)         # HP 条 ≤50%
SUPPRESS_MARK: tuple[int, int, int, int] = (250, 150, 60, 255)  # 压制角标
AIR_OUTLINE_DASH: tuple[int, int, int, int] = (210, 210, 210, 160)  # 高度层虚线圈

# ── 未来贴图槽位（本阶段恒 None——零图片纪律；引入贴图时在此登记）──
# 例：TEXTURE_SLOTS["unit_infantry"] = "assets/units/infantry.png"
TEXTURE_SLOTS: dict[str, None] = {
    "unit_recon": None,
    "unit_infantry": None,
    "unit_armor": None,
    "unit_firesupport": None,
    "unit_aa_logistics": None,
    "unit_command": None,
    "aircraft": None,
    "objective": None,
    "terrain_tiles": None,
}

# ── FE-T07 可玩壳（shell_window）增量：选区/发令痕迹/按钮面板/小地图 ──
SELECT_BOX: tuple[int, int, int, int] = (255, 255, 255, 200)        # 框选矩形（白虚线感）
SELECT_MARK: tuple[int, int, int, int] = (255, 255, 255, 230)      # 选中单位角框
TRAIL_LINE: tuple[int, int, int, int] = (140, 220, 255, 220)       # 已下令痕迹（命令线）
TRAIL_MARK: tuple[int, int, int, int] = (90, 180, 230, 255)        # 痕迹落点标记
ORDER_PANEL: tuple[int, int, int, int] = (14, 18, 28, 228)         # 命令格/面板底板（藏青）
ORDER_ARMED: tuple[int, int, int, int] = (214, 170, 60, 255)       # 待令按钮高亮（橙黄）
ORDER_TEXT: tuple[int, int, int, int] = (236, 236, 228, 255)       # 按钮文字
MINIMAP_BG: tuple[int, int, int, int] = (12, 15, 24, 240)          # 小地图底（藏青）
MINIMAP_VIEW: tuple[int, int, int, int] = (255, 255, 255, 180)     # 小地图视口框
INFO_PANEL: tuple[int, int, int, int] = (10, 13, 22, 242)          # 单位浮层底板（近不透明）

# ── 交互重设计 v2 增量：命令标记分型 / toast 通道 / 编组栏 / 部署页锚点与幽灵 ──
ATTACK_MARK: tuple[int, int, int, int] = (255, 96, 96, 235)       # attack 命令标记（红）
FM_MARK: tuple[int, int, int, int] = (240, 160, 60, 235)          # fire_mission 弹幕区（橙）
AIR_MARK: tuple[int, int, int, int] = (240, 224, 96, 235)         # air 命令标记（黄）
SMOKE_MARK: tuple[int, int, int, int] = (120, 220, 130, 235)      # smoke 命令标记（绿）
TOAST_ERROR: tuple[int, int, int, int] = (255, 120, 120, 255)     # toast 红字（无效操作反馈）
TOAST_INFO: tuple[int, int, int, int] = (240, 240, 232, 255)      # toast 白字
GHOST_MARK: tuple[int, int, int, int] = (200, 210, 220, 90)       # 待出场幽灵（半透明）
ANCHOR_SECTOR: tuple[int, int, int, int] = (120, 150, 120, 60)    # 部署集结区扇区底色
GROUP_SLOT: tuple[int, int, int, int] = (58, 64, 58, 220)         # 编组栏槽底
GROUP_DEAD: tuple[int, int, int, int] = (70, 70, 70, 220)         # 编组全灭灰显
WARN_RED: tuple[int, int, int, int] = (255, 96, 96, 255)          # 裸奔警告/红字

# ── GP-01 §5.4 布局重排增量：参数条/飞机面板/编辑器页 ──
FM_PANEL_BG: tuple[int, int, int, int] = (14, 18, 28, 240)        # 炮击/空袭参数条底板
AIR_PANEL_BG: tuple[int, int, int, int] = (14, 18, 28, 235)       # 在空飞机面板底板
SEL_PANEL_BG: tuple[int, int, int, int] = (14, 18, 28, 228)       # 选中卡底板（藏青）
AIR_FOCUS_MARK: tuple[int, int, int, int] = (240, 224, 96, 255)   # 选中飞机角框（黄）
DECK_OK: tuple[int, int, int, int] = (120, 200, 120, 255)         # 编辑器校验绿
DECK_BAD: tuple[int, int, int, int] = (235, 100, 100, 255)        # 编辑器违规红

# ── 布局几何（GP-01 §5.2 拆分后跨模块共享的量尺——纯常量零依赖面）──
# §11 断箭式重排（实机参照 out/refs/ba_shot4.jpg＋手册 P18/P22）：无底栏大按钮带，
# 命令=右下浮动命令格（选中即现）；小地图左下＋编组列在旁；呼援=左缘竖轨；
# 选中卡左置；顶栏中央=大计时+双方点数+占点指示（P18"命令菜单位于屏幕右下"）。
TOP_H = 56               # 顶栏高（px——中央计时/点数块需要两行）
TOP_SEG_GAP = 18         # 顶栏段间距（px）
BOTTOM_H = 10            # 底缘镶边（px——旧四行带已拆除，仅存视口内缩量）
MARGIN = 10
LEFT_W = 264             # 部署页左侧卡组面板宽（px）
CAM_PAD = 20             # 相机适配余量（px）≥ 最大图元半径（飞机高层虚线圈 18）
MINIMAP_W, MINIMAP_H = 220, 150       # 小地图（断箭位：左下角，近方形）
SEL_PANEL_W = 216        # 选中卡宽（px——断箭位：左侧，小地图上方）
ORDER_GRID_BTN_W = 92    # 右下命令格按钮宽（px——短标签紧凑，断箭图标密度）
ORDER_GRID_BTN_H = 24    # 命令格按钮高（px）
ORDER_GRID_COLS = 5      # 命令格列数
RAIL_W = 216             # 左缘呼援轨宽（px——容纳「呼XX机×N弹（在空N）」全宽）
BTN_FONT = 12            # 按钮字号

