"""命令通道（FE-T07）：UI 意图 → 查活对象 → 构造命令 → queue_command。

结论先行：本模块是可玩壳的**唯一发令通道**——人机同管线（KevPlayer/AI 侧同走
queue_command，tick.py:2038 唯一入队口）；shell_window 不直接碰命令对象，只把
点击/按键翻译成本模块的意图调用（unit_id/dest_cm 等纯数据入参），由本模块在
world 内查活对象构造命令。合法性由引擎 cmd_* 各门最终裁决（越门静默 REJECT——
候选生成与执行分离口径，sovs/ai/actions.py 头注同款；拒绝反馈经 state_frame
rejections → fsm toast，§4 ④段）。

分层特许（tests/test_arch_constraints.py ②）：本模块是 sovs/ui 唯一允许
import sovs.sim 的文件，且限 sovs.sim.tick（命令类 *Cmd + queue_command）与
sovs.sim.types（枚举）——air 模板注册表（air_data.AIR_CARDS）等其余 sim 面
由 sovs/app 会话胶水层解析后以活对象传入（air_call 的 template 形参），
本模块不越面。

覆盖组（FE-T07 五组 + GP-01 §3/§4/§6 扩容）：
- 移动族：move/stop/cancel/reverse/sprint（MoveCmd/StopCmd/CancelCmd/ReverseCmd
  /SprintCmd；move 的 mode 形参承载 NORMAL/ATTACK/MARCH——§6 F 行军）；
- 攻击：attack（AttackCmd——element 位取首个有射程有弹武器元素）；
- 炮击任务：fire_mission/cancel_fire_mission（SetModeCmd(INDIRECT) 预置 +
  FireMissionCmd——GP-01 §3 全参透传：form POINT|LINE|CREEP、ammo HE|SMOKE、
  ammo_mult 1..3 时长档、salvo_mode FULL|HALF 低强度快闪、creep_speed 徐进
  速度；sim 侧六字段全备 tick.py:1629-1645，本模块只做包装不新增语义）；
- 空军六令（GP-01 §4 ③段——命令类零新增）：air_move（直飞航路）/
  air_patrol（CAP 盘旋，右键映射）/air_reset（E 键原地重置映射——中断
  INGRESS 段任务）/air_alt（V 高度层）/air_engage_air（J 对空开关）/
  air_disengage（Y 缠斗脱离）/air_rtb（B 返航不可逆）＋air_strike（K 点/线
  双形态——axis 画线攻击轴透传）/air_airdrop（O 空投）；
- §6 「sim 有 UI 无入口」包装：unload（DismountCmd＋点楼 GarrisonCmd 排队）/
  sniper_cover（SetSniperCoverCmd 观测）/ambush（ToggleAmbushCmd）/
  deploy_gun/pack_gun（展开/收炮）/tow/untow（拖曳）/formation（队形）/
  supply_dock（补给停靠＝move 入补给半径——车载制映射，无「卸货成堆」命令）；
- 烟幕冲刺姿态：smoke_sprint_stance（SmokeCmd+SprintCmd+SetStanceCmd 三令
  一键——自卫烟幕发数门内元素才发 SmokeCmd，无烟弹单位余两令照发）。

常量镜像纪律：AIR_PATROL_RADIUS_CM＝tables.py patrol_orbit_radius_cm 现值
镜像（本模块禁 import sovs.sim.tables——AST 守卫②；同值由
tests/test_gp01_frontend.py 锚死防漂移）。

trail：每笔意图落一条播报记录（kind/unit_ids/point_cm/tick，UI 画已下令痕迹
与门禁证据共用），TRAIL_CAP 封顶防膨胀；move 条目另携带 mode 字段（交互重设计
A6 判据：攻击移动入口生效）。
"""
from __future__ import annotations

from sovs.sim.tick import (AirAirdropCmd, AirAltCmd, AirCallCmd,  # noqa: E402
                           AirDisengageCmd, AirEngageAirCmd, AirMoveCmd,
                           AirPatrolCmd, AirRTBCmd, AirStrikeCmd, AttackCmd,
                           CancelCmd, CancelFireMissionCmd, DeployCmd,
                           DismountCmd, FireMissionCmd, FormationCmd,
                           GarrisonCmd, MountCmd, MoveCmd, PackCmd,
                           PurchaseCmd, ReverseCmd, SetModeCmd,
                           SetSniperCoverCmd, SetStanceCmd, SmokeCmd,
                           SprintCmd, StopCmd, ToggleAmbushCmd, TowCmd,
                           UntowCmd, queue_command)
