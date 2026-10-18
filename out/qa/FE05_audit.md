# FE-05 审计勘误（FE05_audit）

日期：2026-10-17 ｜ 性质：对 out/qa/FE05_report.md（上一轮交付报告，原文保留）的勘误与 R1 修复记录

## a) 原报告结论不成立的证据

FE-05 原报告 §五「人工目检 8 条：像」与 §三/§四「PASS」**不成立**——当时的
目检与 diff 验收都建立在**系统性错位的画面**上：

1. **根因**：`sovs/ui/assets.py::draw_nine_patch` 把输入 rect `(x0,y0,x1,y1)`
   直接展开传给 `arcade.LRBT`——而 `LRBT` 的参数序是
   **(left, right, bottom, top)**。错序后 `right=y0`、`bottom=x1`：对
   顶栏 (0,744,1280,800) 得到 left=0/right=744/bottom=1280/top=800 的
   **负高矩形**——九宫格面板（顶栏/命令格底砖/选中卡/主菜单按钮/整页
   换皮）整体错位、拉斜或出屏。battle/menu 页全屏受害（单位贴图走
   XYWH 不受此 bug 影响，但所有面板皮肤全错位）。
2. **复现对比**：`out/qa/fe05_audit/before_battle.png`（以参数序还原补丁
   在同一窗/同一帧复现原 bug）vs `after_battle.png`（修复后同帧）——
   before 中右下单位详细卡/命令格为斜置色块、顶栏缺失；after 全部归位。
   拼接对照图 `compare_battle.png`（左两块=before、右两块=after），
   两图全帧 diff=0.3784。
3. **diff 指标为何没抓住**：原验收断言「每页 vs F0 基线 diff ≥0.01」——
   错位画面相对基线变化更大，diff 反而更高（LRBT 修复后 deploy=0.0089、
   result=0.006 反而不过）。**diff 只证明"变化"，不证明"正确"**——
   该指标奖励坏得更多的画面，已在 R1 删除（见 c-1）。

## b) 三处审计修复（各一句）

- `sovs/ui/assets.py`：`draw_nine_patch` 两处 `arcade.LRBT` 改按
  **(x0, x1, y0, y1)** 正确参数序建矩形（九宫格与退化拉伸两路径）。
- `sovs/ui/minimap.py`：地形底图与外框两处 `LRBT` 同上改为正序。
- `sovs/ui/unit_render.py`：overlay 资产（12×12/12×8）不再拉成 48px——
  selected=四角 12px 角标、moving=底中箭头、suppressed=左上图标，均原尺寸。

## c) R1 修复记录（1-1～1-4）与测试增改

| # | 修复 | 改动文件 |
|---|---|---|
| 1-1 | 删 diff 验收 `test_every_page_diff_at_least_1pct`，改结构断言 | tests/test_skin.py |
| 1-2 | 编辑器缩略图行外压标题 → **行内左端 24×24**＋dk_add 行标签左对齐＋卡池行区 top-78→top-84（4px 净距） | sovs/ui/deck_editor_page.py |
| 1-3 | 单位详细卡：CARD_W 320→**340**（末列不裁）；HP 文本 y1-46→**y1-56**（与血条零重叠，hp_bar_rect/hp_text_rect 量尺）；武器表逐列 fit 列距-4；状态行 fit 收进卡宽 | sovs/ui/unit_card.py |
| 1-4 | 选中双重标记二选一：**删 scene 白框**，保留 unit_render 四角角标 | sovs/ui/scene.py |

**新增测试**（tests/test_skin.py）：
- `TestSkinStructure`（GL 实渲染、窗保活）：`test_a_seven_pages_nonempty_1280x800`
  / `test_b_topbar_skin_covers_over_5pct` / `test_c_order_grid_tile_base_over_20pct`
  / `test_d_minimap_structure`（视口框灰线断言基于实测像素 170..200）
  / `test_e_unit_card_column_width_contract`（每列 fit 后宽 ≤ 列距-4）。
