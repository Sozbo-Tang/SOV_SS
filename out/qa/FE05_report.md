> 2026-10-17 勘误：§五 目检结论以 out/qa/FE05_audit.md 为准，原文保留。

# FE-05 断箭 HUD 复刻轮 · 总验收报告

日期：2026-10-17 ｜ 执行：界面复刻总工程师（ZCode）｜ 分支：main（未提交——按硬约束 3）

## 一、逐块状态

| 块 | 状态 | 说明 |
|---|---|---|
| F0 资产基建 | ✅ 已落地 | 索引/加载面/九宫格原语/QA 工具齐；画面零变化 |
| F1 单位贴图 | ✅ 已落地 | 帧加 template_id（加键不 bump）；67+10 全映射；缺图字形回退 |
| F2 断箭铭牌 | ✅ 已落地 | 下尖五边形/血条/人数/角标≤4/三档缩放/选中三角 |
| F3 单位详细卡 | ✅ 已落地 | session.unit_detail 按需查询；320×236 右下卡；与空中卡互斥 |
| F4 命令图标 | ✅ 已落地 | 39 键贴图化 32px＋cmd_tile 四态九宫格；禁用灰 alpha 90 |
| F5 卡面缩略图 | ✅ 已落地 | 呼援轨 20px/部署 24px/编辑器 40px＋card_frame 六类；config 主按钮 btn_primary |
| F6 ALT 视线+遮拦红显 | ✅ 已落地 | los_probe 四例判定＋ALT 叠层＋fm 预览「遮拦」红显＋los.png＋登记面翻面 |
| F7 断箭主菜单 | ✅ 已落地 | menu 页四页签＋menu.png＋交互缺省自主菜单（--start config 跳过） |
| F8 皮肤统一 | ✅ 已落地 | 九宫格全面换皮（顶栏/chip/面板/按钮五态/编组/小地图底图+框/结算三件/设置行+键帽/整页背景）＋上下文绘制光标 |

## 二、改动文件

**sovs/sim**（仅 F1 一处，加键不 bump）：`state_frame.py`（_unit_entry +"template_id"）

**sovs/app**：`session.py`（+unit_detail / +los_probe）、`qa.py`（interactive+start）、`screenshot.py`（+menu.png/+los.png）

**sovs/ui**：`assets.py`（新：索引消费/加载回退/九宫格/皮肤填充/按钮皮肤）、`unit_render.py`（新）、`nameplate.py`（新）、`unit_card.py`（新）、`los_overlay.py`（新）、`menu_page.py`（新）、`cursor.py`（新）；改 `palette.py`（铭牌配色/量尺）、`glyphs.py`（未改）、`scene.py`（单位/飞机循环改调新函数+fm 预览遮拦钩）、`hud_top.py`（顶栏/chip/结算皮肤）、`hud_bottom.py`（按钮皮肤/缩略图卡/轨底/部署面板/编组槽）、`selection_panel.py`（互斥接入+两卡皮肤）、`fm_panel.py`（参数条皮肤）、`minimap.py`（地形底图+外框）、`order_icons.py`（贴图化）、`deck_editor_page.py`（卡池缩略图/背景/主按钮）、`settings_page.py`（行底+键帽+背景）、`shell_window.py`（menu/ALT/光标接线）、`shell_fsm.py`（menu 页/迁移/键门）

**tools**：`build_asset_index.py`（新）、`qa_visual.py`（新）、`skirmish_shell.py`（--start）

**数据产物**：`data/gen/asset_index.json`（units 67/air 10/orders 39/ui 66/unit_mark 5/missing=0）

**测试**：`test_arch_constraints.py`（+7 模块登记）、`test_manual_conformance.py`（ALT 翻面 done＋计数 66〔40/5/20/1〕）；新增 `test_ui_assets.py`(7)/`test_unit_art.py`(6)/`test_nameplate.py`(6)/`test_unit_detail.py`(4)/`test_unit_card.py`(5)/`test_order_icons_art.py`(6)/`test_card_art.py`(5)/`test_los_overlay.py`(8)/`test_menu_page.py`(8)/`test_skin.py`(8)；`test_skirmish_shell.py`（CLI 断言随 +start 演进）

**文档**：`docs/GP-02-手册符合性总表-v1.md`（#59 翻面＋摘要行同步）

## 三、门禁实测值

- 全量：`1569 passed, 1580 warnings in 49.88s`（基线 1506＋新增 63）
- 架构守卫：`python3 -m pytest tests/test_arch_constraints.py -q` → `3 passed`
- 截图门禁：`python3 tools/skirmish_shell.py --screenshot out/qa/` → **9 张**（7 基线页＋menu.png＋los.png）全 ✓ 1280×800 非空
- 基线快照：`out/qa_fe05_baseline/`（F0 前向量量 UI）

## 四、diff 实测（tools/qa_visual.py，vs F0 基线，tol=8）

