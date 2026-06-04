# Werewolf Ville - 技术报告

## 1. 项目概述

### 1.1 项目名称
Werewolf Ville（狼人小镇）

### 1.2 设计目的
基于斯坦福 Smallville（Generative Agents）项目改造的**狼人杀推理游戏**。玩家扮演侦探 Crow，在一个有 6 个 AI 居民（5个NPC居民 + 1个侦探）的小镇中调查狼人身份。每个居民由大语言模型（LLM）驱动，拥有独立的记忆、认知和性格系统。玩家需要通过移动侦探、与居民对话、收集线索来推理出谁是狼人。

### 1.3 核心玩法
- **白天阶段**（30分钟真实时间）：侦探在小镇中移动，与居民对话收集线索
- **夜晚阶段**（5分钟真实时间）：狼人选择一名居民杀害，侦探无法行动
- **胜负条件**：侦探正确指认狼人则村民胜利；超过5天或村民几乎全灭则狼人胜利

### 1.4 技术栈
| 层级 | 技术 |
|------|------|
| 前端渲染 | Phaser 3（2D 像素风游戏引擎） |
| 前端通信 | Fetch API（轮询 `/api/status`） |
| 后端框架 | Flask + Flask-SocketIO |
| LLM 接口 | OpenAI 兼容 API（默认 DeepSeek） |
| 地图数据 | Tiled 地图编辑器导出 JSON + CSV |
| 角色美术 | 独立 Atlas PNG 精灵图（每个角色一张） |
| 运行环境 | Python 3.10 |

---

## 2. 项目架构

### 2.1 文件结构

```
werewolf-ville/
├── main.py                    # 入口：Web UI 或 CLI 模式
├── game_engine.py             # 游戏引擎：时间系统、状态调度、寻路、LLM 行为
├── agent.py                   # 智能体：MD 文件记忆/认知架构、对话生成
├── llm.py                     # LLM 封装：OpenAI 兼容 API 调用
├── config.yaml                # 全局配置
├── requirements.txt           # Python 依赖
├── personas/                  # 每个角色的 MD 文件
│   ├── Arthur_Burton/
│   │   ├── soul.md            # 角色灵魂（性格、背景）- 游戏中不变
│   │   ├── agent.md           # 当前任务/状态 - 频繁更新
│   │   ├── memory.md          # 记忆 - 按时间记录，旧记忆压缩
│   │   └── cognition.md       # 认知/反思 - 当前思考
│   ├── Crow/                  # 侦探额外有 notebook.md
│   └── ...
├── static/
│   └── assets/
│       ├── characters/        # 角色精灵图
│       │   ├── Arthur_Burton.png
│       │   ├── Crow.png
│       │   ├── atlas.json     # 共享动画帧定义
│       │   └── ...
│       └── the_ville/         # 地图资源
│           ├── visuals/       # Tiled 地图 JSON + 瓦片图片
│           └── matrix/maze/   # 碰撞迷宫 CSV
└── ui/
    ├── app.py                 # Flask 路由 + WebSocket
    └── templates/
        └── index.html         # 前端单页（Phaser + UI 面板）
```

### 2.2 核心模块关系

```
main.py
  └── ui/app.py (Flask)
        ├── game_engine.py (游戏引擎)
        │     ├── agent.py (智能体)
        │     │     └── llm.py (LLM 调用)
        │     └── collision_maze (寻路)
        └── index.html (Phaser 前端)
```

---

## 3. 已完成的工作

### 3.1 游戏引擎（game_engine.py）

#### 3.1.1 时间系统
- **白天**：30分钟真实时间 = 17小时游戏时间（7:00-24:00）
- **夜晚**：5分钟真实时间，自动过渡到白天
- **Tick 机制**：每5秒一个 tick，更新所有智能体状态

#### 3.1.2 碰撞迷宫连通性修复
**问题**：原始 `collision_maze.csv` 将地图分割成多个不连通区域（建筑墙壁没有门），导致 BFS 寻路总是失败，角色只能穿墙直线移动。

