# 测试说明 · demo-bagration-v1

今天版本的可测内容：**新单位图（67 地面 + 10 飞机）、新战场底图/小地图、4 张菜单背景、断箭风格 HUD/地图 UI、demo 启动脚本**。

## 1. 获取代码

```bash
git clone --branch demo-bagration-v1 --depth 1 \
  https://github.com/Sozbo-Tang/SOV_SS.git
cd SOV_SS
```

不想用 git：打开
`https://github.com/Sozbo-Tang/SOV_SS/releases/tag/demo-bagration-v1`
下载 Source code (zip) 解压。

## 2. 安装（Python 3.13）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[fe]"
```

> Windows：`py -3.13 -m venv .venv`、`.venv\Scripts\activate`、`pip install -e ".[fe]"`。

## 3. 启动

```bash
./demo.sh                    # 1600x900，主菜单
./demo.sh --size 1280x800    # 小窗
./demo.sh --smoke            # 无头自动跑一局，先确认环境
```

`--smoke` 末尾应出现 `OK ... 标准玩法剧本全绿`。

## 4. 必测清单

| # | 步骤 | 预期 |
|---|---|---|
| 1 | 主菜单 → 单人遭遇战 | 背景是地图桌上的电话/挎包绘景，按钮可点 |
| 2 | 配置页 | 地图「巴格拉季昂野外」、卡组、简报三行 |
| 3 | 部署页 | 左侧卡组点选→地图东侧放置；倒计时 12s 后开战 |
| 4 | 战斗页：选中单位 | 右下单位卡显示 T-34/85 等数据；地图上单位是**正俯视**图 |
| 5 | 战斗页：框选/右键移动 | 移动令生效；小地图与底图**同一张绘景**，不是棋盘格 |
| 6 | 战斗页：飞机 | 左侧呼入 IL-2/Pe-2/Yak-9，场上有飞机图标 |
| 7 | 战斗页：炮击/空袭 | 命令格显示对应按钮，点击后任务体生效 |
| 8 | 结算页 | 战果面板正常；可返回菜单 |
| 9 | 分辨率 | 1280×800 / 1600×900 均无遮挡、无越界 |

## 5. 本轮已知限制（不是 bug）

- 地形是文生图绘景，**村庄/桥/道路与玩法路网不保证严格对齐**；小地图已同源。
- 参考图未参与生成（网关无 `/images/edits`），单位靠提示词；个别 P1 单位偏题。
- 无音频。
- 地形底图来源标记 `assets/fe/terrain/bagration_field_base.source = img_gen`；跑 `pytest` 时 R6 程序化语义测试会跳过，属预期。

## 6. 反馈格式

请附：

1. 系统 / Python / arcade 版本；
2. 复现步骤 + 截图（全屏，含 HUD）；
3. 是否能稳定复现；控制台报错原文（如有）。

发到 issue 或直接回传，标题写 `[demo-bagration-v1]`。
