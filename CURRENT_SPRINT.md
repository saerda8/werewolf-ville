# Current Sprint

更新日期：2026-06-04

关联需求：REQ-011 ~ REQ-017（版本与项目治理）。完成时 commit 标注 `(refs REQ-XXX)`。

## Sprint 目标

实现黄昏集合、顺时针讨论、全员投票、自动拘留与夜晚不可操作过场。

## 当前频道

玩法设计频道：黄昏投票与夜晚过场开发中。

## 任务清单

- [x] 初始化 Git 仓库并创建首个基线提交。
- [x] 创建项目连续性文档 `PROJECT_CONTINUITY.md`。
- [x] 建立 `ROADMAP.md`。
- [x] 建立 `BUG_BACKLOG.md`。
- [x] 建立 `CURRENT_SPRINT.md`。
- [x] 建立频道工作流文档与短期任务 `.planning/` 目录规范。
- [x] 汇总 DeepSeek 的 `game_engine.py` 拆分建议并建立 `GAME_ENGINE_SPLIT_PLAN.md`。
- [x] 汇总 Antigravity 的频道/流程建议并落实在 `PROJECT_CHANNELS.md`。
- [x] 写出最终 `game_engine.py` 拆分执行计划与 Worker 协作 SOP。
- [x] 执行低风险拆分切片并提交。

## 本轮不做

- 不直接修 UI 气泡 bug。
- 不直接改投票玩法。
- 不新增银器/夜晚玩法。

原因：先拆结构，再修 bug，避免重复回归。

## 验证要求

每个拆分切片必须通过回归门禁（详见 `PROJECT_CONTINUITY.md §11.1`），至少：

```powershell
python -m py_compile agent.py game_engine.py llm.py ui/app.py
```

根据影响范围运行相关测试：

```powershell
pytest -q tests/test_engine_foundation.py
pytest -q tests/test_vote_flow.py
pytest -q tests/test_ui_bubble_layout.py
```

验收后更新 `BUG_BACKLOG.md` 状态（如有相关 bug）并在 commit 中标注关联 REQ。

## 项目线程状态

- [x] 项目结构与治理线程：`019e8322-7e35-71b1-aba5-0148fb57347d`
- [x] 玩法设计线程：`019e92f1-c30c-7e42-a14c-b695433729bf`
- [x] Bug 修复线程：`019e92f1-e1b0-7153-9b92-859a70f450d4`

Codex 项目目标使用工作区路径 `G:\Trae-Project\werewolf-ville`。后续创建线程不强行传模型名。

## 结构阶段收口结果（2026-06-04）

- [x] 抽离导航与地图纯工具：`engine_navigation.py`
- [x] 抽离警长每日任务构建：`engine_tasks.py`
- [x] 抽离引擎侧气泡计时与摘要：`engine_bubbles.py`
- [x] 抽离黄昏、投票与监狱流程：`engine_dusk.py`
- [x] 每个结构切片独立验证并提交
- [x] 记录后续高风险拆分边界

项目结构阶段完成，已完成一轮 Bug Backlog 收口。后续新方向应转入 **玩法设计线程**，围绕 NPC 行为框架、行动枚举、线索灯泡、主动汇报和交谈规则形成设计文档，不再在本线程混入新玩法讨论。

最终收口回归：`python -m pytest tests -q`，结果 `380 passed`。

## 玩法体验修复收口（2026-06-05）

- [x] 开局聚集和尸体送走/返回流程完成前，克罗不能被玩家点击地图或点击 NPC 强制移动。
- [x] 普通气泡显示时长统一为约 6 秒；蓝色思考/行动气泡不再因 NPC 仍在行动或思考而无限续命。
- [x] NPC 轮流发言间隔统一为 0.5 秒，覆盖开局第一轮、第二轮和黄昏发言。
- [x] 开始游戏前本地 Chat2API 也走后端真实 NPC 模型通路检测，不再前端直接判定通过。
- [x] NPC 行动气泡只显示短动作，不展示完整思考、计划或模型内心独白。
- [x] NPC 每次成功思考/计划后必须先执行一次行动；已有待执行行动时，行动完成前不会再次请求大模型思考。
- [x] 回归验证：`python -m pytest tests -q` 通过，结果 `398 passed`，只有 pytest cache 权限警告。