**解决方案**：新增 `_connect_maze_regions()` 函数，在加载碰撞迷宫后自动打通区域间的墙壁：
1. 用 flood_fill 检测所有连通区域
2. 按大小排序，将所有小区域与最大区域连通
3. 在每个小区域边界找到最短墙壁，打通2格宽的通道（模拟门/入口）
4. 打通后地图 11952/11952 格全部连通

#### 3.1.3 BFS 寻路优化
**问题**：原 BFS `max_steps=500` 太小，大地图上搜索不到路径；且每个节点存储完整路径列表，内存浪费严重。

**解决方案**：
- `max_steps` 从 500 增大到 50000
- 改用 parent map 回溯路径，避免每个节点存储完整路径
- BFS 失败时直接传送到目标位置（兜底策略）

#### 3.1.4 角色移动系统
- 所有角色使用 BFS 寻路避墙移动
- 每 tick 移动 8 格（加速移动）
- 侦探被玩家操控时跳过日程更新
- NPC 按硬编码日程移动到各地点

#### 3.1.5 LLM 驱动的 NPC 行为
**问题**：NPC 行为完全由硬编码日程驱动，没有大模型参与，缺乏智能。

**解决方案**：新增 `_llm_tick()` 方法，每6个 tick（约30秒）触发一次 LLM 调用：
- **NPC 反思**：轮询选择 NPC，调用 `agent.reflect()` 生成内心独白
- **NPC 主动对话**：检测同位置角色，30% 概率触发 LLM 对话
- **狼人 LLM 选目标**：夜间杀人使用 `werewolf_choose_target()` 而非随机选择
- 所有 LLM 调用异步执行（`threading.Thread`），不阻塞游戏主循环

#### 3.1.6 日志分类系统
日志条目添加 `type` 字段，分为5类：
| 类型 | 说明 | 前端显示 |
|------|------|----------|
| `system` | 移动、日程等系统日志 | 不显示 |
| `think` | LLM 思考/反思 | 显示（紫色斜体） |
| `chat` | LLM 对话 | 显示（绿色） |
| `kill` | 杀人事件 | 显示（红色加粗） |
| `memory` | 记忆/状态更新 | 显示（蓝色） |

#### 3.1.7 侦探出生位置修复
**问题**：侦探 Crow 出生在 (69, 8)（地图顶部森林），被墙壁围住无法移动。

**解决方案**：将 Crow 的家改到 (67, 31)（Hobbs Cafe 旁边，镇中心区域），确保出生在可通行且连通的区域。

### 3.2 智能体系统（agent.py）

#### 3.2.1 MD 文件记忆架构
每个角色有4个核心 MD 文件：
- **soul.md**：角色灵魂（性格、背景、信仰、恐惧）- 游戏中不变
- **agent.md**：当前任务/状态 - 频繁更新（通过 `update_agent()` 用 LLM 更新）
- **memory.md**：记忆 - 按时间记录，旧记忆自动压缩
- **cognition.md**：认知/反思 - 当前思考

侦探额外有 **notebook.md**：详细对话记录，不衰减。

#### 3.2.2 对话系统
- `generate_response()`：基于 soul + agent + memory + cognition 生成对话回复
- 狼人有角色提示（伪装成普通居民）
- 侦探有角色提示（调查狼人案件）
- 对话自动记录到 memory，侦探额外记录到 notebook

#### 3.2.3 记忆压缩
- `compress_memory()`：保留最近1天的完整记录，更早的压缩为摘要
- `compress_notebook()`：侦探笔记压缩比例更高（保留更多细节）

#### 3.2.4 狼人决策
- `werewolf_choose_target()`：LLM 选择杀人目标（优先落单居民，不杀侦探）
- `detective_deduce()`：侦探推理（综合笔记和认知判断狼人）
- `detective_announce()`：侦探宣布推理结果

### 3.3 前端（index.html）