- `TestNinePatchParamOrder::test_rect_width_height_forwarded`——
  `draw_nine_patch((10,20,210,120))` → Rect 宽=200/高=100、四边正序
  **（直接抓 LRBT 参数序根因）**。
- `TestSelectedOverlayKeepsAssetSize`：`test_selected_corner_marks_at_asset_size`
  （四角 4×(12,12)、本体唯一 (48,48)）/ `test_unselected_no_corner_marks`
  **（抓 overlay 拉伸回归）** / `test_scene_selection_white_box_removed`
  （源级锁：scene 不得再引 SELECT_MARK 白框）。
- tests/test_unit_card.py：`test_last_column_fits_card_width`、
  `test_hp_text_disjoint_from_bar`（＋320→340 同步）。
- tests/test_card_art.py：`test_deck_thumb_rect_geometry` 重写
  （行内 24×24＋与 pool_title_rect 零重叠）。

## d) 当前实跑（R1 收口）

- 窄组 1：`pytest tests/test_skin.py tests/test_unit_art.py tests/test_card_art.py -q`
  → `25 passed`（另 test_skin 单跑 15 passed 含源级锁）
- 窄组 2：`pytest tests/test_hud_geometry.py tests/test_shell_window.py -q`
  → `54 passed`
- 全量：`python3 -m pytest -q` → **0 failed**（数字见本次汇报正文）
- 截图：`python3 tools/skirmish_shell.py --screenshot out/qa/` → **9 张全 ✓**
- 9 张路径：`out/qa/{menu,config,deck_edit,deck_edit_over,deploy,battle_empty,battle,los,result}.png`
- 审计工件：`out/qa/fe05_audit/{before_battle,after_battle,compare_battle}.png`

## 仍需人眼确认项

1. 命令格深色剪影图标、单位高留白美术与断箭实机（ba_shot4）的整体观感差。
2. 铭牌 3×3 色块＋单汉字角标在 1080p 的可读性。
3. 主菜单 ARSENAL 双语标签在 210px 页签内的拥挤度。
4. 交互模式绘制光标（系统箭头隐藏＋贴图光标）的手感。
5. 空中 40px 贴图机头朝向与美术基准向一致性（facing 按 0°=北实现）。

---

## 2026-10-17 二次勘误（R2 视觉收口轮——上文原文保留）

a) **R1 §c 表 1-3 行「末列不裁」不成立**：实测弹种列仍显示 "SMO..."——
   根因是 R1 的 `test_e_unit_card_column_width_contract` 为**恒真断言**
   （先 `fit_text` 截断、再测截断结果的宽度 ≤ 列距-4——任何截断都能过），
   不能证明全文可容纳。R2 已改非恒真：`fit_text("SMOKE", span-4, 10)
   == "SMOKE"` 全文相等断言＋短 token（KE/HE/71/71/120）无「…」＋长卡名
   允许且必然截断；`_COL[4]` 282→**272**（末列 span 50→60，fit 后 56px），
   "SMOKE" 全文显示。

b) **compare_battle.png 描述纠正**：该图为**左右各取一帧半幅拼接**——
   左半（上下两块拼合）取自 before_battle.png 的左半幅、右半取自
   after_battle.png 的右半幅；原文「左两块=before、右两块=after」的表述
   有歧义，以本句为准。

c) **R2 1-1 铭牌阈值修复记录**：原 F2 分档 `zoom<0.06 只血条 / ≥0.12 才
   全量` 高出默认相机量尺 10~20 倍——战场默认 `scene.fit_scale≈0.006`
   （视口 ~1260px／地图 200000cm），铭牌在默认视角整体不显示（截图只有
   40×3 血条）。R2 分档改为 `≥0.0040 画铭牌＋血条／≥0.0050 画人数与
   角标／<0.0040 只血条`（`ZOOM_PLATE_MIN/ZOOM_DETAIL_MIN` 常量入
   nameplate.py）——默认 0.006 全量命中、`min_scale≈fit×0.8≈0.0048`
   下界仍见铭牌。测试面：test_zoom_tiers 按新分档翻新＋新增
   fit_scale/min_scale 实算断言＋TestSkinStructure
   `test_f_nameplate_pixels_at_default_zoom`（默认视角铭牌带像素 ≥30）。

