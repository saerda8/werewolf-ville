"""
智能体系统 - 基于 MD 文件的记忆与认知架构

每个智能体包含:
- soul.md:      角色灵魂（性格、背景、信仰、恐惧）- 游戏中不变
- agent.md:     当前任务（目标、计划、当前状态）- 频繁更新
- memory.md:    记忆（按时间记录，旧记忆自动压缩）
- cognition.md: 认知+反思（当前思考、推理、判断）
- memory_index.json: 结构化记忆索引（带时间戳、重要性分数，用于检索）

侦探额外有:
- notebook.md:  详细对话记录，不衰减
"""
import os
import sys
import json as _json
import time as _time
import math
import threading
import uuid
from llm import chat, chat_for_agent, get_model_for_agent, get_last_error_for_agent
from config_loader import load_config, get_config
from utils import safe_truncate, tokenize_chinese
from world_config import ACTIVE_CHARACTERS, display_name_for_person


CONFIG = load_config()
PERSONAS_DIR = os.path.join(os.path.dirname(__file__), "personas")


def active_town_people_rule() -> str:
    people = "、".join(
        display_name_for_person(name) for name in ACTIVE_CHARACTERS.keys()
    )
    return (
        "人物边界：这个小镇当前只有以下8个可行动人物："
        f"{people}。所有对外发言只能使用这些中文名字，不要说英文名、全名或内部代号。"
        "不得编造、提及或引用名单外的人名；如果需要说“其他人”，"
        "只能说“其他镇民/路人”，不要给他们起名字。"
    )


