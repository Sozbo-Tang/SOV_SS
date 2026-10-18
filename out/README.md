# out/ · Demo 产物（精选，非全部）

`out/` 默认被 `.gitignore` 忽略；这里只提交与 demo 评审直接相关的产物。
完整缓存（dry-run payload、inbox、旧截图、references 等）保留在本地，不进仓。

## 内容

- `qa/*.png`：1280×800 五页截图（menu/config/settings/deck_edit/deploy/battle/result）；
- `qa/FE05_report.md`、`qa/FE05_audit.md`：HUD 复刻报告与审计；
- `img_gen/batch_01|02/manifest.json`：82 张图的生成台账（backend/mode/sha256/status）；
- `img_gen/batch_01|02/queue.json`：变体优先队列；
- `img_gen/batch_01|02/contact_sheet.png`：评审拼图；
- `img_gen/batch_01/{units,air,bg}/*.png`：1024px 母版（已入库 128px 版在 `assets/fe/`）；
- `img_gen/batch_02/units/*.png`：P1 单位 1024px 母版；
- `img_gen/prompts/*.txt`：82 条提示词；
- `demo/README.md`：demo 启动/流程/限制。

## 不提交

`img_gen/dry_run_payload/`、`img_gen/inbox/`、`img_gen/t_case/`、`qa_1600/`、
`qa_1920/`、`references/`、`refs/`、`manual_build/`、`art/` 等本地缓存/研究素材。