---

## R3 收口（2026-10-18——上文原文保留）

1. **四件小修**：①铭牌人数改「hp/hp_max」（如 16/16，本局侦察排 16 人满编）
   且仅步兵挂数字——载具/火炮/防空/侦察车铭牌只留血条（nameplate.py
   count 门控＋unit_render state +category；缺 category 按步兵兼容）；
   ②选中摘要条瘦身 STRIP_H 64→44、STRIP_W 600→520（chip 40→26 高、
   字号 11→10、focus 框 2px→1px；与命令格 12px 缝不变）；
   ③卡组行纯色路径描边 ORDER_TEXT→(90,100,90,160)（去白竖线刺眼）；
   ④双分辨率：screenshot()/interactive() +size 参数、CLI --size WxH。
2. **实跑**：全量 `python3 -m pytest -q` → 0 failed（数字见本轮汇报）；
   窄组 nameplate/hud_geometry/skin 全绿；test_skirmish_shell CLI 断言随
   +size 参数演进（期望值同步，非弱化）。
3. **两套截图（各 9 张）**：
   - 1280×800：`out/qa/{menu,config,deck_edit,deck_edit_over,deploy,battle_empty,battle,los,result}.png`
   - 1600×900：`out/qa_1600/`（同名 9 张；A3=169/B3=551 护栏绿）
   - 1600×900 结构复核：顶栏 56/命令格右下/摘要条+状态卡右对齐集群/
     小地图左下+1..9 编组列/编辑器三栏——均无重叠溢出；fit_scale≈0.0077
     ≥0.0050，铭牌全量档命中。
4. **新增测试**：test_nameplate `test_count_only_for_infantry`/
   `test_count_text_hp_slash_hpmax`；test_hud_geometry 行高/行宽期望值
   44/520 同步；test_skin `TestSkinStructure1600`（九图存在/尺寸 1600×900/
   顶栏>5%/tile>20%）＋`_drive_fe05_pages` 共享驱动（1280 类复用，
   补 result.png 后 test_a 升为九图）＋`test_scene_selection_white_box_removed`
   （R1 保留）等全部在库。
5. **未覆盖项**：1600×900 仅结构断言（无逐区块像素基线）；cmd_tile 皮肤
   在 1600 下为同资产九宫格缩放（无 @2x 消费面——资产在库未接线，留待
   后续轮）；deck_edit 页脚校验红字与卡池面板底的叠放关系沿 1280 口径
   未动（非本轮范围）。

> 2026-10-18 R4.1 记录：page_fit 缩放下限 0.75→0.5＋窗口最小尺寸 960×600（等比锁测试在库——scale=min(w/1280,h/800) 禁非等比拉伸）；settings 页进截图门禁（config 后进出），1280/1600 两套各 **10 张**。

> 2026-10-18 R6 记录：目标点挪位（村 108000,64000 r6500／路口 100000,42000 r6000／农庄不动——间距>半径和断言入库）；config 胜利裁决行改「夺取三处要点」；tools/gen_terrain.py 落巴格拉季昂底图 2560×1280＋小地图 512×256（seed=sha256(map_key) 确定性、北=PNG 第 0 行）；接入=战场底图（500m 主网格 α50）＋建筑屋顶八座（含毁态）＋小地图地形化＋溪口木桥；hero 镜头入截图流（t2400 村中心 0.012）。过程中勘正三处：scenario_info 漏 map_key 键（底图整轮不绘的根因）、Armor 四面板取 front、溪流采样点校准。