class Agent:
    """狼人小镇智能体"""

    def __init__(self, name: str, role: str = "villager", model: str = None):
        self.name = name
        self.role = role
        self.model = model if model else get_model_for_agent(name)  # 前端要显示
        self.folder = os.path.join(PERSONAS_DIR, name.replace(" ", "_"))
        os.makedirs(self.folder, exist_ok=True)

        # 文件锁：防止多线程并发读写 MD 文件
        self._file_lock = threading.Lock()

        # 对话状态锁定：正在和谁交谈，None 表示空闲
        self.in_conversation_with = None
        self._conversation_lock = threading.Lock()

        # 对话状态
        self.chat_count = {}
        self.dialogue_history = []
        self.deep_dive_used = 0
        self.deep_dive_quota = 0
        self.is_alive = True

        # 位置与移动
        self.x = 0
        self.y = 0
        self.target_x = 0
        self.target_y = 0
        self.current_action = ""
        self.current_action_type = ""
        self.current_emoji = ""
        self.current_location = ""
        self.runtime_state = "idle"
        self._pending_action = {}
        self._last_decision = {}
        self._last_raw_response = ""
        self._last_response_error = ""

        # 寻路控制
        self._llm_decided = False
        self._last_llm_decision_time = 0
        self.current_thought = ""
        self.current_thought_time = 0

        # 记忆索引（结构化存储，用于检索）
        self.memory_index = self._load_memory_index()

        # 每日计划
        self.daily_plan = []  # [{"hour": 7, "location": "Hobbs Cafe", "action": "opening cafe"}, ...]
        self.plan_day = 0     # 当前计划对应的天数

        # 空间记忆树（NPC知道每个地点有什么物件）
        self.spatial_memory = self._load_spatial_memory()

        # Scratch（结构化短期状态）
        self.scratch = self._load_scratch()

        # 行动历史（防止重复行为循环，最多保留5条）
        self.action_history = []

        # 可访问性控制：每个角色不能进入其他人的家
        self.accessible_sectors = self._init_accessible_sectors()

    def get_runtime_role_prompt(self) -> str:
        if self.role == "detective":
            return "Role: You are the detective. Find the werewolf through evidence."
        elif self.role == "werewolf":
            return "Role: You are the werewolf. Blend in, hide your traces, and kill one non-Crow resident per night, Crow last."
        else:
            return "Role: You are a villager. Live your normal life first, investigate factual clues second, and report clues/suspicions to Crow."

    # ==================== 记忆索引 ====================

    def _load_memory_index(self) -> list:
        """加载记忆索引文件"""
        path = os.path.join(self.folder, "memory_index.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return _json.load(f)
            except Exception:
                return []
        return []

    def _save_memory_index(self):
        """保存记忆索引文件"""
        path = os.path.join(self.folder, "memory_index.json")
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(self.memory_index, f, ensure_ascii=False, indent=2)

    # ==================== Typed Memory Index ====================

    def _load_typed_memory_index(self) -> list:
        """加载类型化记忆索引文件 typed_memory_index.json"""
        path = os.path.join(self.folder, "typed_memory_index.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return _json.load(f)
            except Exception:
                return []
        return []

    def _save_typed_memory_index(self, index: list):
        """保存类型化记忆索引文件 typed_memory_index.json"""
        path = os.path.join(self.folder, "typed_memory_index.json")
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(index, f, ensure_ascii=False, indent=2)

    def _score_importance(self, event: str) -> int:
        """重要性打分 1-10（纯规则打分，避免同步 LLM 调用阻塞）"""
        # 极高优先级事件
        critical_keywords = ["死亡", "被杀", "杀害", "狼人", "尸体", "杀人"]
        for kw in critical_keywords:
            if kw in event:
                return 10

        # 高优先级事件
        high_keywords = ["失踪", "恐惧", "发现", "真相", "嫌疑", "线索", "证据", "可疑"]
        score = 3  # 默认低分
        for kw in high_keywords:
            if kw in event:
                score = max(score, 8)

        # 中优先级事件
        medium_keywords = ["对话", "聊天", "提到", "听说", "看到", "去了", "来到", "告别", "离开"]
        for kw in medium_keywords:
            if kw in event:
                score = max(score, 5)

        # 角色特殊加分
        if self.role == "werewolf" and any(kw in event for kw in ["变身", "夜晚", "杀人", "目标"]):
            score = max(score, 9)
        if self.role == "detective" and any(kw in event for kw in ["线索", "推理", "证据", "可疑"]):
            score = max(score, 8)

        return min(score, 10)

    def _llm_score_importance(self, event: str) -> int:
        """LLM精确打分：事件对角色的重要性 1-10"""
        prompt = f"""请评估以下事件对{self.name}（{self.role}）的重要性，1-10分。
1=完全不重要（日常琐事），10=极其重要（生死攸关）

事件：{event}

只输出一个数字："""
        try:
            resp = chat_for_agent(self.name, "你是一个事件重要性评估器。只输出1-10的数字。", prompt, temperature=0.1)
            score = int(resp.strip().split()[0])
            return max(1, min(10, score))
        except Exception:
            return 0

    def add_memory(self, event: str, day: int):
        """追加记忆到 memory.md + 更新记忆索引"""
        entry = f"\n### [第{day}天] {event}\n"
        self._append_md("memory.md", entry)

        # 更新索引
        importance = self._score_importance(event)
        self.memory_index.append({
            "day": day,
            "event": event,
            "importance": importance,
            "timestamp": _time.time(),
        })
        self._save_memory_index()

    def add_typed_memory(self, *, memory_type: str = "", type: str = "event", day: int = 0, game_hour: float = 0,
                          subject: str = "", predicate: str = "", object: str = "", text: str = "",
                          importance: int = None, keywords: list = None,
                          evidence=None, source: str = "", visibility: str = "private", **_extra) -> str:
        """添加结构化类型化记忆，支持 thought/plan/chat 等类型未来检索。

        字段：id/type/created_at/day/game_hour/subject/predicate/object/text/
              importance/keywords/evidence/source/visibility
        解析异常安全降级，新旧记录兼容。
        """
        # 安全解析：类型只允许特定值
        allowed_types = {"event", "chat", "thought", "plan"}
        requested_type = memory_type or type
        memory_type = requested_type if requested_type in allowed_types else "event"

        # 安全解析：重要性
        if importance is None:
            importance = self._score_importance(text or "")
        try:
            importance = max(1, min(10, int(importance)))
        except (TypeError, ValueError):
            importance = self._score_importance(text or "")

        # 安全解析：keywords
        if keywords is None:
            keywords = []
        elif isinstance(keywords, str):
            keywords = [keywords]
        elif not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if str(k).strip()]

        # 安全解析：visibility
        allowed_visibility = {"public", "private", "witnessed"}
        if visibility not in allowed_visibility:
            visibility = "private"

        if isinstance(evidence, str):
            evidence = [evidence] if evidence.strip() else []
        elif not isinstance(evidence, list):
            evidence = []
        evidence = [str(item).strip() for item in evidence if str(item).strip()]

        entry = {
            "id": str(uuid.uuid4()),
            "type": memory_type,
            "created_at": _time.time(),
            "day": day,
            "game_hour": game_hour,
            "subject": str(subject or "").strip(),
            "predicate": str(predicate or "").strip(),
            "object": str(object or "").strip(),
            "text": str(text or "").strip(),
            "importance": importance,
            "keywords": keywords,
            "evidence": evidence,
            "source": str(source or "").strip(),
            "visibility": visibility,
        }

        # 同时追加到旧索引（兼容检索）
        self.memory_index.append({
            "day": day,
            "event": text or "",
            "importance": importance,
            "timestamp": entry["created_at"],
            "type": memory_type,
        })
        self._save_memory_index()

        # 追加到 memory.md（完整文本）
        if text:
            self._append_md("memory.md", f"\n### [第{day}天] {text}\n")

        # 保存 typed memory 索引
        typed_index = self._load_typed_memory_index()
        typed_index.append(entry)
        self._save_typed_memory_index(typed_index)

        return entry["id"]

    def retrieve_memories(self, query: str, top_k: int = 10) -> list:
        """
        三重打分检索：Recency + Relevance + Importance
        返回最相关的 top_k 条记忆
        """
        if not self.memory_index:
            return []

        now = _time.time()
        scored = []

        for entry in self.memory_index:
            # 1. Recency: 指数衰减，越近越高
            age_hours = (now - entry["timestamp"]) / 3600
            recency = math.exp(-0.1 * age_hours)  # 半衰期约7小时

            # 2. Relevance: 按词分割后计算关键词重叠度
            query_words = set(tokenize_chinese(query))
            event_words = set(tokenize_chinese(entry["event"]))
            overlap = len(query_words & event_words)
            relevance = min(overlap / max(len(query_words), 1), 1.0)

            # 3. Importance: 归一化到 0-1
            importance = entry["importance"] / 10.0

            # 加权求和
            total = 0.5 * recency + 0.3 * relevance + 0.2 * importance
            scored.append((total, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def get_retrieved_memory_text(self, query: str, max_chars: int = 800) -> str:
        """检索相关记忆并格式化为文本"""
        entries = self.retrieve_memories(query, top_k=15)
        if not entries:
            return safe_truncate(self.read_memory(), max_chars)

        lines = []
        total_len = 0
        for entry in entries:
            line = f"[第{entry['day']}天] {entry['event']}"
            if total_len + len(line) > max_chars:
                break
            lines.append(line)
            total_len += len(line)

        return "\n".join(lines) if lines else safe_truncate(self.read_memory(), max_chars)

    # ==================== 空间记忆树 ====================

    def _load_spatial_memory(self) -> dict:
        """加载空间记忆树"""
        path = os.path.join(self.folder, "spatial_memory.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return _json.load(f)
            except Exception:
                return {}
        return {}

    def _save_spatial_memory(self):
        """保存空间记忆树"""
        path = os.path.join(self.folder, "spatial_memory.json")
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(self.spatial_memory, f, ensure_ascii=False, indent=2)

    def build_spatial_memory(self, sector_maze, arena_maze, go_maze,
                             sector_dict, arena_dict, go_dict):
        """从场景数据构建空间记忆树：{sector: {arena: [objects]}}
        已废弃：请使用 load_shared_spatial_memory 加载引擎预扫描结果"""
        from game_engine import get_tile_scene

        tree = {}
        for y in range(100):
            for x in range(140):
                info = get_tile_scene(x, y, sector_maze, arena_maze, go_maze,
                                      sector_dict, arena_dict, go_dict)
                sector = info["sector"]
                arena = info["arena"]
                objects = info["game_objects"]
                if not sector:
                    continue
                if sector not in tree:
                    tree[sector] = {}
                if arena and arena not in tree[sector]:
                    tree[sector][arena] = set()
                for obj in objects:
                    if obj:
                        if not arena:
                            if "_default" not in tree[sector]:
                                tree[sector]["_default"] = set()
                            tree[sector]["_default"].add(obj)
                        else:
                            tree[sector][arena].add(obj)

        # set → list for JSON serialization
        for sector in tree:
            for arena in tree[sector]:
                tree[sector][arena] = sorted(list(tree[sector][arena]))

        self.spatial_memory = tree
        self._save_spatial_memory()

    def load_shared_spatial_memory(self, shared_tree: dict):
        """加载引擎预扫描的空间记忆（深拷贝，每个角色独立过滤）"""
        import copy
        self.spatial_memory = copy.deepcopy(shared_tree)
        self._save_spatial_memory()

    def get_location_description(self, location_name: str) -> str:
        """获取NPC记忆中某地点的描述（用于prompt）"""
        if not self.spatial_memory:
            return ""

        # 尝试匹配地点名
        for sector, arenas in self.spatial_memory.items():
            if location_name.lower() in sector.lower() or sector.lower() in location_name.lower():
                parts = []
                for arena_name, objects in arenas.items():
                    arena_short = arena_name.split(",")[-1].strip() if "," in arena_name else arena_name
                    if objects:
                        parts.append(f"{arena_short}有{'、'.join(objects)}")
                if parts:
                    return f"{sector}：{'；'.join(parts)}"
                return f"{sector}"

        return ""

    # ==================== Scratch（结构化短期状态）====================

    @staticmethod
    def _default_scratch() -> dict:
        return {
            "vision_r": 5,           # 视觉范围（格）
            "att_bandwidth": 3,      # 注意力带宽（同时关注几人）
            "retention": 5,          # 记忆保留强度（1-10）
            "daily_plan_req": "",    # 每日计划要求
            "innate": "",            # 天生特质
            "learned": "",           # 习得特质
            "currently": "",         # 当前目标
            "lifestyle": "",         # 生活方式
            "fear": "",              # 当前恐惧
        }

    def _load_scratch(self) -> dict:
        """加载 scratch.json"""
        path = os.path.join(self.folder, "scratch.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return _json.load(f)
            except Exception:
                pass
        # 默认值
        return self._default_scratch()

    def _save_scratch(self):
        """保存 scratch.json"""
        path = os.path.join(self.folder, "scratch.json")
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(self.scratch, f, ensure_ascii=False, indent=2)

    def update_scratch(self, **kwargs):
        """更新 scratch 字段"""
        for key, value in kwargs.items():
            if key in self.scratch:
                self.scratch[key] = value
        self._save_scratch()

    def init_scratch_from_soul(self):
        """从 soul.md 初始化 scratch 的 innate/learned/fear 等字段"""
        soul = self.read_soul()
        if not soul:
            return

        # 提取性格作为 innate
        innate = ""
        for line in soul.split("\n"):
            if "性格" in line:
                # 取性格段落
                parts = soul.split("## 性格")
                if len(parts) > 1:
                    innate = parts[1].split("##")[0].strip()[:200]
                break

        # 提取恐惧
        fear = ""
        for line in soul.split("\n"):
            if "恐惧" in line:
                parts = soul.split("## 恐惧")
                if len(parts) > 1:
                    fear = parts[1].split("##")[0].strip()[:100]
                break

        # 提取信仰作为 learned
        learned = ""
        for line in soul.split("\n"):
            if "信仰" in line:
                parts = soul.split("## 信仰")
                if len(parts) > 1:
                    learned = parts[1].split("##")[0].strip()[:200]
                break

        # 生活方式
        lifestyle = ""
        if self.role == "werewolf":
            lifestyle = "白天伪装成普通居民，夜晚变身"
        elif self.role == "detective":
            lifestyle = "调查狼人案件，收集线索"

        self.update_scratch(
            innate=innate or "普通小镇居民",
            learned=learned or "无特殊习得特质",
            fear=fear or "无特殊恐惧",
            lifestyle=lifestyle or "小镇日常生活",
            currently="",
        )

    # ==================== 可访问性控制 ====================

    def _init_accessible_sectors(self) -> set:
        """初始化可访问区域：公共区域 + 自己的家"""
        # 公共区域（所有人可进）
        public_sectors = {
            "Hobbs Cafe", "The Rose and Crown Pub", "The Willows Market",
            "Oak Hill College", "Harvey Oak Supply", "Johnson Park",
        }

        # 每个角色的家（只有自己能进）
        home_mapping = {
            "Arthur Burton": "Lin family's house",
            "Crow": "Tamara Taylor and Carmen Ortiz's house",
            "Isabella Rodriguez": "Moreno family's house",
            "Klaus Mueller": "Adam Smith's house",
            "Maria Lopez": "Yuriko Yamamoto's house",
            "Sam Moore": "Moore family's house",
            "Jane Moreno": "Carlos Gomez's apartment",
            "Mei Lin": "Giorgio Rossi's apartment",
        }

        accessible = set(public_sectors)
        # 自己的家可以进
        my_home = home_mapping.get(self.name, "")
        if my_home:
            accessible.add(my_home)
        # home 总是可以进
        accessible.add("home")

        return accessible

    def can_access_location(self, location_name: str) -> bool:
        """检查角色是否可以进入某地点"""
        if location_name == "home":
            return True
        # 检查是否在可访问列表中
        for sector in self.accessible_sectors:
            if location_name.lower() in sector.lower() or sector.lower() in location_name.lower():
                return True
        # 公共区域总是可以
        public_sectors = {"Hobbs Cafe", "The Rose and Crown Pub", "The Willows Market",
                          "Oak Hill College", "Harvey Oak Supply", "Johnson Park"}
        for ps in public_sectors:
            if location_name.lower() in ps.lower() or ps.lower() in location_name.lower():
                return True
        return False

    def filter_accessible_locations(self, locations: list) -> list:
        """过滤出角色可访问的地点列表"""
        return [loc for loc in locations if self.can_access_location(loc)]

    def sanitize_prompt_text(self, text: str) -> str:
        """非狼人角色动态替换狼人相关敏感词（信息隔离）"""
        if not text:
            return ""
        if self.role == "werewolf":
            return text
        # 替换规则
        replacements = {
            "狼人杀手": "杀手",
            "狼人案件": "连环失踪与死亡案",
            "狼人杀": "杀人推理",
            "指认狼人": "指认凶手",
            "找出狼人": "找出凶手",
            "谁是狼人": "谁是凶手",
            "她是狼人": "她是凶手",
            "他是狼人": "他是凶手",
            "判断狼人": "判断凶手",
            "狼人身份": "杀手身份",
            "狼人的日常": "凶手的日常",
            "狼人": "凶手",
            "werewolf": "killer",
            "Werewolf": "Killer"
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return text

    # ==================== MD 文件 I/O ====================

    def _read_md(self, filename: str) -> str:
        with self._file_lock:
            filepath = os.path.join(self.folder, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()
            return ""

    def _write_md(self, filename: str, content: str):
        with self._file_lock:
            filepath = os.path.join(self.folder, filename)
            tmp_path = filepath + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, filepath)

    def _write_json(self, filename: str, content):
        with self._file_lock:
            filepath = os.path.join(self.folder, filename)
            tmp_path = filepath + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                _json.dump(content, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, filepath)

    def _append_md(self, filename: str, content: str):
        with self._file_lock:
            filepath = os.path.join(self.folder, filename)
            tmp_path = filepath + ".tmp"
            existing = ""
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = f.read()
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(existing + "\n" + content)
            os.replace(tmp_path, filepath)

    # ==================== Soul ====================

    def read_soul(self) -> str:
        return self._read_md("soul.md")

    # ==================== Agent (当前任务/状态) ====================

    def read_agent(self) -> str:
        return self._read_md("agent.md")

    def write_agent(self, content: str):
        self._write_md("agent.md", content)

    def update_agent(self, new_info: str):
        """LLM更新agent.md：读当前 → LLM根据新事件更新 → 写回"""
        current = self.read_agent()
        soul = self.read_soul()
        system_prompt = f"""你是{self.name}的内心状态管理器。
根据新发生的事情，更新角色的当前状态、目标和计划。
保持简洁，只记录重要信息。输出完整的更新后的内容（Markdown格式）。

硬性边界：
- 不得改变角色在灵魂文件中的职业、身份、主要生活场所和长期信念。
- 不得编造小镇名单外的人名。
- 对玩家可见的人名使用中文名，不要输出英文全名。
- 如果新信息与灵魂文件冲突，以灵魂文件为准，只更新短期状态。"""
        user_prompt = f"灵魂文件（不可改写，只能作为边界）:\n{soul}\n\n当前状态:\n{current}\n\n新发生的事情:\n{new_info}\n\n请输出更新后的完整状态："
        updated = chat_for_agent(self.name, system_prompt, user_prompt)
        if updated:
            self.write_agent(updated)

    # ==================== Memory ====================

    def read_memory(self) -> str:
        return self._read_md("memory.md")

    def write_memory(self, content: str):
        self._write_md("memory.md", content)

    def compress_memory(self, current_day: int):
        """LLM压缩旧记忆：最近 retain_full_days 天不动，更早的摘要化。同步清理索引。"""
        memory = self.read_memory()
        if not memory:
            return

        retain_days = CONFIG["memory"]["retain_full_days"]

        system_prompt = f"""你是一个记忆压缩器。请压缩以下角色的旧记忆。
规则：
1. 最近{retain_days}天的记忆保持原样，不要修改
2. 更早的记忆压缩为简短摘要，保留关键信息
3. 去掉琐碎细节，只保留：重要事件、关键对话、发现线索、人际关系变化
4. 保持 Markdown 格式
5. 输出完整的压缩后的记忆文件内容"""

        user_prompt = f"当前是第{current_day}天。以下是{self.name}的记忆：\n\n{memory}"
        compressed = chat_for_agent(self.name, system_prompt, user_prompt, temperature=0.3)
        if compressed and len(compressed) > 50:
            self.write_memory(compressed)
        else:
            print(f"[compress_memory] {self.name}: LLM 返回为空或过短({len(compressed) if compressed else 0}字)，"
                  f"保留原文不压缩", file=sys.stderr, flush=True)

        # 清理索引：保留最近 retain_days 天的条目，更早的只保留重要性>=7的
        if self.memory_index:
            before = len(self.memory_index)
            self.memory_index = [
                e for e in self.memory_index
                if e["day"] >= current_day - retain_days or e["importance"] >= 7
            ]
            if len(self.memory_index) < before:
                self._save_memory_index()

    # ==================== 每日反思 ====================

    def daily_reflection(self, day: int, dead_list: list) -> str:
        """每日反思总结：LLM 回顾今天所有经历，生成当日总结，覆盖写入 cognition.md。
        
        Args:
            day: 当前天数
            dead_list: 已死亡角色列表
        
        Returns:
            str: 反思内容，失败返回 ""。
        """
        if not CONFIG.get("memory", {}).get("daily_reflection_enabled", False):
            return ""

        soul = safe_truncate(self.read_soul(), 300)
        cognition = safe_truncate(self.read_cognition(), 500)
        retrieved = self.get_retrieved_memory_text(f"第{day}天 今天 经历", 800)
        agent_state = safe_truncate(self.read_agent(), 300)

        system_prompt = f"""你是 {self.name}，小镇居民。
你的灵魂：{soul}
你的当前状态：{agent_state}

请回顾你今天的经历，写一篇简短的个人日记式总结（100字以内），包括：
1. 今天你做了什么事情
2. 有什么重要的发现或事件
3. 你对明天的展望

用第一人称叙述。"""

        user_prompt = f"""今天是第{day}天。
已死亡的人：{', '.join(dead_list) if dead_list else '无人死亡'}。

你今天的记忆：
{retrieved}

你之前的思考：
{cognition}

请写出你今天结束时的总结反思："""

        thought = chat_for_agent(self.name, system_prompt, user_prompt)
        if thought and len(thought) > 20:
            # 新增时间戳前缀
            timestamp = _time.strftime("%Y-%m-%d %H:%M:%S")
            full_entry = f"# 第{day}天总结 ({timestamp})\n\n{thought}"
            self.write_cognition(full_entry)
        return thought or ""

    # ==================== Cognition ====================

    def read_cognition(self) -> str:
        return self._read_md("cognition.md")

    def write_cognition(self, content: str):
        self._write_md("cognition.md", content)

    def reflect(self, context: str) -> str:
        """实时反思：检索相关记忆 → LLM内心独白 → 追加到cognition.md（不覆盖）"""
        soul = safe_truncate(self.read_soul(), 300)
        agent_state = safe_truncate(self.read_agent(), 300)
        retrieved_memory = self.get_retrieved_memory_text(context, 600)
        cognition = safe_truncate(self.read_cognition(), 300)

        # 动态替换狼人相关词汇（信息隔离）
        soul_clean = self.sanitize_prompt_text(soul)
        agent_clean = self.sanitize_prompt_text(agent_state)
        retrieved_clean = self.sanitize_prompt_text(retrieved_memory)
        cognition_clean = self.sanitize_prompt_text(cognition)

        system_prompt = f"""你是{self.name}，一个生活在小镇中的居民。
你的灵魂：{soul_clean}
你的当前状态：{agent_clean}
{active_town_people_rule()}

请基于你的记忆和当前情况，进行思考和反思。
输出你的内心独白，包括：
1. 你对当前情况的理解
2. 你的疑虑和猜测
3. 你接下来想做什么

如果决定行动，必须严格按以下格式输出：
【行动】去[地点名]做什么，目标坐标(x, y)
【理由】为什么要去

纯思考（不涉及行动）只需输出简短文字即可。
总字数必须严格控制在100字以内，超出部分将被视为无效。请务必言简意赅！"""

        user_prompt = f"你的相关记忆：\n{retrieved_clean}\n\n你之前的思考：\n{cognition_clean}\n\n当前发生的事情：\n{self.sanitize_prompt_text(context)}\n\n请输出你现在的思考和反思："

        thought = chat_for_agent(self.name, system_prompt, user_prompt)
        if thought:
            self.current_thought = thought.strip()
            self.current_thought_time = _time.time()
            timestamp = _time.strftime("%H:%M:%S")
            entry = f"\n### [{timestamp}] 实时反思\n{thought}\n"
            self._append_md("cognition.md", entry)
            self.update_scratch(currently=thought[:100])
        return thought

    # ==================== Notebook (侦探专属) ====================

    def read_notebook(self) -> str:
        if self.role != "detective":
            return ""
        return self._read_md("notebook.md")

    def write_notebook(self, content: str):
        if self.role != "detective":
            return
        self._write_md("notebook.md", content)

    def add_notebook_entry(self, entry: str, day: int):
        """侦探笔记：详细记录，不衰减"""
        if self.role != "detective":
            return
        content = f"\n### [第{day}天] {entry}\n"
        self._append_md("notebook.md", content)

    def compress_notebook(self, current_day: int):
        """侦探笔记压缩：比普通压缩更细致"""
        if self.role != "detective":
            return
        notebook = self.read_notebook()
        if not notebook:
            return

        compression = CONFIG["detective"]["notebook_compression"]

        system_prompt = f"""你是侦探的笔记压缩器。请压缩侦探的旧笔记。
规则：
1. 最近2天的笔记保持原样
2. 更早的笔记压缩，但保留比普通记忆更多的细节（压缩比例{compression}）
3. 特别保留：对话中的关键陈述、时间线、矛盾点、线索
4. 保持 Markdown 格式"""

        user_prompt = f"当前是第{current_day}天。以下是侦探的笔记：\n\n{notebook}"
        compressed = chat_for_agent(self.name, system_prompt, user_prompt, temperature=0.3)
        if compressed:
            self.write_notebook(compressed)

    # ==================== 对话 ====================

    def can_chat_with(self, other_name: str, is_deep_dive: bool = False) -> bool:
        if self.role != "detective":
            return True
        count = self.chat_count.get(other_name, 0)
        limit = CONFIG["conversation"]["detective_normal_chat_limit"]
        if is_deep_dive:
            return self.deep_dive_used < self.deep_dive_quota
        return count < limit

    def record_chat(self, other_name: str, is_deep_dive: bool = False):
        # 仅首次对话计数，后续用 _chat_round_count 控制轮数
        if other_name not in self.chat_count:
            self.chat_count[other_name] = 1
        if is_deep_dive and self.role == "detective":
            self.deep_dive_used += 1

    def record_dialogue(self, partner_name: str, incoming: str, outgoing: str, day: int):
        entry = {
            "day": day,
            "partner": display_name_for_person(partner_name),
            "incoming": str(incoming or ""),
            "outgoing": str(outgoing or ""),
            "time": _time.time(),
        }
        self.dialogue_history.append(entry)
        self.dialogue_history = self.dialogue_history[-40:]

    def generate_response(self, partner_name: str, message: str, day: int,
                          priority: bool = False, max_retries: int = None) -> str:
        """检索相关记忆 → 构造prompt(含角色/狼人/侦探提示) → LLM → 记录memory → 侦探额外记notebook → 返回"""
        soul = safe_truncate(self.read_soul(), 300)
        agent_state = safe_truncate(self.read_agent(), 200)
        # 使用检索：以对话内容为查询
        query = f"{partner_name} {message}"
        retrieved_memory = self.get_retrieved_memory_text(query, 500)
        cognition = safe_truncate(self.read_cognition(), 200)

        # 动态过滤狼人词汇（信息隔离）
        soul_clean = self.sanitize_prompt_text(soul)
        agent_clean = self.sanitize_prompt_text(agent_state)
        retrieved_clean = self.sanitize_prompt_text(retrieved_memory)
        cognition_clean = self.sanitize_prompt_text(cognition)
        message_clean = self.sanitize_prompt_text(message)

        # 角色提示
        role_hint = f"\n重要：{self.get_runtime_role_prompt()}"

        self_display = display_name_for_person(self.name)
        partner_display = display_name_for_person(partner_name)
        system_prompt = f"""你是{self_display}，正在和{partner_display}对话。
你的灵魂：{soul_clean}
你的当前状态：{agent_clean}{role_hint}
{active_town_people_rule()}

规则：
1. 保持角色性格，自然对话
2. 根据你的记忆和认知来回应
3. 对话必须极其简洁自然，像真人聊天，且必须严格控制在60字以内，超出部分将被视为无效！"""

        user_prompt = f"你的相关记忆：\n{retrieved_clean}\n\n你的思考：\n{cognition_clean}\n\n{partner_display}对你说：{message_clean}\n\n请回复："

        response = chat_for_agent(
            self.name,
            system_prompt,
            user_prompt,
            priority=priority,
            max_retries=max_retries,
        )
        self._last_response_error = "" if response else "empty_response"

        # 记录到记忆
        self.record_dialogue(partner_name, message, response or "", day)
        self.add_memory(f"与{partner_display}对话 - {partner_display}说：{message[:100]} | 我回复：{(response or '')[:100]}", day)

        # 侦探额外记录到笔记
        if self.role == "detective":
            self.add_notebook_entry(
                f"与{partner_display}对话\n- {partner_display}说：{message}\n- 我回复：{response}", day
            )

        return response

    # ==================== 狼人专属 ====================

    def werewolf_choose_target(self, villagers: list, day: int) -> str:
        """LLM选目标：检索相关记忆 → 提示"优先落单/不杀侦探/避银器" → 返回名字"""
        if self.role != "werewolf":
            return ""

        soul = safe_truncate(self.read_soul(), 300)
        query = f"夜晚 杀人 目标 {' '.join(villagers)}"
        retrieved_memory = self.get_retrieved_memory_text(query, 400)
        cognition = safe_truncate(self.read_cognition(), 200)

        system_prompt = f"""你是狼人{self.name}，现在是夜晚，你需要选择一个目标来杀害。
你的灵魂：{soul}
{self.get_runtime_role_prompt()}
规则：
1. 优先选择独自一人、落单的居民
2. 只输出一个名字，不要解释"""

        user_prompt = f"你的相关记忆：\n{retrieved_memory}\n\n你的思考：\n{cognition}\n\n可选目标：{', '.join(villagers)}\n\n你选择杀谁？只输出名字："

        target = chat_for_agent(self.name, system_prompt, user_prompt, temperature=0.5)
        return target.strip()

    # ==================== 每日计划 ====================

    def generate_daily_plan(self, day: int) -> list:
        """LLM生成全天日程计划，返回计划列表"""
        if self.plan_day == day and self.daily_plan:
            return self.daily_plan  # 今天已生成过

        soul = safe_truncate(self.read_soul(), 300)
        query = f"计划 日程 {self.current_location}"
        retrieved_memory = self.get_retrieved_memory_text(query, 400)

        # 角色提示
        role_hint = self.get_runtime_role_prompt()

        system_prompt = f"""你是{self.name}，{role_hint}
你的性格：{soul}
你的相关记忆：{retrieved_memory}
{active_town_people_rule()}

请生成你今天（第{day}天）的日程计划。
规则：
1. 从7点到22点，每小时一个计划
3. 地点英文名必须是以下之一（括号内是中文对照）：
   - home (家/住处)
   - Hobbs Cafe (霍布斯咖啡馆)
   - The Rose and Crown Pub (玫瑰与王冠酒馆)
   - The Willows Market (柳树市场与药房)
   - Oak Hill College (橡树山学院)
   - Harvey Oak Supply (哈维橡树五金店)
   - Johnson Park (约翰逊公园)
   在 JSON 中的 location 必须填上述英文键名（例如 "Hobbs Cafe" 或 "home"），一字不差！
4. 动作要具体，比如"磨制铁器"而不是"工作"
5. 只输出JSON数组，不要其他内容"""

        user_prompt = f"""请输出今天的日程计划，格式如下：
[
  {{"hour": 7, "location": "home", "action": "起床洗漱"}},
  {{"hour": 8, "location": "Hobbs Cafe", "action": "吃早餐喝咖啡"}},
  ...
  {{"hour": 22, "location": "home", "action": "睡觉"}}
]

只输出JSON数组："""

        try:
            resp = chat_for_agent(self.name, system_prompt, user_prompt, temperature=0.7)
            if not resp:
                self.daily_plan = self._default_plan()
                self.plan_day = day
                return self.daily_plan

            resp = resp.strip()
            if resp.startswith("```"):
                resp = resp.split("```")[1]
                if resp.startswith("json"):
                    resp = resp[4:]
                resp = resp.strip()
            if resp.endswith("```"):
                resp = resp[:-3].strip()

            plan = _json.loads(resp)
            if isinstance(plan, list) and len(plan) > 0:
                self.daily_plan = plan
                self.plan_day = day
                # 记录到记忆
                plan_summary = "；".join([f"{p.get('hour', '?')}点在{p.get('location', '?')}{p.get('action', '')}" for p in plan[:5]])
                self.add_memory(f"制定了今日计划：{plan_summary}...", day)
                return self.daily_plan
        except Exception as e:
            print(f"[generate_daily_plan Error] {self.name}: {e}")

        self.daily_plan = self._default_plan()
        self.plan_day = day
        return self.daily_plan

    def _default_plan(self) -> list:
        """默认日程（LLM失败时使用）- 有目的的计划，不是散步闲逛"""
        role = getattr(self, 'role', 'villager')
        if role == "werewolf":
            return [
                {"hour": 7, "location": "home", "action": "起床，检查身上是否有异常痕迹"},
                {"hour": 8, "location": "Hobbs Cafe", "action": "去吃早餐，观察镇上的动静"},
                {"hour": 10, "location": "home", "action": "回家休息，准备晚上的行动"},
                {"hour": 12, "location": "Hobbs Cafe", "action": "吃午餐，听别人谈话"},
                {"hour": 14, "location": "Johnson Park", "action": "去公园散步，寻找目标"},
                {"hour": 16, "location": "The Rose and Crown Pub", "action": "去酒吧喝一杯，和居民聊天"},
                {"hour": 18, "location": "home", "action": "回家吃晚餐"},
                {"hour": 20, "location": "The Rose and Crown Pub", "action": "去酒吧散步，假装关心治安"},
                {"hour": 22, "location": "home", "action": "回家，锁门睡觉"},
            ]
        elif role == "detective":
            return [
                {"hour": 7, "location": "home", "action": "起床，整理调查笔记"},
                {"hour": 8, "location": "Hobbs Cafe", "action": "去咖啡馆观察居民动向"},
                {"hour": 10, "location": "Hobbs Cafe", "action": "去咖啡馆找人谈话"},
                {"hour": 12, "location": "Hobbs Cafe", "action": "午餐时和居民交流线索"},
                {"hour": 14, "location": "The Rose and Crown Pub", "action": "去酒吧打听消息"},
                {"hour": 16, "location": "Johnson Park", "action": "去公园观察谁行为异常"},
                {"hour": 18, "location": "The Willows Market", "action": "去市场询问商贩"},
                {"hour": 20, "location": "home", "action": "回家整理线索，更新笔记"},
                {"hour": 22, "location": "home", "action": "整理思路，休息"},
            ]
        else:
            return [
                {"hour": 7, "location": "home", "action": "起床洗漱，准备出门"},
                {"hour": 8, "location": "Hobbs Cafe", "action": "去咖啡馆买早餐"},
                {"hour": 10, "location": "The Willows Market", "action": "去市场采购日用品"},
                {"hour": 12, "location": "Hobbs Cafe", "action": "吃午餐，和朋友聊天"},
                {"hour": 14, "location": "Johnson Park", "action": "去公园散步，留意周围动静"},
                {"hour": 16, "location": "The Willows Market", "action": "去市场看看有没有新消息"},
                {"hour": 18, "location": "Hobbs Cafe", "action": "吃晚餐，讨论狼人传闻"},
                {"hour": 20, "location": "The Rose and Crown Pub", "action": "去酒吧放松，听人聊天"},
                {"hour": 22, "location": "home", "action": "回家锁门，早点休息保平安"},
            ]

    def get_current_plan_action(self, game_hour: int) -> dict:
        """根据当前小时获取计划中的行动"""
        if not self.daily_plan:
            return {}

        # 找到当前时间最近的计划
        best = self.daily_plan[0]
        for p in self.daily_plan:
            if p.get("hour", 0) <= game_hour:
                best = p
            else:
                break
        return best

    # ==================== 记忆整理 ====================

    @staticmethod
    def parse_memory_consolidation_result(raw: str) -> dict:
        """Parse memory-lane JSON into a stable shape."""
        default = {"memories": [], "current_goal": ""}
        if not raw:
            return default

        extracted = Agent._extract_json_text(str(raw))
        if not extracted:
            return default

        try:
            parsed = _json.loads(extracted)
        except Exception:
            return default
        if not isinstance(parsed, dict):
            return default

        allowed_types = {"event", "chat", "thought", "plan"}
        memories = []
        raw_memories = parsed.get("memories", [])
        if not isinstance(raw_memories, list):
            raw_memories = []

        for item in raw_memories:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            memory = dict(item)
            memory_type = str(memory.get("type", "event")).strip()
            memory["type"] = memory_type if memory_type in allowed_types else "event"
            try:
                importance = int(memory.get("importance", 1))
            except (TypeError, ValueError):
                importance = 1
            memory["importance"] = max(1, min(10, importance))
            keywords = memory.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [keywords]
            elif not isinstance(keywords, list):
                keywords = []
            memory["keywords"] = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
            for key in ("subject", "predicate", "object"):
                memory[key] = str(memory.get(key, "")).strip()
            memories.append(memory)

        return {
            "memories": memories,
            "current_goal": str(parsed.get("current_goal", "") or "").strip(),
        }

    @staticmethod
    def build_memory_consolidation_prompt(payload: dict, agent_name: str = "NPC") -> tuple[str, str]:
        try:
            payload_text = _json.dumps(payload or {}, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            payload_text = str(payload)

        system_prompt = f"""你是 {agent_name} 的 NPC 记忆整理模块。
只整理记忆，不决定行动。
输入可能包含：本轮观察、NPC 思考、计划、行动、行动结果、对话、旁观事件。
输出 JSON，memories 中的 type 只能是 event|chat|thought|plan。

规则：
- 不编造输入之外的事实，不补不存在的人、物、地点、关系或动机。
- 只沉淀对未来决策有用的事件、对话、想法、计划、怀疑、恐惧、关系、线索和身份风险。
- 隐藏身份事实只能在 NPC 知道或亲眼见证时写入；不能因为系统提示、角色真相或旁白而写入。
- 例行低价值动作可以低重要度记录，也可以省略。

只输出 JSON，不要解释。"""

        user_prompt = f"""请整理以下输入，输出格式固定为：
{{
  "memories": [
    {{
      "type": "event|chat|thought|plan",
      "text": "完整中文句子",
      "importance": 1,
      "keywords": ["关键词"],
      "subject": "主体",
      "predicate": "关系或动作",
      "object": "对象"
    }}
  ],
  "current_goal": "短期目标；没有则空字符串"
}}

输入：
{payload_text}"""
        return system_prompt, user_prompt

    def consolidate_memory(self, payload: dict) -> dict:
        system_prompt, user_prompt = self.build_memory_consolidation_prompt(payload, self.name)
        raw = chat_for_agent(self.name, system_prompt, user_prompt, temperature=0.2)
        return self.parse_memory_consolidation_result(raw or "")

    # ==================== 行动决策 ====================

    def decide_next_action(self, game_hour, day, dead_list, nearby_info, scene_info="") -> dict:
        """BDI风格行动决策：Belief→Desire→Intention→Action
        返回 {"ok": bool, "target_location": ..., "target_object": ..., "target_person": ...,
               "action": ..., "action_status": ..., "action_type": ..., "thought": ..., "expected_result": ...,
               "has_visible_clue_hint": bool, "has_detective_hint": bool, "raw_response": ...}
        失败时 ok=False，调用方不应合成 fallback。"""
        soul = safe_truncate(self.read_soul(), 400)
        # 检索相关记忆
        query = f"{self.current_location} {self.current_action} {' '.join(dead_list)}"
        retrieved_memory = self.get_retrieved_memory_text(query, 500)
        current_loc = self.current_location or "unknown"
        current_act = self.current_action or "idle"

        # 今日计划作为参考（不强制）
        plan_action = self.get_current_plan_action(game_hour)
        plan_ref = f"你今天计划{plan_action['hour']}点在{plan_action['location']}做{plan_action['action']}。" if plan_action.get('hour') else "今天没有计划。"

        # Scratch 当前目标
        scratch_currently = self.scratch.get("currently", "")

        # 认知状态
        cognition = safe_truncate(self.read_cognition(), 200)

        # 当前任务/目标文件 (agent.md) —— NPC 的使命与目标
        agent_state = safe_truncate(self.read_agent(), 400)

        # 动态替换狼人敏感词（信息隔离）
        soul_clean = self.sanitize_prompt_text(soul)
        retrieved_clean = self.sanitize_prompt_text(retrieved_memory)
        plan_ref_clean = self.sanitize_prompt_text(plan_ref)
        scratch_clean = self.sanitize_prompt_text(scratch_currently)
        cognition_clean = self.sanitize_prompt_text(cognition)
        agent_clean = self.sanitize_prompt_text(agent_state)
        nearby_clean = self.sanitize_prompt_text(nearby_info)
        scene_clean = self.sanitize_prompt_text(scene_info)

        scene_section = ""
        if scene_info:
            scene_section = f"\n场景信息：{scene_clean}"

        # 角色目标提示
        role_goal = f"你的行动准则：{self.get_runtime_role_prompt()}"

        # 构建行动历史文本
        ah_lines = []
        for i, ah in enumerate(reversed(self.action_history[-5:])):
            ah_lines.append(f"{i + 1}. [{ah.get('action_type', '?')}] {ah.get('location', '?')}: {ah.get('action', '?')}")
        action_history_text = "没有已完成的行动记录。" if not ah_lines else "\n".join(ah_lines)

        # 动态构建可选地点和内部可交互物件描述
        locs_with_desc = []
        locations_keys = [
            ("home", "家/住处"),
            ("Hobbs Cafe", "霍布斯咖啡馆"),
            ("The Rose and Crown Pub", "玫瑰与王冠酒馆"),
            ("The Willows Market", "柳树市场与药房"),
            ("Oak Hill College", "橡树山学院"),
            ("Harvey Oak Supply", "哈维橡树五金店"),
            ("Johnson Park", "约翰逊公园")
        ]
        for key, cn_name in locations_keys:
            desc = self.get_location_description(key)
            if desc:
                locs_with_desc.append(f"- {key} ({cn_name}) -> 内部区域和可交互物件: {desc}")
            else:
                locs_with_desc.append(f"- {key} ({cn_name})")
        loc_options_text = "\n".join(locs_with_desc)

        prompt = f"""你是{self.name}，小镇居民。你需要做出一个有意义的下一步行动决策。

## 你的身份与核心信念
{soul_clean}

## 你的任务文件（agent.md，记录你的使命与当前目标，行动必须服务于这些目标）
{agent_clean}

## 你当前的想法与短期目标
- 当前目标：{scratch_clean}
- 你的思考（必须参考，不要忽略）：
{cognition_clean}

{role_goal}

{active_town_people_rule()}

## 当前处境
- 当前时间：第{day}天 {game_hour}点
- 你当前在：{current_loc}，当前状态：{current_act}
- 已死亡的人：{dead_list}
- 附近的人：{nearby_clean}
{scene_section}

## 你的相关记忆
{retrieved_clean}

## 今日计划（仅供参考，可以偏离）
{plan_ref_clean}

## 你最近已完成的行动（从近到远排列）
{action_history_text}
**重要：不要重复刚才完成的行动。请选择一个新方向或换一个地点、换一种做法。**

## 可选地点与内部物件清单（只能选以下英文地点名之一，一字不差；如果决定与某物件交互，请在 target_object 中精确填写下面列表中该地点下所列出的英文物件名）：
{loc_options_text}

⚠️ 重要：在 JSON 中的 target_location 必须填上述英文键名（如 "Hobbs Cafe" 或 "home"），一字不差，不能填中文！

## 决策指导
你不是一个随机地点选择器。根据你的身份、目标和当前处境，选择一个有意义的行动。
重要原则：
- 如果当前位置就能实现当前目标，选择 continue_current/observe/inspect/work/rest 并继续当前具体事务
- 只有确实需要去另一个地点时才选择 move_to
- 如果 action 里写了"去/前往/到达/走向"某个地点，action_type 必须是 move_to，target_location 必须是那个目的地
- 不要写"准备去某地"却把 action_type 写成 continue_current；continue_current 只表示继续当前已经在做的事务
- 不要在多个地点之间无目的地"散步"或"闲逛"
- action 必须具体，如"向店员打听昨晚是否有人深夜出现"，而非含糊的"活动"
- action_status 是行动中白色气泡文本，只写正在做的短任务，最多10个中文字，不设最少字数；不要写地点、原因、计划、"也/还/今天会..."，例如"整理中"、"检查库存"、"清点药品"
- action_status 必须只描述当前真实存在的人、物或事务；不得虚构客人、顾客、镇民、对方或不存在的目标；如果附近没有可互动的人，只能写物件或职业相关短任务
- thought 必须 60-100 个中文字符，只基于当前可见信息、相关记忆、短期目标或最近行动结果；不得使用 NPC 不知道的隐藏事实，不写全局推理长文
- plan 必须 20-40 个中文字符，格式严格为“去/留在/接近 <目标>，<做一件事>”；只描述下一步，不写后续连环计划，解释放在 thought
- target_location 必须从上方的可选地点列表中选，一字不差！不要自己编造地点名（如"码头"、"广场东侧"等）
- 如果你需要交换信息、试探嫌疑、请别人帮忙或确认线索，优先选择 talk/socialize，并把 target_person 填为8人名单里的中文名。
- 如果你发现了线索、怀疑、可疑事实或自己笃信的推理，但判断不需要立刻主动告诉警长，选择 inspect/observe/work/continue_current，并把 has_visible_clue_hint 设为 true；右侧UI会亮灯泡，等待警长来深挖。
- 只有你判断必须马上告诉警长的明确线索或紧急重要事项，才选择 talk/socialize 并把 target_person 填为"克罗"或"Crow"；普通怀疑不要主动找警长。

用JSON格式回复：
{{"action_type": "move_to|continue_current|observe|inspect|work|rest|investigate|socialize|talk|hide", "target_location": "地点名", "target_object": "目标物件（可选）", "target_person": "目标人物中文名（可选，只能填8人名单里的中文名）", "action": "开始行动蓝泡短句：前往目标并做什么（36字以内）", "plan": "去/留在/接近 <目标>，<做一件事>（20-40字）", "action_status": "行动中白泡短句：只写正在做什么（最多10字，不含也/还/计划尾巴）", "thought": "行动动机（60-100字，只基于当前可见/记忆）", "expected_result": "期望达到什么效果（30字以内）", "duration_minutes": 5-30之间的游戏内分钟数, "has_visible_clue_hint": true/false, "has_detective_hint": true/false}}

action_type 含义：
- move_to: 需要移动到另一个地点
- continue_current: 继续当前已经在做的事务，不是新的“停留”动作
- observe: 观察周围环境/人物
- inspect: 检查某物件/区域
- work: 做自己的本职工作
- rest: 休息
- investigate: 调查可疑事物
- socialize: 社交互动
- talk: 和某人交谈
- hide: 隐藏自己

duration_minutes 含义：
- 这是游戏内分钟，不是现实秒数
- 普通行动根据事情长短选择5到30分钟，不要全部写30
- 简短观察/拿取物品可短一些，整理书架/看书/工作可长一些

只输出JSON，不要其他内容。"""

        raw_original = ""
        try:
            resp = chat_for_agent(self.name, "你是一个小镇居民AI，只输出JSON。", prompt)
            raw_original = resp.strip() if resp else ""

            if not raw_original:
                last_error = get_last_error_for_agent(self.name)
                error = f"empty_response; last_error={last_error}" if last_error else "empty_response"
                return {"ok": False, "error": error, "target_location": "", "target_object": "", "target_person": "", "action": "", "action_status": "", "action_type": "", "thought": "", "expected_result": "", "raw_response": ""}

            # 提取 JSON（健壮解析，支持围栏、前后文字、值内花括号）
            raw = self._extract_json_text(raw_original)
            if not raw:
                return {"ok": False, "error": "json_extraction_failed: no valid JSON found in response",
                        "target_location": "", "target_object": "", "target_person": "",
                        "action": "", "action_status": "", "action_type": "", "thought": "",
                        "expected_result": "", "raw_response": raw_original}

            result = _json.loads(raw)
            # 规范化 action_type：兼容中文旧值
            raw_at = result.get("action_type", "")
            result["action_type"] = self._normalize_action_type(raw_at)
            result.setdefault("target_location", "")
            result.setdefault("target_object", "")
            result.setdefault("target_person", "")
            result.setdefault("action", "")
            result.setdefault("plan", "")
            result.setdefault("action_status", "")
            result.setdefault("thought", "")
            result.setdefault("expected_result", "")
            def _duration_minutes(value):
                try:
                    duration = int(float(value))
                except (TypeError, ValueError):
                    duration = 15
                return max(5, min(30, duration))
            result["duration_minutes"] = _duration_minutes(result.get("duration_minutes", 15))
            def _bool_field(value):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.strip().lower() in {"true", "yes", "1", "是", "有"}
                return bool(value)
            result["has_visible_clue_hint"] = _bool_field(result.get("has_visible_clue_hint", False))
            result["has_detective_hint"] = _bool_field(result.get("has_detective_hint", False))
            if result.get("thought"):
                self.current_thought = str(result["thought"]).strip()
                self.current_thought_time = _time.time()
            result["ok"] = True
            result["raw_response"] = raw_original
            return result
        except Exception as e:
            return {"ok": False, "error": f"json_parse_error: {e}", "target_location": "", "target_object": "", "target_person": "", "action": "", "action_status": "", "action_type": "", "thought": "", "expected_result": "", "raw_response": raw_original}

    @staticmethod
    def _extract_json_text(raw: str) -> str:
        """从 LLM 原始响应中健壮地提取 JSON 对象字符串。

        处理场景：
        - 裸 JSON： `{"key": "value"}`
        - ```json 代码围栏
        - ``` 无语言标识的代码围栏
        - 围栏前后有说明文字
        - JSON 字符串值中包含花括号（如 `"action": "move to {place}"`）

        策略：
        1. 优先查找 ``` 代码围栏，提取其中第一个完整 JSON 对象。
        2. 无围栏时，在文本中查找平衡的 {…} 对，同时跟踪字符串上下文
           以正确处理值中的花括号。
        3. 返回第一个能通过 json.loads 验证的 JSON 文本；若全部失败则返回 ""。
        """
        if not raw or not raw.strip():
            return ""

        text = raw.strip()

        # --- 策略 A：查找 ``` 代码围栏 ---
        fence_start = text.find("```")
        if fence_start != -1:
            # 找到开头的 ```
            after_fence = text[fence_start + 3:].lstrip()
            # 跳过可选的 "json" 语言标识
            if after_fence.startswith("json"):
                after_fence = after_fence[4:].lstrip()
            # 找结束的 ```
            fence_end = after_fence.find("```")
            if fence_end != -1:
                candidate = after_fence[:fence_end].strip()
                if candidate:
                    # 在这个围栏内容中提取第一个 JSON 对象
                    extracted = Agent._find_first_json_object(candidate)
                    if extracted:
                        try:
                            _json.loads(extracted)
                            return extracted
                        except _json.JSONDecodeError:
                            pass

        # --- 策略 B：直接在全文找第一个 JSON 对象 ---
        extracted = Agent._find_first_json_object(text)
        if extracted:
            try:
                _json.loads(extracted)
                return extracted
            except _json.JSONDecodeError:
                pass

        return ""

    @staticmethod
    def _find_first_json_object(text: str) -> str:
        """在文本中找到第一个平衡的 {…} JSON 对象，正确处理字符串内的花括号。

        逐字符扫描，跟踪：
        - 是否处于字符串中（"..."），处理反斜杠转义
        - 花括号深度

        返回从第一个 { 到匹配的 } 的子串；若找不到则返回 ""。
        """
        depth = 0
        in_string = False
        escaped = False
        start = -1

        for i, ch in enumerate(text):
            if escaped:
                escaped = False
                continue
            if ch == '\\' and in_string:
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    return text[start:i + 1]

        return ""

    @staticmethod
    def _normalize_action_type(raw: str) -> str:
        """将中文/混合 action_type 统一映射为英文字符串"""
        mapping = {
            "移动": "move_to", "move": "move_to", "walk": "move_to", "walking": "move_to",
            "工作": "work", "working": "work",
            "社交": "socialize", "social": "socialize", "chatting": "socialize",
            "调查": "investigate", "investigating": "investigate",
            "休息": "rest", "sleeping": "rest", "relaxing": "rest",
            "观察": "observe",
            "日常": "continue_current", "stay": "continue_current", "停留": "continue_current",
            "原地停留": "continue_current", "继续当前": "continue_current",
            "检查": "inspect",
            "交谈": "talk",
            "隐藏": "hide",
        }
        key = raw.strip().lower()
        return mapping.get(key, key if key else "continue_current")

    def get_action_result(self, action_type: str, action: str, location: str,
                          target_object: str = "", target_person: str = "",
                          expected_result: str = "") -> str:
        """为已完成的行动生成一句自然语言结果句子（代码生成，不调用LLM）。
        返回人类可读的中文描述，避免 JSON/code-like 输出。"""
        loc = location or "某处"
        obj = f"{target_object}" if target_object else ""
        person = f"{target_person}" if target_person else ""
        templates = {
            "move_to": f"到达了{loc}，准备行动。",
            "continue_current": f"在{loc}继续当前事务：{action}。",
            "stay": f"在{loc}继续当前事务：{action}。",
            "observe": f"在{loc}观察了周围的情况。",
            "inspect": f"在{loc}检查了{'周围环境' if not obj else obj}。",
            "work": f"在{loc}完成了工作：{action}。",
            "rest": f"在{loc}休息了一下。",
            "investigate": f"在{loc}进行了调查。",
            "socialize": f"在{loc}进行了社交活动。",
            "talk": f"在{loc}与{'他人' if not person else person}交谈。",
            "hide": f"在{loc}隐藏了起来。",
        }
        base = templates.get(action_type, f"在{loc}：{action}。")
        if expected_result:
            base += f" 预期效果：{expected_result}"
        return base

    # ==================== 工具方法 ====================

    def get_full_context(self) -> str:
        """获取智能体的完整上下文（用于展示或调试）"""
        notebook_section = ""
        if self.role == "detective":
            notebook_content = self.read_notebook()
            notebook_section = f"\n## Notebook\n{notebook_content}"

        return f"""# {self.name} ({self.role})

## Soul
{self.read_soul()}

## Agent State
{self.read_agent()}

## Memory
{self.read_memory()}

## Cognition
{self.read_cognition()}
{notebook_section}"""

    def init_files(self):
        """每次新游戏重置运行时状态；soul.md 是唯一跨局保留的角色设定。"""
        self.memory_index = []
        self.dialogue_history = []
        self.scratch = self._default_scratch()
        self.daily_plan = []
        self.plan_day = 0
        self.current_action = ""
        self.current_emoji = ""
        self.current_thought = ""
        self.current_thought_time = 0
        self.current_action_type = ""
        self.current_location = ""
        self.runtime_state = "idle"
        self.action_history = []
        self.chat_count = {}
        self.in_conversation_with = None
        self._pending_action = {}
        self._last_decision = {}
        self._last_raw_response = ""
        self._last_response_error = ""
        self._llm_decided = False
        self._last_llm_decision_time = 0
        self._is_thinking = False
        self._thinking_started_at = 0
        self._next_llm_retry_time = 0
        self._action_plan_ready_at = 0
        self._arrived_at_time = 0
        self._departure_delay_until = 0
        self._is_reflecting = False
        self._reflect_started_at = 0

        for filename in ["agent.md", "memory.md", "cognition.md"]:
            self._write_md(filename, "")
        if self.role == "detective":
            self._write_md("notebook.md", "")
        self._write_json("scratch.json", self.scratch)
        self._write_json("spatial_memory.json", {})
        self._write_json("memory_index.json", self.memory_index)

    def detective_deduce(self, day: int) -> dict:
        """侦探专属推理功能：结合笔记、记忆和认知来推理谁是狼人/凶手"""
        if self.role != "detective":
            return {"error": "Only detective can deduce"}

        notebook = safe_truncate(self.read_notebook(), 1200)
        cognition = safe_truncate(self.read_cognition(), 600)
        soul = safe_truncate(self.read_soul(), 300)

        # 获取小镇所有 NPC 名字（排除 Crow）
        all_names = [n for n in os.listdir(PERSONAS_DIR) if os.path.isdir(os.path.join(PERSONAS_DIR, n)) and n != "Crow"]
        all_names = [n.replace("_", " ") for n in all_names]

        system_prompt = f"""你是侦探 {self.name}。你在调查一系列连环杀人/失踪案件，目标是找出隐藏的凶手。
你的灵魂设定：{soul}

请综合你目前记录的侦探笔记（notebook.md）和你的认知与思考（cognition.md），对小镇所有存活的居民（不包括你自己）进行一次深刻的案情推理。

分析要点：
1. 每个人在夜间是否有不在场证明。
2. 每个人在白天的言行是否有矛盾之处，是否有回避问题或紧张的表现。
3. 凶手极力想隐藏自己，表现可能过于友好或极度沉默。

你需要输出包含所有分析目标的 JSON，格式如下（百分比总和不一定需要是100）：
{{
    "suspects": {{
        "居民名字1": {{
            "suspicion_percentage": 50,
            "reason": "简短的怀疑理由（50字以内）"
        }},
        "居民名字2": {{
            "suspicion_percentage": 10,
            "reason": "理由"
        }}
    }},
    "most_suspicious": "怀疑度最高的人的名字",
    "deduction_summary": "完整的案情推导总结（150字以内）"
}}

只返回 JSON，不要其他内容。"""

        user_prompt = f"""当前是第{day}天。
需要进行怀疑度分析的目标人名单：{', '.join(all_names)}。

你的侦探笔记：
{notebook}

你目前的思考与认知：
{cognition}

请进行案情推理并返回 JSON："""

        try:
            resp = chat_for_agent(self.name, system_prompt, user_prompt, temperature=0.3)
            resp = resp.strip()
            if resp.startswith("```"):
                resp = resp.split("```")[1]
                if resp.startswith("json"):
                    resp = resp[4:]
                resp = resp.strip()
            if resp.endswith("```"):
                resp = resp[:-3].strip()

            result = _json.loads(resp)
            summary = result.get("deduction_summary", "推理已得出。")
            self.add_memory(f"进行了案情推理：{summary[:100]}", day)
            self.add_notebook_entry(f"案情推理总结：\n{summary}\n怀疑度最高：{result.get('most_suspicious', '无')}", day)
            return result
        except Exception as e:
            print(f"[detective_deduce Error]: {e}", file=sys.stderr, flush=True)
            return {"suspects": {}, "most_suspicious": "", "deduction_summary": f"推理失败: {e}"}

    def detective_announce(self, werewolf_guess: str) -> dict:
        """侦探宣布指认结果"""
        if self.role != "detective":
            return {"error": "Only detective can announce"}
        # 返回指认结果（由游戏引擎在最外层判断输赢）
        return {
            "guess": werewolf_guess,
            "timestamp": _time.time()
        }