from sovs.sim.types import (AltTier, FireMissionForm, FormationShape,  # noqa: E402
                            Mode, MoveMode, SalvoMode, Stance, UnitFlag)

TRAIL_CAP = 64                       # 已发令轨迹条数上限（UI 播报面防膨胀）

# CAP 盘旋半径缺省（右键盘旋待令用）——tables.py patrol_orbit_radius_cm 现值
# 镜像（见头注「常量镜像纪律」；tests/test_gp01_frontend.py 同值锚）。
AIR_PATROL_RADIUS_CM = 2000


class CmdBus:
    """UI 意图 → 命令对象 → queue_command（world 鸭子引用——不 import World 类）。"""

    TRAIL_CAP = TRAIL_CAP             # 类面再出口（测试/UI 取值免模块引用）

    def __init__(self, world, player_index: int):
        self.world = world
        self.player_index = int(player_index)
        self.trail: list[dict] = []

    # ── 内部：查活对象 + 入队 + 轨迹 ──

    def _player(self):
        return self.world.players[self.player_index]

    def _unit(self, unit_id: int):
        for u in self.world.units:
            if u.id == unit_id and u.alive:
                return u
        return None

    def _aircraft(self, aircraft_id: int):
        for a in self.world.aircraft:
            if a.id == aircraft_id:
                return a
        return None

    def _building(self, building_id: int):
        for b in getattr(self.world, "buildings", ()):
            if b.id == building_id and b.hp > 0:
                return b
        return None

    def _queue(self, cmd):
        queue_command(self.world, cmd)
        return cmd

    def _record(self, kind: str, unit_ids=(), point=None, mode=None) -> None:
        entry = {"kind": kind, "unit_ids": list(unit_ids),
                 "point_cm": None if point is None else [point[0], point[1]],
                 "tick": self.world.tick}
        if mode is not None:
            entry["mode"] = mode          # trail 扩展字段（A6：move 条目携带 NORMAL/ATTACK/MARCH）
        self.trail.append(entry)
        if len(self.trail) > TRAIL_CAP:
            del self.trail[: len(self.trail) - TRAIL_CAP]

    # ── 盲部署：购卡（PurchaseCmd——位置由 spawn_step 落己方底边中点锚）──

    def purchase(self, template_id: int):
        """购卡意图：deck 槽查活对象 → PurchaseCmd(player, template)。

        空降投送限定卡（DELIVERY_AIRDROP_ONLY——空裁8 购买门恒拒）与未知卡在
        查活对象阶段即拦（不入队，返回 None）；点数/余量门留给引擎裁决。
        """
        for slot in self._player().deck_slots:
            if slot.template.template_id == template_id:
                if slot.template.flags & UnitFlag.DELIVERY_AIRDROP_ONLY:
                    return None
                return self._queue(PurchaseCmd(player=self._player(),
                                               template=slot.template))
        return None

    # ── 移动族（Move/Stop/Cancel/Reverse/Sprint）──

    def move(self, unit_ids, dest_cm, mode: str = "NORMAL",
             queue: bool = False, record: bool = True) -> list:
        """移动令（逐单位 MoveCmd；path=[dest] 单段——预置展开车道同款形态）。

        mode 透传 MoveMode 名（NORMAL/ATTACK/MARCH——攻击前进 A6/行军 §6 F）；
        queue=True 走 Shift 排队（MoveCmd queue 形参 types.py 已备，入单位级
        command_queue 链尾）。trail 条目携带 mode 字段（A6 判据）；record=False
        供组合令（unload/supply_dock）内联复用不重复落账。
        """
        cmds = []
        for uid in unit_ids:
            u = self._unit(uid)
            if u is not None:
                cmds.append(self._queue(MoveCmd(
                    unit=u, path=[(int(dest_cm[0]), int(dest_cm[1]))],
                    mode=MoveMode[mode], queue=bool(queue))))
        if cmds and record:
            self._record("move", unit_ids, dest_cm, mode=mode)
        return cmds

    def stop(self, unit_ids) -> list:
        cmds = [self._queue(StopCmd(unit=u)) for uid in unit_ids
                if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("stop", unit_ids)
        return cmds

    def cancel(self, unit_ids) -> list:
        cmds = [self._queue(CancelCmd(unit=u)) for uid in unit_ids
                if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("cancel", unit_ids)
        return cmds

    def reverse(self, unit_ids, dest_cm) -> list:
        cmds = [self._queue(ReverseCmd(unit=u, dest=(int(dest_cm[0]),
                                                      int(dest_cm[1]))))
                for uid in unit_ids if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("reverse", unit_ids, dest_cm)
        return cmds

    def sprint(self, unit_ids) -> list:
        cmds = [self._queue(SprintCmd(unit=u)) for uid in unit_ids
                if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("sprint", unit_ids)
        return cmds

    # ── 攻击（AttackCmd——element 位=首个有射程有弹武器元素）──

    def attack(self, unit_id: int, target_unit_id: int) -> list:
        shooter = self._unit(unit_id)
        foe = self._unit(target_unit_id)
        if shooter is None or foe is None:
            return []
        e = self._first_armed_element(shooter)
        t = next((el for el in foe.elements if el.hp_current > 0), None)
        if e is None or t is None:
            return []
        self._record("attack", [unit_id], foe.pos)
        return [self._queue(AttackCmd(element=e, target=t))]

    @staticmethod
    def _first_armed_element(unit):
        """首个有射程>0 且有弹的元素（actions.py _first_armed_element 同款）。"""
        for e in unit.elements:
            if any(ws.template.max_range_cm > 0 and ws.ammo_left > 0
                   for ws in e.weapon_states):
                return e
        return None

    # ── 炮击任务（SetMode(INDIRECT) 预置 + FireMissionCmd / Cancel）──

    def fire_mission(self, unit_id: int, point_or_line, *, form: str = "POINT",
                     ammo: str = "HE", ammo_mult: int = 1,
                     salvo_mode: str | None = "FULL",
                     creep_speed: int = 0) -> list:
        """炮击任务令（GP-01 §3 全参透传）：无 INDIRECT 位的单位不构造。

        point_or_line：form=POINT 传 (x,y)；LINE/CREEP 传 ((x0,y0),(x1,y1))。
        ammo HE|SMOKE（SMOKE 走引擎烟档门——无烟弹武器行的卡组任务被拒并经
        rejection_log 反馈）；ammo_mult 1..3 时长档；salvo_mode FULL|HALF
        （HALF=低强度快闪前 ⌈N/2⌉ 门）；creep_speed 徐进速度（CREEP 形态用，
        档位=shell_fsm.CREEP_SPEEDS_CM）。缺省参=既有 POINT/HE 行为不变。
        """
        unit = self._unit(unit_id)
        if unit is None or not (unit.template.mode_set & (1 << Mode.INDIRECT)):
            return []
        cmds = [self._queue(SetModeCmd(element=el, mode=Mode.INDIRECT))
                for el in unit.elements]               # 资格外元素由引擎资格门拒
        fm_form = FireMissionForm[form]
        is_point = fm_form is FireMissionForm.POINT
        point = (int(point_or_line[0]), int(point_or_line[1])) if is_point else None
        line = None if is_point else ((int(point_or_line[0][0]),
                                       int(point_or_line[0][1])),
                                      (int(point_or_line[1][0]),
                                       int(point_or_line[1][1])))
        cmds.append(self._queue(FireMissionCmd(
            unit=unit, form=fm_form, point=point, line=line,
            ammo_mult=int(ammo_mult), ammo=str(ammo),
            salvo_mode=(SalvoMode[salvo_mode] if salvo_mode else None),
            creep_speed=int(creep_speed))))
        self._record("fire_mission", [unit_id],
                     point if is_point else point_or_line[0])
        return cmds

    def cancel_fire_mission(self, unit_ids) -> list:
        cmds = [self._queue(CancelFireMissionCmd(unit=u)) for uid in unit_ids
                if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("cancel_fire_mission", unit_ids)
        return cmds

    # ── 空军呼叫（AirCallCmd→AirStrikeCmd/AirAirdropCmd）──

    def air_call(self, template, payload: dict) -> list:
        """呼叫航空器（template=胶水层自 AIR_CARDS 解析的活模板对象传入）。

        payload 键域 {BOMB:int, SUPPLY:int, PARATROOP:True}；PARATROOP=True 在
        此执行期换装 deck 槽活模板（DELIVERY_AIRDROP_ONLY 位余份>0 的首槽——
        actions.py:131-137 deck 槽解析同款口径）；无预备队卡即不构造。
        """
        payload = dict(payload or {})
        if payload.get("PARATROOP") is True:
            slot = self._paratroop_slot()
            if slot is None:
                return []
            payload["PARATROOP"] = slot.template      # 换装：True → 活模板引用
        self._record("air_call", (), None)
        return [self._queue(AirCallCmd(player=self._player(), template=template,
                                       payload=payload))]

    def _paratroop_slot(self):
        for slot in self._player().deck_slots:
            if (slot.template.flags & UnitFlag.DELIVERY_AIRDROP_ONLY
                    and slot.copies_left > 0):
                return slot
        return None

    def air_strike(self, aircraft_id: int, target_cm, weapon: str = "BOMB",
                   axis=None):
        """K 空袭令（点/线双形态——GP-01 §4 ③段评审②补）。

        axis=None=点目标（run 轴由机位自动推导）；axis=((x0,y0),(x1,y1))=
        画线攻击轴（cmd_air_strike 按玩家线向推导 run_start/run_end）。
        """
        a = self._aircraft(aircraft_id)
        if a is None:
            return None
        axis_t = None if axis is None else ((int(axis[0][0]), int(axis[0][1])),
                                            (int(axis[1][0]), int(axis[1][1])))
        self._record("air_strike", (), target_cm)
        return self._queue(AirStrikeCmd(aircraft=a,
                                        target=(int(target_cm[0]),
                                                int(target_cm[1])),
                                        weapon=weapon, axis=axis_t))

    def air_airdrop(self, aircraft_id: int, point_cm):
        a = self._aircraft(aircraft_id)
        if a is None:
            return None
        self._record("air_airdrop", (), point_cm)
        return self._queue(AirAirdropCmd(aircraft=a,
                                         drop_point=(int(point_cm[0]),
                                                     int(point_cm[1]))))

    # ── 空军六令（GP-01 §4 ③段——AirMove/Patrol/Alt/EngageAir/Disengage/RTB）──

    def air_move(self, air_ids, dest_cm) -> list:
        """直飞航路（Shift+右键映射——转场/进场压低空用；RUN/EGRESS 引擎门拒）。"""
        cmds = []
        for aid in air_ids:
            a = self._aircraft(aid)
            if a is not None:
                cmds.append(self._queue(AirMoveCmd(
                    aircraft=a, path=[(int(dest_cm[0]), int(dest_cm[1]))])))
        if cmds:
            self._record("air_move", air_ids, dest_cm)
        return cmds

    def air_patrol(self, air_ids, center_cm,
                   radius: int = AIR_PATROL_RADIUS_CM) -> list:
        """CAP 盘旋待命（右键盘旋映射——到点绕圈＋同空域自动缠斗，§4 Q 键等效）。"""
        cmds = []
        for aid in air_ids:
            a = self._aircraft(aid)
            if a is not None:
                cmds.append(self._queue(AirPatrolCmd(
                    aircraft=a, center=(int(center_cm[0]), int(center_cm[1])),
                    radius=int(radius))))
        if cmds:
            self._record("air_patrol", air_ids, center_cm)
        return cmds

    def air_reset(self, air_ids) -> list:
        """E 键空中重置映射：AirPatrolCmd 原地重置（中断进行中 INGRESS 段的
        攻击/空投任务回盘旋；RUN/EGRESS 不可中断=引擎门，拒绝日志反馈）。"""
        cmds = []
        for aid in air_ids:
            a = self._aircraft(aid)
            if a is not None:
                cmds.append(self._queue(AirPatrolCmd(
                    aircraft=a, center=(int(a.pos[0]), int(a.pos[1])),
                    radius=AIR_PATROL_RADIUS_CM)))
        if cmds:
            self._record("air_reset", air_ids)
        return cmds

    def air_alt(self, air_ids, tier: str) -> list:
        """高度层变更（V 键——LOW/MID/HIGH；超 alt_ceiling 引擎门拒）。"""
        t = AltTier[str(tier).upper()]
        cmds = []
        for aid in air_ids:
            a = self._aircraft(aid)
            if a is not None:
                cmds.append(self._queue(AirAltCmd(aircraft=a, tier=t)))
        if cmds:
            self._record("air_alt", air_ids)
        return cmds

    def air_engage_air(self, air_ids, engage: bool) -> list:
        """对空开关（J 键——开拨实战门+带弹丢弹 D015；无对空槽机型引擎门拒）。"""
        cmds = []
        for aid in air_ids:
            a = self._aircraft(aid)
            if a is not None:
                cmds.append(self._queue(AirEngageAirCmd(aircraft=a,
                                                        engage=bool(engage))))
        if cmds:
            self._record("air_engage_air", air_ids)
        return cmds

    def air_disengage(self, air_ids) -> list:
        """缠斗脱离（Y 键——仅 DOGFIGHT 态引擎门放行，tail 掷骰 R-20）。"""
        cmds = []
        for aid in air_ids:
            a = self._aircraft(aid)
            if a is not None:
                cmds.append(self._queue(AirDisengageCmd(aircraft=a)))
        if cmds:
            self._record("air_disengage", air_ids)
        return cmds

    def air_rtb(self, air_ids) -> list:
        """RTB 返航（B 键——B-22 不可逆；UI 侧二次确认 toast 提示）。"""
        cmds = []
        for aid in air_ids:
            a = self._aircraft(aid)
            if a is not None:
                cmds.append(self._queue(AirRTBCmd(aircraft=a)))
        if cmds:
            self._record("air_rtb", air_ids)
        return cmds

    # ── §6 「sim 有 UI 无入口」包装（命令类全部既有——零新增语义）──

    def unload(self, unit_ids, cm=None, building_id=None) -> list:
        """U 卸载待令组：DismountCmd＋（点楼=GarrisonCmd 排队下车进楼/点地=
        move 开进）。建筑对象经 world.buildings 查活（hp>0）。"""
        cmds = []
        units = [u for uid in unit_ids if (u := self._unit(uid)) is not None]
        building = self._building(building_id) if building_id is not None else None
        for u in units:
            cmds.append(self._queue(DismountCmd(squad_unit=u)))
            if building is not None:
                cmds.append(self._queue(GarrisonCmd(unit=u, building=building)))
        if building is None and cm is not None and units:
            cmds.extend(self.move([u.id for u in units], cm, record=False))
        if cmds:
            self._record("unload", unit_ids, cm)
        return cmds

    def sniper_cover(self, unit_ids, target_unit_id: int) -> list:
        """N 狙击观测（SetSniperCoverCmd——命中减半乘区，§3 表行 6 精确映射）。"""
        foe = self._unit(target_unit_id)
        if foe is None:
            return []
        cmds = [self._queue(SetSniperCoverCmd(sniper_unit=u, target_unit=foe))
                for uid in unit_ids if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("sniper_cover", unit_ids, foe.pos)
        return cmds

    def ambush(self, unit_ids) -> list:
        """伏击显式开关（R-12——比断箭「掩体+停火」组合更强，§6 补 UI 入口）。"""
        cmds = [self._queue(ToggleAmbushCmd(unit=u)) for uid in unit_ids
                if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("ambush", unit_ids)
        return cmds

    def deploy_gun(self, unit_ids) -> list:
        """展开炮位（DeployCmd——火炮 needs_deployed 射击门前置）。"""
        cmds = [self._queue(DeployCmd(unit=u)) for uid in unit_ids
                if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("deploy", unit_ids)
        return cmds

    def pack_gun(self, unit_ids) -> list:
        """收炮行军（PackCmd——cmd_pack_or_move 处理体）。"""
        cmds = [self._queue(PackCmd(unit=u)) for uid in unit_ids
                if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("pack", unit_ids)
        return cmds

    def tow(self, unit_ids) -> list:
        """拖曳（TowCmd——恰两单位时：首选中=牵引车全元素、次选中=首元素被拖；
        元素级资格/吨位门由引擎裁决）。"""
        units = [u for uid in unit_ids if (u := self._unit(uid)) is not None]
        if len(units) != 2 or not units[1].elements:
            return []
        cmds = [self._queue(TowCmd(tower_elements=list(units[0].elements),
                                   towed_element=units[1].elements[0]))]
        self._record("tow", unit_ids, units[1].pos)
        return cmds

    def untow(self, unit_ids) -> list:
        """解除拖曳（UntowCmd——element 级，取首元素）。"""
        cmds = []
        for uid in unit_ids:
            u = self._unit(uid)
            if u is not None and u.elements:
                cmds.append(self._queue(UntowCmd(element=u.elements[0])))
        if cmds:
            self._record("untow", unit_ids)
        return cmds

    def formation(self, unit_ids, shape: str) -> list:
        """队形切换（FormationCmd——NONE/LINE/COLUMN/WEDGE，§6 选中面板入口）。"""
        units = [u for uid in unit_ids if (u := self._unit(uid)) is not None]
        if not units:
            return []
        cmds = [self._queue(FormationCmd(units=units,
                                         shape=FormationShape[shape.upper()]))]
        self._record("formation", unit_ids)
        return cmds

    def supply_dock(self, unit_ids, truck_unit_id: int) -> list:
        """补给停靠待令组（§6 车载制映射：选中缺弹单位点补给卡车＝move 入补给
        半径——D065 卡车即移动补给堆，无「卸货成堆」独立命令）。"""
        truck = self._unit(truck_unit_id)
        if truck is None:
            return []
        cmds = self.move(unit_ids, truck.pos, record=False)
        if cmds:
            self._record("supply_dock", unit_ids, truck.pos)
        return cmds

    def mount(self, unit_ids, carrier_unit_id: int) -> list:
        """战斗期组运输（MountCmd ㉑A——班元素逐班占座；§6 表「已有」面的
        UI 包装，element 位=各单位全部元素）。"""
        carrier = self._unit(carrier_unit_id)
        if carrier is None:
            return []
        squads = [e for uid in unit_ids
                  if (u := self._unit(uid)) is not None for e in u.elements]
        if not squads:
            return []
        cmds = [self._queue(MountCmd(squad_elements=squads,
                                     carrier_unit=carrier))]
        self._record("mount", unit_ids, carrier.pos)
        return cmds

    # ── 烟幕冲刺姿态（SmokeCmd+SprintCmd+SetStanceCmd 三令一键）──

    def smoke_sprint_stance(self, unit_ids, stance: str = "HOLD_FIRE") -> list:
        """三令组合：自卫烟幕（发数门内元素）+ 冲刺 + 转禁火姿态（隐蔽机动）。"""
        cmds = []
        for uid in unit_ids:
            u = self._unit(uid)
            if u is None:
                continue
            cmds.extend(self.smoke([uid], record=False))
            cmds.append(self._queue(SprintCmd(unit=u)))
            cmds.append(self._queue(SetStanceCmd(unit=u,
                                                 stance=Stance[stance])))
        if cmds:
            self._record("smoke_sprint", unit_ids)
        return cmds

    # ── 单令包装（交互重设计：X 自卫烟幕单令 / H 交战纪律切换）──

    def smoke(self, unit_ids, *, record: bool = True) -> list:
        """自卫烟幕单令（X 键——SmokeCmd 既有命令类的包装，不新增引擎语义）：
        发数门内元素才构造（cmd_smoke 发数门镜像——无烟弹单位不入队不落 trail）。"""
        cmds = []
        for uid in unit_ids:
            u = self._unit(uid)
            if u is None:
                continue
            smoker = next((e for e in u.elements if e.self_smoke_left > 0), None)
            if smoker is not None:
                cmds.append(self._queue(SmokeCmd(element=smoker,
                                                 point=tuple(smoker.pos))))
        if cmds and record:
            self._record("smoke", unit_ids)
        return cmds

    def stance(self, unit_ids, stance: str) -> list:
        """姿态单令（H 键——SetStanceCmd 包装：weapons_free↔hold_fire 独立切换）。"""
        cmds = [self._queue(SetStanceCmd(unit=u, stance=Stance[stance]))
                for uid in unit_ids if (u := self._unit(uid)) is not None]
        if cmds:
            self._record("stance", unit_ids)
        return cmds
