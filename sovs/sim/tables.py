"""§D.0 BalanceConfig：全部可调常数（对齐伪代码 v1.7；禁止在系统函数写死数值）。
v1.7（终检 GAP-07/19）：补 §D.0 五常数；terrain_speed_bp 增瓦片注入接口——
TERRAIN[tile] 表（Tiled→JSON）接入前为 stub：未注入瓦片时按移动类全局缺省值。"""
from __future__ import annotations

from dataclasses import dataclass

from .types import MovementClass


@dataclass(slots=True)
class BalanceConfig:
    # 移动（速度档 → cm/tick，10Hz）
    speed_table_cm_tick: tuple[int, ...] = (0, 25, 45, 70, 100, 140)
    road_bonus_cm_tick: int = 170
    sprint_duration_ticks: int = 100
    sprint_cooldown_ticks: int = 600   # ── 断箭补空占位（断箭移动机制映射_v1 §三.1；
                                       #    2026-10-04 设定数值块）：社区"约 60 秒"=600t
                                       #    低置信、官方仅 recharge 定性（调研联网核证 v1
                                       #    N22+§三未确证#6）。冷却门已接线（2026-10-07
                                       #    发起人拍板采纳，命令族收口块）：cmd_sprint 增
                                       #    now<sprint_until+cooldown→REJECT（sprint_until
                                       #    语义不变、契约⑧速度式不动；初值 0=从未冲刺
                                       #    哨兵豁免首冲）——「零消费者不接线」留痕就此
                                       #    收口，纯接线零新常数──
    # ── 2026-10-04 发起人拍板（断箭式，MV-B-03/MV-B-04 双改B——映射档 §四.2 冲突2）──
    pinned_move_mult_bp: int = 5000    # PINNED 可接受移动令但速度减半（判据缝
                                       # movement.pinned，GDD-05 士气槽落地前恒假=零行为差）
    sprint_suppress_cut_bp: int = 5000 # 冲刺开跑拍压制减半（断箭官方「Sprint can be
                                       # used defensively to break suppression」；≥10000 短路零效）
    tow_speed_tier: int = 1
    tow_follow_offset_cm: int = 300  # AMB-10 拍板：被拖元素跟随于牵引元素后方固定偏移
    water_speed_bp: int = 5000       # ── 断箭补空占位（断箭移动机制映射_v1 §三.2；
                                     #    2026-10-04 设定数值块）：两栖水上瓦片注入值=
                                     #    类级越野 bp×此值//10000（≈50%——断箭步兵水上
                                     #    9/越野 18 折算；两栖载具水上 km/h 未公布=
                                     #    未确证#10）。条件性条目仅随 MV-B-02 改B 生效
                                     #    （MovementClass 扩枚举/加两栖旗标——契约②不许
                                     #    旁路）；注入通道=terrain_speed_tile_bp 既有接口、
                                     #    寻路侧 bp 值天然走 tile_cost 既有定标。首版无
                                     #    水域——本表仅出占位值不接线（零消费者，不冒充）──

    # ── MOVEMENT_PSEUDOCODE_v1.2 §4 移动段新常数（6 字段全数出表——2026-10-06
    #    速度链块收口：批③ Formation 族块先行出表 reverse/formation×2 三字段，
    #    本块补出 crippled_threshold_bp/crippled_speed_mult_bp（§2.3 增量③）与
    #    auto_approach_standoff_cm（§2.11）；**删除登记 1 条**（§4：crit_mob_
    #    minor_mult_bp=5000——GAP-14 拆除 MOB 读取后零消费，随 D071 连锁一并
    #    删除，本块已执行**）── **删除登记再 +1 条（2026-10-07 D071 全拆）**：
    #    crit_per_hp_bp=1200（原交战段）随 roll_crit 整删一并删除——唯一消费者
    #    已拆、零消费死常数；恢复路径=重启暴击时随 roll_crit 一并出表（combat.py
    #    头部拆除留痕）──
    reverse_speed_bp: tuple[int, int, int, int] = (0, 2500, 3000, 0)
    # 倒车速度乘区（FOOT/WHEEL/TRACK/HORSE 序——GAP-03/MV-B-13）：FOOT/HORSE=0 且
    # issue_move 门 4 据此拒令（§2.2/§2.7——AMB-9）；速度乘区消费者（§2.3 增量②）
    # 已随速度链块 2026-10-06 接线（movement.move_speed_cm_tick 读 reverse_speed_bp
    # 求值函数——单位级覆盖>类级）
    crippled_threshold_bp: int = 2500   # 重伤阈值 HP≤25%（D068 字面——GAP-14；§4
                                        # 默认占位。边界含等号：hp×10000≤hp_max×此值）
    crippled_speed_mult_bp: int = 5000  # 重伤减速×0.5（D068「HP≤25%速度减半」——
                                        # GAP-14；替换 MOB MINOR 乘区原位（该乘区随
                                        # 拆除已删），判 ANY 元素=排级同速 MV-B-14）
    formation_line_spacing_cm: int = 1500   # 横队相邻元素间距/楔形横向半距×2（§2.8；数值章节定标）
    formation_column_spacing_cm: int = 1000  # 纵队/楔形纵深间距（§2.8；同上）
    auto_approach_standoff_cm: int = 2000    # 超射程自动进位的最大射程内侧余量（§2.11；
                                             # stand=MAX(max_range−此值, max_range//2)——AMB-4 半射程
                                             # 下界；2000cm 固定余量在 max_range≤196,000cm 时独立
                                             # 覆盖 DIR8 近似误差 ≈1.015%）

    # ── PB-51 原地转向速率（2026-10-04 拍板纳入——断箭 N17 neutral steering，映射 §五.9；
    #    推翻 MOVEMENT_PSEUDOCODE_v1.2 §2.13 reject 的静止分支，见 movement.pivot_step）──
    pivot_rate_deg_per_tick: tuple[int, int, int, int] = (10, 6, 8, 10)
    # 原地转向速率 deg/tick，FOOT/WHEEL/TRACK/HORSE 序（reverse_speed_bp 同序先例）。
    # 数值占位待数值章节定标：断箭证据低置信（N17 仅 Reddit 摘要「坦克普遍可原地转向」
    # 无数值）；量级锚=核证 v1 N15 Turn rate 两档 60/80（单位未标注、疑占位——按 deg/s
    # 读即 6/8 deg/tick），档序按拍板文本「履带快于轮式」对调指派（N15 原序轮 80>履 60
    # 系行进间转向口径，原地中性转向履带严格占优——拍板方向为准）；FOOT/HORSE=10 无据
    # 占位（步兵/骡马原地转身近似即时：180°=18t）。注意：射击侧 R-09 rotate_step 仍读
    # 逐卡 turn_rate_deg（AMB-5 换算）——两轨并存为已知分叉，统一轨待数值章节拍板
    # （填 CSV 逐卡值或 rotate_step 改读本表），登记见 tick.py TODO。

    # ── 寻路（MOVEMENT v1.2 §2.14 + 运行发起人 2026-10-02 裁定；算法=sovs/sim/pathfind.py）──
    pathfind_diag_cost_bp: int = 14142  # 对角步代价=入格 tile_cost×此值//10000（√2 整型
                                        # 近似）——§2.14 未规定，发起人裁定补定标（登记表）
    pathfind_cache_entries: int = 256   # find_path 结果 LRU 缓存上界（PB-10「缓存随消费侧
                                        # 接线再落」——2026-10-04 寻路接线块；性能常数非平衡值，
                                        # 0=禁用；键含地形内容指纹→地形突变天然失效）
    pathfind_max_expansions: int = 500000  # A* 单查询最大展开节点数保险丝（PB-58 拍板
                                        # 「限幅」——PB-50 前置门，2026-10-06 落地）：真实展开数
                                        # （done 集 增量）超此值即中止→直线兜底 RETURN [to]
                                        # （同 AMB-8/不可达口径），最坏单查询耗时上界≈此值×
                                        # 单展开成本（实测 ~7.6µs/展开——最劣档 327,342 次展开
                                        # 2.48s 折算；注：仅覆盖 A* 循环项，缓存未命中查询的
                                        # terrain_fingerprint/_min_step_cost 前置费用随瓦片数线性、
                                        # 不在 cap 内——PB-58 评审留痕）。0=不限幅（区别于 pathfind_cache_entries
                                        # 的 0=禁用——「展开 0 次」无意义）。占位来源：2026-10-06
                                        # 黑盒二分实测（经本常数二分最小成功 cap=精确展开数，
                                        # bench/pathfind_bench.py cap 模式可复跑 S3 锚）基准全部
                                        # 10 查询展开数——S1 档 max 12,204 / S2 档 max 51,072 /
                                        # S3 最劣档（1km 图 1000cm 网格=1e6 格）角到角 max
                                        # 327,342；取同量级（10^5 档）整洁上界 500,000（实测包络
                                        # 1.53× 余量）——已测档位零行为差、仅熔断超包络病态查询。
                                        # 备选未采留痕：勘察案 5 万~10 万（≈百毫秒上界）更紧但
                                        # 会熔断 S3 角到角查询（327,342>100k）改变基准已测行为；
                                        # 1e6（上跳一个量级）fuse 近失效——均待发起人/数值章节
                                        # 复核（性能常数非平衡值）

    # ── 地形数据（PB-58 块② 正式示范图数据管线，2026-10-06；消费=sovs/sim/map_loader.py）──
    ruin_speed_bp: int = 4000  # RUIN（村庄废墟）瓦片注入 speed_bp——四移动类同值，loader 侧
                               # 注入（gen JSON 只携带瓦片类型标记，改值无需重建数据——单一
                               # 权威在本表）。§2.14 语义 bp==0=不可通行：数值章节若拍板
                               # 废墟=实体屏障，置 0 即得（pathfind.py:7 口径天然承载）。
                               # 无据占位待数值章节定标（PB-58 ask「废墟/村庄=可通行减速率
                               # 占位（标注数值章节定标）」——勘察 decisionPoint (a)(b) 由
                               # ask 文本裁定为减速占位档）：4000bp=40% 速度；选值依据=使
                               # FOOT(8000)/TRACK(7000) 对成片废墟产生可观测绕行、全四类
                               # 均受抑（<WHEEL 缺省 5000——单值不可能只慢部分类），示范图
                               # 绕障行为可断言——性能/演示取向，非平衡定标。FOREST 不注入
                               # （§2.12 拍板：森林不减速只喂 sensing——map_loader 旁挂
                               # forest_tiles 集合承载，sensing 遮蔽通道已接〔2026-10-07
                               # 感知接线块：terrain_sensing_channels 装配 in_forest/
                               # forest_m 两 fn 喂 system_sensing/校射，见登记表〕)；
                               # ROAD 不注入（速度吃既有 MARCH 道路地板
                               # movement.py:84-89 与 prefer_road 减半 pathfind.py:127-128，
                               # 零造数）

    # 侦察（隐蔽 0..10 → 视野倍率 bp）
    stealth_factor_bp: tuple[int, ...] = (
        15000, 13500, 12000, 11000, 10500, 10000,
        9500, 9000, 8000, 6500, 5000,
    )
    forest_stealth_add_x10: int = 20       # ×10 整型存储（=+2.0 级）
    garrison_stealth_add_x10: int = 30     # =+3.0 级
    detect_atten_per_m: int = 150
    infiltration_mult_bp: int = 15000
    ambush_mult_bp: int = 20000
    reveal_mult_bp: int = 4000
    sensing_period_ticks: int = 5
    # ── 移动×感知三乘区出表（2026-10-04 断箭设定数值块·映射冲突3 裁决 B——发起人
    #    默认裁决可推翻）：行为/数值一律不变仅出表（原 sensing.py 硬编码 5000/20000/
    #    ÷2）。来源=MOVEMENT_PSEUDOCODE_v1.2 §7 MV-B-08 冻结值（契约⑳——D066 猎兵
    #    静默行军/侦察车免惩罚的前提乘区）；断箭官方 Detection 六条无移动项=本作自设
    #    严于断箭（Reddit 单源"越快越易被 spot"未证实、未确证#2 维持并存——留痕见
    #    tick.py 登记表）──
    stealth_move_mult_bp: int = 5000          # 移动隐蔽乘区（effective_stealth_x10：
                                              # moving → m×此值//10000）
    forest_walk_silent_mult_bp: int = 20000   # FOREST_WALK_SILENT 林中静默豁免乘区
                                              # （×2 抵回移动惩罚）
    move_vision_mult_bp: int = 5000           # 观察者移动视野乘区（detection_range_cm：
                                              # r×5000//10000 ≡ r//2 位级一致——r 恒
                                              # 非负整数域）

    # 交战
    melee_range_cm: int = 5000
    ambush_acc_bonus_bp: int = 13000
    calib_acc_bonus_bp: int = 12500
    calib_per_shot: int = 20            # 校射按发累积【拍板默认】（§D.0；GAP-07）
    calib_max_reduction_bp: int = 6000  # 校射最大散布收束（GAP-07）
    sup_penalty_bp: int = 6000
    sup_decay_per_tick: int = 1
    # ── 压制衰减裁处成轨（2026-10-07 数据定标块·发起人默认裁决=案 A 维持 10/s
    #    转正入数值总账 v1 §一，可推翻）：GDD-05 B2:127/B4:177 写 5/s 字面不采——
    #    ①整型纪律硬约束（5/s=0.5/tick 非整，须隔拍衰减/计数器复杂化）；②同源
    #    标尺不采自洽（同页 B4 的 0..150 标尺/50/100/150 阈值已随 PB-54 明示不采
    #    ——5/s 随同源规格一并不采；「断箭数值不直接迁移」P-120 先例）；③士气
    #    整局验收手推链全建立在 decay=1/tick（回落拍 626/645/715/1015/1016 序列）。
    #    SUPP_DECAY_X2 旗标档（近卫恢复加倍·方案18）= 本值×2=20/s 语义留痕 ──
    # crit_per_hp_bp=1200 已随 D071 全拆删除（2026-10-07——见上方移动段删除登记）
    front_arc: int = 45
    side_arc: int = 135

    # ── 士气状态机（GDD-00 D014 四态/D025 阈值制「数值待配」；GDD-05 下篇 B2:128/
    #    B4:176-183 updateMorale 同构——2026-10-04 士气块。全部占位待数值章节定标）──
    morale_sup_th: int = 40    # 受压阈值（单位级聚合压制=max 存活元素 suppression）
    morale_pin_th: int = 70    # 钉住阈值（PB-49：可动减速 pinned_move_mult_bp）
    morale_rout_th: int = 100  # 溃逃阈值。标尺口径：维持现元素压制 0..100 封顶
                               # （combat.inject_suppression）——GDD-05 B1:99/B4:178 的
                               # 单位级 0..150+ 与 50/100/150 需抬封顶并重标 sup_penalty_bp
                               # 连续消费链，未随本块采（勘察 decisionPoint 取最小改动档；
                               # D025 数值待配=三值全占位可调）。定标须知（2026-10-04
                               # 评审提示，数值章节定标时按此复核）：40/70/100 非 B4
                               # 50/100/150 的等比换算；rout_th=100 恰等于压制封顶——
                               # 仅新注入打满封顶可达、且同拍衰减先行（①system_timers
                               # 先于 ⑤.5 system_morale 判态，重整拍判定前已 −1），抬
                               # rout_th 须同步抬 inject 封顶，否则溃逃档不可达
    morale_rally_ticks: int = 300  # 溃逃→重整时长（D014 待定①处置：GDD-05 B4:182「30s」
                                   # 默认=300t@10Hz 占位；D014 待定③=D034 军官/政委光环
                                   # 加速随指挥单位块拍板实现形态——本常数为可乘基数，
                                   # aura_bonus_bp 连乘先例（combat.py）可直套，无架构锁死）
    # ── 士气效果（2026-10-04 士气效果接线块——D014「受压=命中/性能下降、钉住=火力
    #    大减」的命中侧乘区；D023 命中率式「×士气惩罚」项 + GDD-05 B4:149 moraleFactor
    #    按态乘区（受压×0.7/钉住×0.3）双锚。消费=combat.morale_acc_factor_bp →
    #    fire_direct acc 链（对空链不乘——依据=代码先例：fire_aa 本就窄于 fire_direct
    #    不乘 ambush/aura/self_defense + ⑦⑧ R-17 最小许可集先例；2026-10-04 评审
    #    遗留④改准，留痕 fire_aa docstring/登记表士气留待项⑫）。
    #    低置信占位待定标：断箭参考杠杆为「瞄准时间×2/×3」未采（ask 二选一取命中 bp
    #    档——双规格锚在此侧）；与元素压制连续项（aim_factor_bp/sup_penalty_bp）
    #    叠乘=双粒度记账（元素级=本元素光学/乘员抖动，单位级=指挥协同崩解），非双算 ──
    morale_acc_factor_sup_bp: int = 7000  # 受压命中×0.7（B4:149 字面值）
    morale_acc_factor_pin_bp: int = 3000  # 钉住命中×0.3（B4:149；D014「火力大减」承载）

    # 狙击 R-02
    sniper_base_prob_bp: int = 3000
    sniper_cover_mult_bp: int = 5000
    sniper_tally_kills: int = 3

    # 后勤（2026-10-03 拍板：弹药/医疗合并为一池按重量计的通用补给）
    med_weight_per_hp_g: int = 1         # 每 1 HP 治疗消耗补给重量 g（v1 定标 2026-10-03 拍板转正。
                                       # ⚠ 与 med_weight_per_unit_g 入/出池换算不对称（批③评审#1 留痕）：
                                       # 入池 5g/份 × 出池 1g/HP=满载医疗可治量较池化前双槽隐含膨胀 5×
                                       # （120 份×1HP=120HP vs 600g÷1g/HP=600HP）——两常数数值章节定标
                                       # 须一并裁；现役零卡置 HAS_SUPPLY 不可达）
    # ── PB-56 批③ buy_supplies 重量式两常数（2026-10-06；§D.0 :73-74 出表——勘察
    #    decisionPoints「负载与换算锚」案 c：双参作舱位门、写点换算入池）──
    supply_round_weight_g: int = 1       # §D.0 :74 supply_round_weight（弹药池通用每发重量，
                                         # D.0 标「待定」）——占位 1g/发：D012 满额互算
                                         # cargo_weight_max 600 ÷ cargo_rounds_max 600（GDD-02
                                         # v1.9:452「600发或120份按重量混装」两满额自洽）且与
                                         # per-weapon ammo_weight 数据占位 1g（types.py:238）
                                         # 同值——数值章节定标
    med_weight_per_unit_g: int = 5       # §D.0 :73 med_weight_per_unit=5（D065 混装载重核算；
                                       # ⚠ 出池侧见 med_weight_per_hp_g 注——入/出换算不对称两常数
                                       # 一并定标（批③评审#1）；
                                         # 600÷120 满额互算同值）——每份医疗品入池重量
    ammo_resupply_per_tick: int = 2      # 每拍每武器可转运发数（发数限速；重量只管池耗——
                                         # 重弹吃池快，转运节奏由本常数统一定）
    repair_radius_cm: int = 3000
    vehicle_death_crew_permille: int = 400  # R-07 车载被毁班剩 40% 血（§D.0；GAP-07）
    mount_time_ticks: int = 200             # R-07 上车 20s（GAP-07）

    # 声测 R-03
    sonar_locate_threshold: int = 100
    sonar_max_radius_cm: int = 6000
    sonar_min_radius_cm: int = 1500
    sonar_hold_ticks: int = 100
    sonar_move_reset_cm: int = 3000

    # 烟雾
    smoke_radius_cm: int = 3000
    smoke_ttl_ticks: int = 600
    # ── PB-53 载具自卫烟幕（2026-10-04 拍板纳入——断箭 N32/映射 §五.19；cmd_smoke
    #    自卫路径消费 cooldown/delay，发数=ElementTemplate.self_smoke_charges 数据位）──
    self_smoke_default_charges: int = 2   # 数据侧定标参考占位（模板槽缺省 0=无能力——本
                                          # 常数零消费者不接线，sprint_cooldown_ticks 同款
                                          # 先例；断箭无每车发数证据=核证 v1 未确证#13，
                                          # 量级取 §F6 :1297 数据硬要求「烟罐×2/排」同款 2）
    self_smoke_cooldown_ticks: int = 300  # 两发冷却 30s（断箭无数值——无据占位待定标）
    self_smoke_delay_ticks: int = 20      # 生效延迟 2s（N32 唯一证据=官方补丁定性「固有
                                          # 部署延迟（不能导弹临头才按）」无秒数——无据
                                          # 占位待定标）
    # 半径/时长不另立轨：自卫烟幕复用上方 smoke_radius_cm/smoke_ttl_ticks（拍板行
    # 「复用 SmokeZone」——与 resolve_blast 迫击炮烟弹同源两常数，两体系同一烟区口径）

    # 建筑（§D.0 :76——楼塌驻军伤害，数值章节定；默认 0=塌楼无伤害）
    building_collapse_dmg: int = 0
    # ── 驻楼容量（2026-10-06 发起人拍板：小/中/大楼=1/2/3 个步兵排；容量按排=单位数计）──
    building_garrison_slots_small: int = 1   # 小楼（排）
    building_garrison_slots_medium: int = 2  # 中楼（排）
    building_garrison_slots_large: int = 3   # 大楼（排）
    building_size_footprint_max_cm: tuple[int, int] = (5000, 10000)
                                       # 小/中楼 footprint 上界阈值（≥上限即下一档）——阈值本身
                                       # 无文档锚=占位（发起人拍板只给档数 1/2/3），数值章节定标
                                       # 可调；apply_map 据此派生（map_loader.garrison_slots_for）

    # ── 相位与渗透（§F8 :1413-1421；phase_ticks=§D.0 表值。2026-10-03 发起人拍板：
    #    盲部署 90s→60s、取消开局禁火相位（D007/D008=GDD-00 :55/:59 废止）；实战时长不变）──
    phase_ticks: tuple[int, int] = (600, 13200)  # 盲部署60s/实战22min（按 phase 0/1 索引）
    infiltration_ticks: int = 600  # 渗透 60s 窗口（§F8 :1417 / §F7 :1396 两处字面 600 出表）

    # ── 经济与部署（§F7 :1374-1405；§D.0 :80 spawn_interval_ticks。2026-10-03 拍板：
    #    出牌序偏移步长删除——点单位直落锚点可叠放（PB-16），deploy_spawn_step_cm 退役）──
    spawn_interval_ticks: int = 10             # §D.0 :80 逐个间隔出牌（spawn_step 内部节流门）
    airdrop_crate_hp: int = 1                  # §F6 :1344 空投箱「HP 小（可摧毁）」——v1 定标=1
                                               # 任一命中即毁（2026-10-03 拍板转正，数值章节可调）

    # ── 爆破/面压制（AMB-01 衰减式三常数——2026-10-03 拍板出表，数值沿伪代码内嵌值
    #    不变；falloff_bp(d)=10000−MIN(coeff, d×coeff//(2×radius))，底线=10000−coeff）──
    blast_falloff_coeff_bp: int = 8000         # 衰减幅度系数 bp（跨度=2×弹半径）
    suppression_min_radius_cm: int = 2000      # 压制圈下限 MAX(blast_radius, ·)（AMB-01 字面）

    # ── 航空段（AIR_UNITS_PSEUDOCODE_IMPL_v1.4 §D.0：38 字段行，按字段名单一口径；
    #    一常数一轨——全部航空可调常数收此一处，系统函数禁止写死数值）──
    air_budget_base: int = 750                 # D038 空军独立预算（方案A占位）
    air_per_type_max: int = 2                  # 每机型同型在空上限（B-24/D032"每机型限2"出表——AMB3-08）
    air_map_margin_cm: int = 40000             # 场外缓冲带宽
    air_entry_offset_cm: int = 60000           # 进场段长度（cmd_air_call 消费——飞入时间位置化）
    patrol_orbit_radius_cm: int = 2000         # 待命盘旋半径
    dogfight_engage_cm: int = 8000             # R-20 同空域判据
    dogfight_interval_ticks: int = 30          # 缠斗回合周期（3s）
    dogfight_base_prob_bp: int = 3000          # 缠斗击落基础概率
    dogfight_tail_base_bp: int = 4000          # 脱离追尾基础概率
    dogfight_rounds_max: int = 40              # 缠斗回合上限（B-07）
    dogfight_reengage_immunity_ticks: int = 30  # 脱离后免咬窗（B-08 联动 GAP-08）
    self_defense_prob_bp: int = 2000           # D015 自卫火力基础命中
    alt_transition_ticks: int = 30             # 高度层间过渡（B-08）
    strafe_run_lead_cm: int = 8000             # 攻击线 RUN 段半长
    strafe_corridor_half_cm: int = 1500        # R-22 带状走廊半宽
    strafe_acc_alt_bp: tuple[int, int, int] = (13000, 10000, 7000)   # R-23 扫射精度（低/中/高）
    strafe_suppression_radius_cm: int = 2000   # 扫射近失压制半径
    strafe_suppress_jitter_cm: int = 1000      # 近失落点抖动（AMB-01）
    bomb_scatter_alt_bp: tuple[int, int, int] = (6000, 10000, 15000)  # R-23 炸弹散布高度系数
    bomb_scatter_speed_ref: int = 100          # 炸弹散布速度基准
    bomb_scatter_cloud_bp: tuple[int, int, int] = (10000, 11000, 13000)  # D026 云层投弹乘区（GAP-18）
    bomb_ellipse_ratio_bp: int = 5000          # 椭圆短轴=长轴×0.5
    dive_scatter_mult_bp: int = 5000           # 俯冲投弹精度乘区（B-09；斯图卡×0.5）
    dump_scatter_mult_bp: int = 20000          # 转对空丢弹散布乘区（应急抛投×2——放大方向；dive 5000 为缩小）
    airdrop_scatter_base_cm: int = 3000        # 空投散布基础（R-21/D015）
    airdrop_scatter_alt_bp: tuple[int, int, int] = (8000, 12000, 16000)
    airdrop_scatter_speed_ref: int = 100       # 空投速度基准（AMB-04 独立轨）
    airdrop_beacon_mult_bp: int = 5000         # 契约⑤冻结值：信标散布×0.5
    airdrop_beacon_radius_cm: int = 2500       # 信标吸附半径（B-16）
    airdrop_fee_points: int = 5                # D017 空投作业费（仅空降分支）
    air_cooldown_base_ticks: int = 600         # D015 冷却基数
    air_cooldown_per_missing_hp_ticks: int = 30
    air_cooldown_downed_multiplier: int = 3    # 击落冷却倍数（B-04）
    air_recon_period_ticks: int = 5            # 侦察标记节流（=sensing 同拍，B-23/GAP-05）
    air_recon_speed_ref: int = 100             # 标记概率速度基准（慢速易标）
    recon_optics_alt_bp: tuple[int, int, int] = (6000, 10000, 14000)   # R-23 观察半径（低小/高大）
    recon_mark_alt_bp: tuple[int, int, int] = (12000, 9000, 6000)      # R-23 标记概率（低高/高低）
    cloud_air_recon_mult_bp: tuple[int, int, int] = (10000, 6000, 3000)  # D026 低云削高空侦察（B-11）

    def speed_cm_tick(self, tier: int) -> int:
        return self.speed_table_cm_tick[tier]

    def terrain_speed_bp(self, movement_class: MovementClass,
                         tile_bp: int | None = None,
                         unit_bp: int = 0) -> int:
        """越野速度系数（道路加成由调用方取 MAX）。
        v1.7（GAP-19）：tile_bp 为按瓦片查表值（§F5 :962 world.terrain_speed_bp(pos, class)，
        TERRAIN[tile] 由 Tiled→JSON 接入）；None = stub 缺省值（位置无关的类级常数，
        TERRAIN 表接入后由调用方注入瓦片值——全局常数降级为缺省而非第二轨）。
        PB-52（2026-10-04 单位级地形数值块）：三级回退 瓦片注入 > 单位级覆盖 > 类级缺省
        ——unit_bp>0 即单位级覆盖（UnitTemplate.terrain_speed_override_bp；0=回退类级）。
        瓦片注入优先于单位级（GAP-19 语义保持：地形层在场时按瓦片值权威）。"""
        if tile_bp is not None:
            return tile_bp
        if unit_bp > 0:
            return unit_bp
        return {
            MovementClass.FOOT: 8000,
            MovementClass.WHEEL: 5000,
            MovementClass.TRACK: 7000,
            MovementClass.HORSE: 9000,
        }[movement_class]


CONFIG = BalanceConfig()