#### 3.3.1 Phaser 3 游戏渲染
- 加载 Tiled 地图（the_ville_jan7.json）
- 9个图层渲染（地面、外墙、装饰、家具等）
- 角色精灵使用独立 Atlas PNG（每个角色一张精灵图 + 共享 atlas.json）
- 行走动画：4方向各4帧（left/right/up/down walk）

#### 3.3.2 相机控制
- **WASD / 方向键**：直接控制相机滚动（每帧8像素）
- **鼠标右键/中键拖拽**：拖拽移动相机
- **左键点击**：移动侦探到目标位置
- 相机边界限制在地图范围内
- 初始位置：小镇中心 (60, 30)

#### 3.3.3 角色显示
- 每个角色使用独立 PNG 精灵图（`PERSONA_ASSET_KEYS` 映射角色名到资源 key）
- 角色初始隐藏，第一次收到 gameState 后直接传送到初始位置
- 平滑移动：每帧4像素，带方向动画
- 死亡角色变灰（`setTint(0x666666)`）
- 名字标签 + 动作气泡

#### 3.3.4 鼠标坐标显示
- 鼠标在地图上移动时，左上角显示 Tile 坐标和 Pixel 坐标
- 格式：`Tile: (x, y)  Pixel: (px, py)`
- 鼠标离开游戏区域时自动隐藏
- 用于调试和选择位置坐标

#### 3.3.5 日志过滤
- 前端只显示 `think`、`chat`、`kill`、`memory` 类型的日志
- `system` 类型（移动、日程等）被过滤掉
- 不同类型用不同颜色和图标区分

#### 3.3.6 UI 面板
- **右侧面板**：时间显示、角色列表、对话面板、宣布按钮
- **底部日志**：只显示 LLM 相关日志
- **游戏结束遮罩**：显示胜负结果

### 3.4 后端 API（app.py）

| API | 方法 | 说明 |
|-----|------|------|
| `/api/status` | GET | 获取完整游戏状态（轮询） |
| `/api/start` | POST | 开始新游戏 |
| `/api/enter_night` | POST | 进入夜晚 |
| `/api/move_detective` | POST | 移动侦探 |
| `/api/detective_chat` | POST | 侦探与居民对话 |
| `/api/detective_announce` | POST | 侦探宣布推理结果 |
| `/api/agent/<name>` | GET | 获取角色详细信息 |
| `/api/reset` | POST | 重置游戏 |
| `/api/collision_maze` | GET | 获取碰撞迷宫数据 |

---

## 4. 关键技术决策

### 4.1 为什么用 MD 文件而非数据库
- 与原 Stanford Smallville 项目保持一致
- 方便调试：直接打开文件查看角色状态
- LLM 读写自然语言文本比结构化数据更自然

### 4.2 为什么 BFS 而非 A* 寻路
- 地图只有 140x100 格，BFS 足够快
- BFS 保证最短路径，实现简单
- A* 需要设计启发函数，对格子地图收益不大

### 4.3 为什么 LLM 调用异步
- 单次 LLM 调用可能需要 2-5 秒
- 同步调用会阻塞游戏主循环，导致所有角色卡住
- 异步线程保证游戏流畅运行

### 4.4 为什么轮询而非 WebSocket 推送
- 前端当前使用 Fetch 轮询 `/api/status`
- 实现简单，不需要维护 WebSocket 连接状态
- 后端已配置 SocketIO，未来可切换为推送模式

---

## 5. 已知问题与待改进

### 5.1 已知问题
1. **角色美术资源**：当前10个角色中，部分角色使用相同的精灵图（原项目有25个角色25套美术资源，当前只用了10个），需要为每个角色使用不同的美术资源
2. **NPC 日程与 LLM 冲突**：NPC 同时受硬编码日程和 LLM 反思驱动，可能出现行为不一致（日程让 NPC 去 Cafe，LLM 反思后想去 Pub）
3. **LLM 调用频率**：当前每30秒只调用一个 NPC 的 LLM，10个 NPC 全部反思一轮需要5分钟，可能不够频繁
4. **碰撞迷宫打通位置**：自动打通的通道可能不在合理位置（如打通了建筑外墙中间而非门口）