## NPC 行为状态机收口（2026-06-06）

- [x] NPC 完成思考/计划后必须先执行一次行动；已有 moving/acting/conversation/pending action 时不会再次进入下一轮思考。
- [x] 计划后目标临时不可达、无法接近目标人或目标物时，转为可见的 continue_current 行动，避免空回 idle。
- [x] NPC 主动找克罗汇报后立即清理对话锁、pending action、thinking/acting 残留状态；普通警长访谈回复完成后也释放锁。
- [x] NPC-NPC 交谈锁跟随白色气泡生命周期释放；等待模型时先显示 `...`，气泡过期后双方释放。
- [x] 全量回归：`python -m pytest tests -q` 通过，406 passed，仅 pytest cache 权限警告。

## NPC 行为生命周期队列收口（2026-06-06）

- [x] NPC 串行规划按 `active_agents` 顺序轮询；当前候选 NPC 处于 retry 或行动决策冷却时，会推进到下一个合格 NPC。
- [x] moving、acting、pending planning、conversation 状态都会被规划队列跳过，避免同一个 NPC 连续占用模型请求机会。
- [x] 普通行动进入本地 `acting` 占用期后不再调用模型；行动完成前不会开启下一轮思考/计划。
- [x] 普通行动期间显示白色持续状态气泡，例如 `正在看书...`，直到行动结束才清除。
- [x] 玩家日志保留 `[行动计划]`、`[开始行动]`、`[行动结果]`，能看到思考/计划/行动闭环。
- [x] 前端版本改为显式 `FRONTEND_VERSION`，当前显示版本 `30`。
- [x] 蓝色行动气泡只显示“前往目标 + 做什么事”，不再混入思考/计划；白色行动持续气泡只显示短任务并跟随行动持续时间。
- [x] 气泡显示改为严格串行互斥：思考/计划蓝泡 -> 开始行动蓝泡 -> 行动持续白泡；moving 阶段不显示白色持续泡，`action_status` 不加“某某说：”。
- [x] 对 `action_status` 增加前端硬门禁：即使后端提前发白泡，也必须等开始行动蓝泡实际结束（`expired === true`）且 NPC 不再移动后才显示。
- [x] NPC 行动决策 JSON 增加 `action_status` 字段：模型直接提供行动持续白泡短句，代码只做兜底清理，不再主要靠硬截断行动句。
- [x] 修复 NPC 到达目标但仍卡在 `moving` 的状态，避免该 NPC 被规划队列长期跳过。
- [x] 行动持续白泡真实显示时间增加 6 秒下限。
- [x] 目标坐标不变但 target_object 不同的行动，也会先尝试移动到周围一格，避免原地不动。
- [x] 第三条记忆线已记录为稳定规则：行动完成后沉淀记忆，记忆写入不产生可见气泡。
- [x] 模型发言请求统一进入 speech queue：警长问话优先，普通 NPC-NPC 发言按触发顺序串行执行。
- [x] 警长访谈锁改为白色气泡过期后释放；NPC 主动单向汇报仍保持无锁，避免残留状态。
- [x] 警长主动找 NPC 交谈会立即中断该 NPC 旧移动/旧行动/旧行动持续泡，目标 NPC 进入交谈占用并显示 `...` 等回复；回复白泡过期后才释放。
- [x] 通用真实交谈白泡不能与开始行动蓝泡共存；第二轮离场发言是阶段特殊流程，先白色发言结束，再进入蓝色离场行动和移动。
- [x] 白天连续实时反思线已切掉；反思只保留为入夜阶段节点后台任务，不再制造无行动蓝泡泡。
- [x] 行动决策失败/异常会进入具体 `continue_current` 持续行动，默认占用 30 游戏分钟，避免 NPC 回 idle 空想。
- [x] 回归验证：`python -m py_compile agent.py game_engine.py llm.py ui/app.py engine_navigation.py engine_tasks.py engine_bubbles.py engine_dusk.py` 通过。
- [x] 相关回归：`python -m pytest tests/test_ui_bubble_layout.py tests/test_agent_action_json.py tests/test_gathering_timeout.py tests/test_engine_foundation.py tests/test_daytime_npc_behavior.py tests/test_game_engine_night_loop.py -q` 通过，368 passed，仅 pytest cache 权限警告。
- [x] 全量回归：`python -m pytest tests -q` 通过，433 passed，仅 pytest cache 权限警告。
- [x] 版本 28 回归：`python -m pytest tests/test_engine_foundation.py tests/test_daytime_npc_behavior.py tests/test_agent_action_json.py tests/test_ui_bubble_layout.py -q` 通过，294 passed；`python -m pytest tests -q -p no:cacheprovider` 通过，435 passed。
- [x] 版本 30 回归：`python -m py_compile agent.py game_engine.py llm.py ui/app.py engine_navigation.py engine_tasks.py engine_bubbles.py engine_dusk.py` 通过；相关回归 `python -m pytest tests/test_engine_foundation.py tests/test_daytime_npc_behavior.py tests/test_ui_bubble_layout.py tests/test_gathering_timeout.py -q -p no:cacheprovider` 通过，350 passed。
- [x] 版本 30 最终全量回归：`python -m pytest tests -q -p no:cacheprovider` 通过，443 passed。