| 区块 | 图 | 区域 | 实测 | 阈值 | 判 |
|---|---|---|---|---|---|
| F1 单位区 | battle.png | (560,380,860,700) | **0.8531** | ≥0.02 | PASS |
| F4 命令格 | battle.png | (940,550,1270,790) | **0.5323** | ≥0.05 | PASS |
| F5 部署轨 | deploy.png | (8,100,230,400) | **0.9797** | ≥0.01 | PASS |
| F5 编辑器池 | deck_edit.png | (80,70,145,420) | **0.9732** | ≥0.01 | PASS |
| F8 config | 全帧 | — | 0.2260 | ≥0.01 | PASS |
| F8 deck_edit | 全帧 | — | 0.6042 | ≥0.01 | PASS |
| F8 deck_edit_over | 全帧 | — | 0.6121 | ≥0.01 | PASS |
| F8 deploy | 全帧 | — | 0.3545 | ≥0.01 | PASS |
| F8 battle_empty | 全帧 | — | 0.5473 | ≥0.01 | PASS |
| F8 battle | 全帧 | — | 0.6610 | ≥0.01 | PASS |
| F8 result | 全帧 | — | 0.0548 | ≥0.01 | PASS |

## 五、人工目检 8 条

1. **顶栏分区**：像。panel_topbar 皮肤打底；左上空援点数（黄大字）＋相位徽标；中央 chip_timer 计时＋双方点数镜像＋占点 pips；右冷却流。差：chip 边角比断箭更方。
2. **左缘呼援轨**：像。页签行＋呼XX机×N弹卡带机型缩略图＋地面卡 20px 缩略图＋rail_bg 底。差：地面卡缩略图为 20px 偏小（规格值）。
3. **右下命令格**：像。cmd_tile 九宫格底砖＋32px 贴图图标＋右下热键角＋行分隔＋待令提示行。差：图标为深色剪影风（美术资产即此风格），断箭原图标更亮。
4. **右下选中集群**：像。垂直三件（命令格→摘要行+12→状态主卡+12）、底中无面板；本帧为地面选区→单位详细卡（标题/HP/装甲/视野/速度·隐蔽/武器表/状态行），与空中卡互斥验证通过。差：武器表列宽较紧。
5. **单位贴图与队色**：像。48px 逐卡俯视贴图＋54px 队色衬（红/蓝 tint）＋overlay＋上缘 hp_bar。差：地面单位美术高留白（白/灰剪影），远看偏淡。
6. **铭牌五要素**：像。下尖五边形半透明黑底＋队色描边＋40×3 血条＋人数（16/16）＋状态角标（实测含 驻/牵 等，截 4）；选中态描边+三角。差：角标字母为单汉字小字号。
7. **左下小地图+1..9 编组列**：像。minimap_terrain 按比例裁切底图＋视口框＋右侧 1..9 编组槽（group_slot 皮肤＋活数角标）。差：外框 minimap_frame 铺 +4px 边（无框资产回退线）。
8. **主菜单四页签**：像。bg_mainmenu 整页背景＋左列 HOME/PLAY/ARSENAL/SETTINGS＋btn_primary 主按钮＋灰显只 toast（多人→「单人版本未开放」）。差：ARSENAL 双语标签在 210px 页签内偏挤。

## 六、过程异常与处置（留痕）

1. **WindowServer 瞬断**（合盖类环境问题，screens=0）：F4-F7 期间两轮截图门禁 IndexError、GL 测试类 32 条 skip——显示恢复后全部补跑实绿；期间产出的个别快照（22:23 deploy 无轨缩略图、22:41 battle 单位缺席）经重跑+逐位对照（单位框色数 338=探针 338）确认是一次性渲染残片，最终工件全部健康。
2. **跨窗 NinePatchTexture 缓存**：多测试类开关窗后 GL_INVALID_VALUE(0x1281)——NinePatch 持创建窗 GL 上下文对象，缓存键加窗口维度后修复（tests/test_skirmish_shell 截图门恢复绿）。
3. **Mimosa 路径门禁**：build_asset_index 的 open() 写法两拦，pathlib+数据键白名单校验版通过。
4. **pyglet ImageMouseCursor 无头段错误**（exit 139）——光标走规格允许的「绘制替代」（arcade 无公开光标 API 留痕于 cursor.py 头注）。

## 七、未覆盖项 / 保留

- **F6 登记面**：已干净完成（ALT deferred→done、负锚转正锚、GP-02 #59 同步）——无保留。
- **cursor 绘制替代**：交互模式下系统光标隐藏+绘制替代；若后续 arcade 暴露原生光标 API 可切换（代码已按 kind 收口单点）。
- **btn hover/pressed 两态**未接线（Btn 无悬停跟踪面——现存交互无此态），皮肤资产在库待未来消费。
- **viewer 窗**（观战器）未换皮——FE-05 范围为可玩壳 HUD；观战器贴图接线（assets/fe/viewer/）留待后续轮。
- **弹道遮拦红显**保持 deferred（引擎级门未做；预览级已落 los_overlay.annotate_fm_block——登记条目注记已更新）。
- 命令格图标色调/铭牌角标字感与断箭实机的细差——美术资产口径，代码侧无偏差。

## 八、复验入口

```bash
python3 tools/build_asset_index.py        # units=67 air=10 orders=39 ui=66 missing=0
python3 -m pytest -q                      # 1569 passed
python3 -m pytest tests/test_arch_constraints.py -q
python3 tools/skirmish_shell.py --screenshot out/qa/   # 9 张全 ✓
python3 - <<'EOF'                         # diff 复测
import sys; sys.path.insert(0,'.')
from tools.qa_visual import diff_ratio
print(diff_ratio('out/qa/battle.png','out/qa_fe05_baseline/battle.png',(560,380,860,700)))
EOF
```