### 5.2 待改进
1. **增加角色数量**：从10个扩展到25个，匹配原项目的角色规模
2. **LLM 驱动日程**：让 NPC 的日程也由 LLM 决定，而非硬编码
3. **侦探推理辅助**：添加侦探自动推理功能，根据收集的线索生成推理报告
4. **UI 改进**：添加小地图、角色详情面板、线索板等
5. **WebSocket 推送**：替换轮询为 WebSocket 推送，减少延迟
6. **碰撞迷宫手动修正**：在自动打通的基础上，手动调整通道位置到建筑门口

---

## 6. 运行指南

### 6.1 环境要求
- Python 3.10+
- 本地运行 LLM API（默认 `http://127.0.0.1:8000/v1`，兼容 OpenAI 格式）

### 6.2 启动步骤
```bash
cd werewolf-ville
pip install -r requirements.txt
python main.py
```
浏览器打开 `http://127.0.0.1:5000`

### 6.3 配置修改
编辑 `config.yaml`：
- `llm.api_base`：修改 LLM API 地址
- `llm.model`：修改模型名称
- `game.day_duration_seconds`：修改白天时长
- `game.agent_count`：修改智能体数量
- `werewolf.character`：修改狼人角色
- `detective.character`：修改侦探角色

---

## 7. 角色配置

### 7.1 当前6个角色

| 角色 | 家坐标 | 身份 | 日程概要 |
|------|--------|------|----------|
| Arthur Burton | (78,32) | 狼人 | 酒吧工作 |
| Crow | (67,31) | 侦探 | 调查小镇 |
| Isabella Rodriguez | (66,30) | 村民 | 经营 Hobbs Cafe |
| Klaus Mueller | (127,46) | 村民 | 大学学习 |
| Maria Lopez | (123,57) | 村民 | 大学学习 |
| Sam Moore | (45,18) | 村民 | 公园散步、市场 |

### 7.2 地图关键位置

| 地点 | 坐标 |
|------|------|
| Hobbs Cafe | (66, 30) |
| The Rose and Crown Pub | (78, 32) |
| The Willows Market | (50, 42) |
| Oak Hill College | (125, 50) |
| Harvey Oak Supply | (40, 25) |
| The Studio | (85, 20) |
| Town Square | (70, 40) |
| Park | (55, 15) |

---

## 8. 修改历史

### 第一轮修改（基础功能修复）
1. 修复屏幕无法移动：重构相机控制，实现 WASD/方向键 + 鼠标拖拽
2. 修复侦探无法操控：添加左键点击地图移动侦探
3. 角色美术差异化：每个角色加载独立 PNG 精灵图
4. 角色初始位置：首次收到状态时直接传送到初始位置，不穿墙移动

### 第二轮修改（LLM 驱动 + 日志优化）
1. NPC 添加 LLM 反思：每30秒轮询一个 NPC 进行 LLM 反思
2. NPC 主动对话：同位置角色30%概率触发 LLM 对话
3. 狼人 LLM 选目标：夜间杀人使用 LLM 决策
4. 日志分类过滤：只显示 LLM 思考/对话/记忆日志，过滤移动日志
5. 修复 `_check_proximity_chats` 引用错误导致游戏循环崩溃

### 第三轮修改（寻路系统重构）
1. 碰撞迷宫连通性修复：`_connect_maze_regions()` 自动打通区域间墙壁
2. BFS 寻路优化：`max_steps` 500→50000，改用 parent map 回溯
3. 移动速度提升：每 tick 3格→8格
4. 侦探出生位置修复：(69,8)→(67,31)
5. 鼠标坐标显示：左上角实时显示 Tile/Pixel 坐标
6. 前端坐标转换修复：`pointer.positionToCamera()` → `camera.getWorldPoint()`