## 黄昏投票与夜晚过场（2026-06-07）

权威规格：`docs/superpowers/specs/2026-06-07-dusk-voting-night-transition-design.md`

执行计划：`docs/superpowers/plans/2026-06-07-dusk-voting-night-transition.md`

- [x] 用户确认玩法规则、固定台词、警长平票裁决和夜晚隐藏过场。
- [x] 写入正式玩法规格与开发计划。
- [x] 实现黄昏压暗、程序化召集与全员回广场。
- [x] 实现第一天固定狼人知识揭露与顺时针讨论。
- [x] 实现玩家只控制克罗票、允许自投、30 秒投票和最高票自动拘留。
- [x] 实现票数/投票者头像结果面板与警长平票裁决说明。
- [x] 实现克罗押送后回办公室，再进入不可操作夜晚过场。
- [x] 完成回归测试、服务重启和浏览器验收。

验收结果：前端版本 `31`；正式 `tests` 目录全量回归 `464 passed`。内置浏览器确认最新页面与版本 31 已加载；第二次截图复核时内置浏览器截图命令超时，不影响页面 HTTP 健康检查。

## NPC 行为改版回归修复（2026-06-07）

- [x] 每次新行动按独立开始时间刷新蓝泡，不再被相同文本的旧缓存吞掉。
- [x] 后端先进入 `starting_action` 蓝泡展示期；展示期结束后才允许移动、普通行动或真实聊天。
- [x] 打招呼、询问、聊天、交谈统一靠近目标后进入真实发言模型管线，不再进入普通行动持续期。
- [x] 交谈目标移动时重新靠近；无法靠近时转为可见 `continue_current`。
- [x] 真实发言、行动中和行动结果日志为绿色；思考、计划、开始执行日志为紫色。
- [x] 被真实白泡互斥隐藏的蓝色行动泡不再计为“已展示完成”。
- [x] NPC 主动向 Crow 单向汇报白泡可见期间不会进入下一轮规划，同时仍不保留对话锁/pending/acting。
- [x] 编译、前端脚本语法和相关回归通过：315 passed。
- [x] 正式全量回归通过：471 passed。
- [x] 内置浏览器验收：`http://localhost:5000/` 已加载版本 32，新模板包含 `log-chat` 与 `starting_action`。

当前前端版本：`32`。

## NPC 观察/记忆/认知升级（2026-06-07）

权威计划：`docs/superpowers/plans/2026-06-07-npc-observation-memory-cognition.md`

当前状态：开发中，未收口，不能按完成项描述。

- [ ] 观察半径采用 `10`，并按可见/可听/公共/隐藏事实权限过滤观察事件。
- [ ] 决策前构建 observation packet，纳入当前周围事件、此前记忆、当前行动、目标、行动历史、公共状态、附近人物/物体和黑盒约束。
- [ ] 保持三条模型线：决策线、真实聊天线、后台记忆线；后台记忆线不阻塞行动/交谈/规划，也不制造蓝泡。
- [ ] 真实聊天从提交模型请求开始占用行动，到白泡消失才完成。
- [ ] `thought`/`plan` 作为真实认知输出进入记忆候选，但必须限长、限视角；`action_status` 必须 grounded，不得虚构不存在对象。

## 整局闭环补完（2026-06-07）

权威计划：`docs/superpowers/plans/2026-06-07-full-game-completion.md`

当前状态：已实现并进入验证提交。第一天白天流程冻结，本轮只从第一天夜晚开始补完整局。

- [x] 固定夜晚顺序：狼人阶段先执行，匿名银质小刀阶段后执行。
- [x] 银质小刀阶段每晚固定显示 60 秒，不因持刀人死亡、报废、已用或不用而缺失。
- [x] 支持同一夜两具尸体，并区分普通尸体与狼人尸体。
- [x] Day 2 / Day 3 早晨公告尸体并一圈讨论，白天必做采访，深挖和银器任务为可选。
- [x] Day 3 夜晚在工具和项链都收齐后制造一颗银质子弹。
- [x] Day 4 早晨讨论后直接投票，投票后进入最终胜负或银子弹射杀。
- [x] 前端补夜晚阶段、双尸体、狼人尸体、银子弹射杀 UI 和规则说明。
- [x] 相关测试、浏览器验收并提交。
## 2026-06-08 白天交谈 / 黄昏讨论 / 夜晚住处修复收口

- [x] 白天交谈：警长发问后可自由移动；目标 NPC 立即停止旧前端行动并显示 `...` 等回复；LLM provider 测试超时改为 30 秒；固定问句改为“你说说，为什么你不可能是凶手？”。
- [x] 黄昏讨论：进入黄昏时清旧行动、旧气泡、旧路径和旧交谈锁；参与者唯一分散站位；讨论后台推进并避免慢模型卡住 UI；右侧不再显示 NPC 发言列表；黄昏/投票延迟 2 秒平移镜头到讨论区域。
- [x] 夜晚住处：Klaus、Maria、Jane、Mei 改为更分散的夜间住处，远离警长区域；Sam 和 Isabella 保留店铺后方住处特例。
- [x] 验证：前端版本 `39`；语法检查通过；相关 UI、住处、LLM provider、白天交谈和黄昏投票测试通过；内置浏览器确认版本 39 和新版模板已加载。

## 2026-06-08 白天交谈 / 黄昏投票 / 夜晚过场回归修复计划

执行计划：`docs/superpowers/plans/2026-06-08-day-dusk-night-regression-fix.md`

当前状态：已整理成计划，尚未执行修复，不能按完成项描述。

- [ ] 深挖灯泡在真实交谈气泡出现时立即消失；深挖次数耗尽不影响正常交谈按钮。
- [ ] 黄昏警长发言、投票和投票结果 UI 移出右侧/右下区域，统一改为屏幕中央弹窗。
- [ ] 投票后按钮立即禁用，票仓显示投票者头像，并在底部单独显示弃票者头像。
- [ ] 黄昏讨论禁止“先听警长/克罗”“我没意见”等划水式发言。
- [ ] 投票结束后先由克罗公布最高票，再让被投者原地发表遗言，气泡停留 6 秒后再押送。
- [ ] 夜晚镜头锁定克罗家，场景变暗但可见，玩家不能移动镜头。
- [ ] 夜晚窗口改为狼人进度条 + 银质小刀进度条两行，确认天亮按钮必须能进入第二天。
- [ ] 修复完成后必须报告前端版本、测试结果、浏览器验证结果和提交状态。
