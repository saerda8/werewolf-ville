"""

游戏引擎 - 时间系统 / 状态调度 / 位置管理





核心循环:

  白天(30min) → 玩家确认进入夜晚 → 夜晚(5min) → 自动进入白天 → ...





白天: 所有智能体按日程自动行动, 玩家可操控侦探

夜晚: 狼人杀人, 玩家只能观看, 夜晚结束自动进入白天

"""

import json
import math
import os
import time
import random

import re

import threading

import sys

import inspect

from collections import deque

from enum import Enum

from agent import Agent

from engine_bubbles import EngineBubbleMixin
from engine_dusk import EngineDuskMixin
from engine_memory_queue import MemoryQueue, MemoryTask
from engine_navigation import (
    _apply_collision_overrides,
    _connect_maze_regions,
    bfs_path,
    get_nearby_objects,
    get_tile_scene,
    load_collision_maze,
    load_scene_data,
)
from engine_observation import ObservationEvent, filter_observable_events
from engine_tasks import EngineTasksMixin
from llm import chat, chat_for_agent, get_last_error_for_agent

from config_loader import load_config, get_config

from utils import safe_truncate

from world_config import (

    PUBLIC_LANDMARKS,

    ACTIVE_CHARACTERS,

    AMBIENT_RESIDENT_SPRITES,

    INITIAL_BODY_SITE,

    CHARACTER_DISPLAY_NAMES,

    SHERIFF_AREA,

    display_name_for_person,

    validate_world_config,

)

from simulation_events import BodyRecord, ClueRecord, undelivered_clues_for

from llm import configure_runtime_llm, set_runtime_model_assignments, available_models

from night_hunt import HuntCandidate, NightHuntState, build_trace_clues, choose_forced_target









CONFIG = load_config()





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





def localize_visible_character_names(text: str) -> str:
    """Convert internal character ids that leak from prompts/models into display names."""
    localized = str(text or "")
    landmark_labels = globals().get("LANDMARK_LABELS_ZH", {})
    for internal, display in sorted(landmark_labels.items(), key=lambda item: len(item[0]), reverse=True):
        localized = localized.replace(internal, display)
    for internal, display in sorted(CHARACTER_DISPLAY_NAMES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.fullmatch(r"[A-Za-z]+", internal):
            localized = re.sub(rf"\b{re.escape(internal)}\b", display, localized)
        else:
            localized = localized.replace(internal, display)
    visible_terms = {
        "LLM": "大模型",
        "idle": "空闲",
        "thinking": "思考中",
        "planning": "计划中",
        "moving": "移动中",
        "acting": "行动中",
        "stay": "继续当前事务",
        "continue_current": "继续当前事务",
        "talk": "交谈",
        "inspect": "检查",
        "observe": "观察",
        "work": "工作",
    }
    for internal, display in visible_terms.items():
        if internal == "LLM":
            localized = localized.replace(internal, display)
        else:
            localized = re.sub(rf"\b{re.escape(internal)}\b", display, localized)
    return localized




def resolve_character_name(name: str) -> str:

    """Resolve a model-facing Chinese display name or internal id to the stable id."""

    raw = str(name or "").strip()

    if not raw:

        return ""

    if raw in ACTIVE_CHARACTERS:

        return raw

    normalized = raw.replace(" ", "")

    for internal, display in CHARACTER_DISPLAY_NAMES.items():

        if raw == display or normalized == display.replace(" ", ""):

            return internal

    return raw





# ==================== 地图常量 ====================





LANDMARKS = PUBLIC_LANDMARKS

LANDMARK_LABELS_ZH = {

    "home": "家中",

    "Hobbs Cafe": "霍布斯咖啡馆",

    "The Rose and Crown Pub": "玫瑰与皇冠酒吧",

    "Oak Hill College": "橡树山学院",

    "The Willows Market and Pharmacy": "柳树市场药房",

    "Harvey Oak Supply Store": "哈维橡树五金店",

    "Johnson Park": "约翰逊公园",

    "Johnson Park east plaza": "约翰逊公园东侧广场",

}





AGENT_CONFIGS = {}

for _name, _info in ACTIVE_CHARACTERS.items():

    AGENT_CONFIGS[_name] = {"home": _info["home"]}





AGENT_CONFIGS["Arthur Burton"]["schedule"] = [("sleeping","home",0,6),("working","Harvey Oak Supply Store",6,22),("relaxing","home",22,24)]

AGENT_CONFIGS["Crow"]["schedule"] = [("sleeping","home",0,7),("investigating","Johnson Park",7,22),("returning home","home",22,24)]

AGENT_CONFIGS["Isabella Rodriguez"]["schedule"] = [("sleeping","home",0,7),("opening cafe","Hobbs Cafe",7,20),("closing up","home",20,24)]

AGENT_CONFIGS["Klaus Mueller"]["schedule"] = [("sleeping","home",0,8),("studying","Oak Hill College",8,17),("hanging out","The Rose and Crown Pub",17,22),("going home","home",22,24)]

AGENT_CONFIGS["Maria Lopez"]["schedule"] = [("sleeping","home",0,5),("working","Hobbs Cafe",5,10),("selling goods","The Willows Market and Pharmacy",10,17),("walking","Johnson Park",17,19),("going home","home",19,24)]

AGENT_CONFIGS["Sam Moore"]["schedule"] = [("sleeping","home",0,7),("opening pub","The Rose and Crown Pub",7,12),("serving guests","The Rose and Crown Pub",12,22),("going home","home",22,24)]

AGENT_CONFIGS["Jane Moreno"]["schedule"] = [("sleeping","home",0,6),("checking park paths","Johnson Park",6,10),("tending flowers","Johnson Park",10,14),("lunch break","Hobbs Cafe",14,15),("evening cleanup","Johnson Park",15,19),("going home","home",19,24)]

AGENT_CONFIGS["Mei Lin"]["schedule"] = [("sleeping","home",0,7),("opening library","Oak Hill College",7,9),("research and cataloguing","Oak Hill College",9,12),("lunch break","Hobbs Cafe",12,13),("afternoon research","Oak Hill College",13,17),("evening walk","Johnson Park",17,18),("going home","home",18,24)]





ACTION_EMOJIS = {"sleeping":"\U0001f634","working":"\U0001f4bc","studying":"\U0001f4da","eating":"\U0001f35c","walking":"\U0001f6b6","chatting":"\U0001f5e3","writing":"\u270d\ufe0f","investigating":"\U0001f50d","shopping":"\U0001f6d2","relaxing":"\U0001f60c","serving":"\U0001f3c3","hanging":"\U0001f3cb","opening":"\U0001f514","closing":"\U0001f511","returning":"\U0001f3e0","at":"\U0001f4cd","having":"\u2615"}



ACTION_TYPE_LABELS_ZH = {
    "move_to": "\u79fb\u52a8\u524d\u5f80",
    "stay": "\u7ee7\u7eed\u5f53\u524d\u4e8b\u52a1",
    "continue_current": "\u7ee7\u7eed\u5f53\u524d\u4e8b\u52a1",
    "observe": "\u89c2\u5bdf\u56db\u5468",

    "inspect": "\u68c0\u67e5\u7269\u4ef6",

    "work": "\u65e5\u5e38\u5de5\u4f5c",

    "rest": "\u4f11\u606f",

    "investigate": "\u8c03\u67e5\u7ebf\u7d22",

    "socialize": "\u793e\u4ea4\u4e92\u52a8",

    "talk": "\u4ea4\u8c08\u5bf9\u8bdd",

    "hide": "\u9690\u85cf\u81ea\u8eab",

}







CHARACTER_DAILY_ROLES = {

    "Arthur Burton":       "你是镇上的修理工，天亮后要去 Harvey Oak Supply Store 开工，修理农具。作为老板你不能让铺子空着。",

    "Crow":                "你是小镇的警长，习惯天亮后去 Johnson Park 一带巡查，注意有没有不寻常的动静。昨晚的狼人事件让你格外警惕。",

    "Isabella Rodriguez":  "你是 Hobbs Cafe 的老板娘，清晨就要去开店，准备咖啡和早餐接待客人。咖啡馆是你的命根子，不能不去。",

    "Klaus Mueller":       "你是 Oak Hill College 的讲师，早上主要在教室上课或整理讲台资料。晚上才去 The Rose and Crown Pub 喝酒放松。",

    "Maria Lopez":         "你是小镇的店员，早晨在 Hobbs Cafe 帮忙，然后去 The Willows Market and Pharmacy 卖东西。你不去的话就没人顾店了。",

    "Sam Moore":           "你是 The Rose and Crown Pub 的老板兼酒保，早上要去酒馆开门、整理吧台并接待客人。酒馆是你的生计，也是收集镇上消息的地方。",

    "Jane Moreno":         "你是 Johnson Park 的园艺管理员，清晨要检查公园小路、花坛和长椅。公园是案发附近的重要公共空间，你会格外留意异常痕迹。",

    "Mei Lin":             "你是 Oak Hill College 的图书管理员兼研究员，早上要去图书馆整理书籍并协助学生查阅资料。你喜欢安静地做研究工作，但对小镇的传闻保持关注。",

}





# 第二圈默认目的地（根据角色日程预设，确保 NPC 能立即开始移动）

DEFAULT_DESTINATIONS = {

    "Arthur Burton": "Harvey Oak Supply Store",

    "Crow": "Johnson Park",

    "Isabella Rodriguez": "Hobbs Cafe",

    "Klaus Mueller": "Oak Hill College",

    "Maria Lopez": "The Willows Market and Pharmacy",

    "Sam Moore": "The Rose and Crown Pub",

    "Jane Moreno": "Johnson Park",

    "Mei Lin": "Oak Hill College",

}





DEFAULT_DEPARTURE_OBJECTS = {

    "Arthur Burton": "behind the supply store counter",

    "Isabella Rodriguez": "behind the cafe counter",

    "Klaus Mueller": "classroom student seating",

    "Maria Lopez": "pharmacy store shelf",

    "Sam Moore": "behind the bar counter",

    "Jane Moreno": "park garden",

    "Mei Lin": "bookshelf",

}





def character_primary_object(name: str, location: str) -> str:
    """Return the role-appropriate object for a character's primary workplace."""
    if DEFAULT_DESTINATIONS.get(name) == location:
        return DEFAULT_DEPARTURE_OBJECTS.get(name, "")
    return ""


LANDMARK_DEFAULT_OBJECTS = {
    "Hobbs Cafe": "behind the cafe counter",

    "The Rose and Crown Pub": "behind the bar counter",

    "The Willows Market and Pharmacy": "pharmacy store shelf",

    "Oak Hill College": "bookshelf",

    "Harvey Oak Supply Store": "supply store product shelf",

    "Johnson Park": "park garden",

}





GATHERING_FALLBACKS = {

    "Crow": "昨夜有人遇害，情况很严重。请大家如实说明行踪。",

    "Arthur Burton": "昨晚我在五金店后间修工具，关门前核对了借出清单。今早听到命案心里发沉，今天会先整理店里来往记录。",
    "Isabella Rodriguez": "昨晚我在咖啡馆收拾杯盘和后厨，到很晚才离开。今早看到大家围在这里，我很害怕，也会回想最后几位客人。",
    "Klaus Mueller": "昨晚我在学院整理课程资料，后来一直在办公室附近。发生命案后我会配合克罗，也想确认夜里有没有人进出学院。",
    "Maria Lopez": "昨晚我在药房清点药品和账目，关门后又整理柜台。现在出了人命，我不会隐瞒，今天也会核对有没有东西被动过。",
    "Sam Moore": "昨晚酒馆打烊后我收拾吧台和桌椅，之后才回去休息。今早这事让我不踏实，我会回酒馆想想客人的话。",
    "Jane Moreno": "昨晚我在公园边整理花坛和工具，天黑后才离开。这里离我常去的地方不远，我很担心，会仔细回想昨晚的路。",
    "Mei Lin": "昨晚我在图书馆整理文献和借阅卡，到很晚才停下。命案让我震惊，今天我会先查镇史和旧报纸里的类似记录。",
}





DEPARTURE_FALLBACKS = {

    "Arthur Burton": "我得去哈维橡树五金店开门修工具，也会留意附近有没有异常。",

    "Isabella Rodriguez": "我得去霍布斯咖啡馆准备早餐，也会留意来往的客人。",

    "Klaus Mueller": "我得去橡树山学院上课，路上会注意有没有异常。",

    "Maria Lopez": "我得去柳树市场药房照看货物，也会留意可疑的人。",

    "Sam Moore": "我得去玫瑰与皇冠酒吧开店营业，准备迎接客人。",

    "Jane Moreno": "我得去约翰逊公园检查花坛和小路，也会留意有没有异常情况。",

    "Mei Lin": "我得去橡树山学院图书馆整理资料，路上会留意异常动静。",

}









class GamePhase(Enum):

    DAY = "day"

    DUSK_DISCUSSION = "dusk_discussion"

    NIGHT = "night"

    GAME_OVER = "game_over"

    PENDING_SILVER_SHOT = "pending_silver_shot"









class WerewolfGameEngine(EngineBubbleMixin, EngineDuskMixin, EngineTasksMixin):
    """狼人小镇游戏引擎"""





    def __init__(self, random_seed=None, llm_override=None):

        self._rng = random.Random(random_seed)

        validate_world_config()

        self.day = 1

        self.phase = GamePhase.DAY

        self.game_hour = 7

        self.agents = {}





        non_crow = [k for k in ACTIVE_CHARACTERS.keys() if k != "Crow"]

        self.werewolf_names = self._rng.sample(non_crow, 2)

        self.werewolf_name = self.werewolf_names[0]  # legacy first wolf string

        self.detective_name = "Crow"





        self.model_assignments = {}

        active_names = list(ACTIVE_CHARACTERS.keys())

        self.llm_provider = configure_runtime_llm(llm_override)

        if self.llm_provider["provider"] != "chat2api":

            for name in active_names:

                self.model_assignments[name] = self.llm_provider["model"]

        else:

            models = list(CONFIG.get("llm", {}).get("available_models", []))

            if not models:

                raise ValueError("llm.available_models must define at least one model entry")

            self._rng.shuffle(models)

            for i, name in enumerate(active_names):

                self.model_assignments[name] = models[i % len(models)]

        set_runtime_model_assignments(self.model_assignments)

        self.dead_list = []

        self.game_log = []

        self.game_over = False

        self.winner = None





        # 时间

        self.day_duration = CONFIG["game"]["day_duration_seconds"]

        self.night_duration = CONFIG["game"]["night_duration_seconds"]

        self.tick_interval = CONFIG["game"]["tick_interval_seconds"]

        self.gathering_turn_timeout = max(

            18,

            int(CONFIG.get("llm", {}).get("request_timeout_seconds", 60)) // 3 + 5,

        )

        self.gathering_per_speaker_timeout = max(

            20,

            int(CONFIG.get("llm", {}).get("request_timeout_seconds", 60)) // 3,

        )

        self.day_start_time = None

        self.night_start_time = None

        self.day_time_expired = False





        # 黄昏讨论阶段

        self.dusk_start_time = None

        self.dusk_duration = CONFIG.get("game", {}).get("dusk_duration_seconds", 600)

        self._dusk_votes = {}          # name -> voted_target (who each NPC accuses)
        self._dusk_vote_reasons = {}   # name -> reason string
        self._dusk_vote_active = False # True when NPC votes have been generated
        self._dusk_discussion_active = False
        self._dusk_discussion_statements = []
        self._dusk_crow_statement = ""
        self._dusk_jail_target = None  # player's choice for jail
        self._vote_history = []        # daily dusk vote snapshots for player review




        # 每日侦探采访任务追踪（排除 Crow 自己）

        self._daily_interviewed = set()  # 今日已采访过的 NPC 集合





        # 监狱/拘留追踪

        self._jailed = set()  # names of jailed residents





        # 银器进展

        # _silver_jewelry_holder: random non-Crow resident who holds the silver jewelry

        # _silver_knife_holder: random non-Crow, non-werewolf resident who has a hidden silver knife

        non_crow_all = [k for k in ACTIVE_CHARACTERS.keys() if k != "Crow"]

        self._silver_jewelry_holder = self._rng.choice(non_crow_all)

        non_crow_non_wolf = [k for k in non_crow_all if k not in self.werewolf_names]

        self._silver_knife_holder = self._rng.choice(non_crow_non_wolf) if non_crow_non_wolf else None

        self._silver_bullet_acquired = False   # from Arthur at Harvey Oak Supply Store

        self._silver_jewelry_acquired = False  # from jewelry holder

        self._silver_bullet_crafted = False    # crafted from bullet + jewelry

        self._silver_bullet_used = False       # Crow can fire the crafted bullet once

        self._silver_knife_used = False        # hidden good-side knife is one-use

        self._silver_knife_night_checked = False
        # Silver knife phase always records 60s regardless of outcome
        self._silver_knife_phase_started_at = 0.0
        self._silver_knife_phase_duration = 60.0  # fixed 60s display
        self._silver_knife_scrapped_tonight = False  # True if holder killed by wolf first
        self._silver_knife_target_tonight = ""       # who the knife was used on tonight
        self._silver_knife_killed_werewolf_tonight = False  # True if knife killed a werewolf

        # Track which silver objectives are completed today

        self._silver_task_done_today = None  # set to task key once per day

        # Track per-day interview requirements

        self._daily_normal_chats = {}  # name -> set of NPCs normally chatted with today

        # Day4 flow control
        self._day4_no_free_activity = False
        self._pending_silver_wolf = ""





        # 线程

        self._running = False

        self._thread = None

        self._lock = threading.RLock()





        # 迷宫/寻路

        self.collision_maze = load_collision_maze()

        self.agent_paths = {}





        # 场景物件数据

        scene_data = load_scene_data()

        self.sector_maze = scene_data[0]

        self.arena_maze = scene_data[1]

        self.go_maze = scene_data[2]

        self.sector_dict = scene_data[3]

        self.arena_dict = scene_data[4]

        self.go_dict = scene_data[5]





        # LLM控制

        self.llm_tick_counter = 0

        self.llm_interval = 20  # 20 tick * 0.5秒 = 10秒一次LLM反思

        self.llm_threads = []

        self.llm_reflect_idx = 0  # 独立轮询计数器（不在每次清零）





        self.chat_bubbles = {}

        self._log_id = 0

        self._socketio = None
        self._detective_chat_active_target = None
        self._detective_chat_pending_target = None
        self._detective_chat_job_id = 0
        self._npc_chat_tokens = {}
        self._speech_queue = []
        self._speech_queue_seq = 0
        self._speech_worker_active = False
        self._observation_events = []
        self._observation_event_id = 1
        self._memory_queue = MemoryQueue()
        self._memory_task_id = 1
        self._memory_worker_active = False




        self.bodies = []

        self.clues = []

        ambient_name = self._rng.choice(AMBIENT_RESIDENT_SPRITES)

        initial_site = INITIAL_BODY_SITE

        body = BodyRecord(

            body_id=f"body_{ambient_name.replace(' ', '_')}",

            victim_name=ambient_name,

            location=initial_site["location"],

            x=initial_site["x"],

            y=initial_site["y"],

            created_day=0,

            discovered=True

        )

        self.bodies.append(body)





        self._init_agents()

        if self.detective_name in self.agents:

            self._reset_daily_deep_dive_quota()





    # ==================== 初始化 ====================



    @staticmethod

    def _daily_deep_dive_quota() -> int:

        conversation = CONFIG.get("conversation", {})

        if "deep_dive_per_day" in conversation:

            return int(conversation.get("deep_dive_per_day", 3))

        quota = conversation.get("deep_dive_quota", 3)

        if isinstance(quota, dict):

            return int(quota.get("kill_1", 3))

        return int(quota)



    def _reset_daily_deep_dive_quota(self) -> None:

        detective = self.agents.get(self.detective_name)

        if not detective:

            return

        detective.deep_dive_quota = self._daily_deep_dive_quota()

        detective.deep_dive_used = 0





    def _observation_radius(self) -> int:
        return int(CONFIG.get("perception", {}).get("observation_radius", 10))

    def _observation_ttl_seconds(self) -> float:
        return float(CONFIG.get("perception", {}).get("observation_ttl_seconds", 300))

    def _record_observation_event(
        self,
        event_type: str,
        subject: str,
        text: str,
        x: int,
        y: int,
        public: bool = False,
        hidden: bool = False,
        witnesses=None,
        object: str = "",
        source: str = "world",
    ) -> ObservationEvent:
        event = ObservationEvent(
            event_id=f"obs_{self._observation_event_id:06d}",
            event_type=str(event_type or "event"),
            subject=str(subject or ""),
            text=str(text or ""),
            x=int(x),
            y=int(y),
            day=int(self.day),
            game_hour=float(self.game_hour),
            timestamp=time.time(),
            object=str(object or ""),
            public=bool(public),
            hidden=bool(hidden),
            witnesses=set(witnesses or []),
            source=str(source or "world"),
        )
        self._observation_event_id += 1
        self._observation_events.append(event)
        cutoff = time.time() - self._observation_ttl_seconds()
        self._observation_events = [item for item in self._observation_events if item.timestamp >= cutoff]
        if event.event_type in {"body_discovered", "vote_result", "night_kill"}:
            if event.public:
                recipients = [
                    name for name, agent in self.agents.items()
                    if name != self.detective_name and agent.is_alive and name not in self._jailed
                ]
            else:
                recipients = [
                    name for name in event.witnesses
                    if name in self.agents
                    and name != self.detective_name
                    and self.agents[name].is_alive
                    and name not in self._jailed
                ]
            for recipient in recipients:
                self._enqueue_memory_task(
                    recipient,
                    {
                        "kind": "observation_event",
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "subject": event.subject,
                        "text": event.text,
                        "day": event.day,
                        "game_hour": event.game_hour,
                        "public": event.public,
                        "hidden": event.hidden,
                        "witnesses": sorted(event.witnesses),
                    },
                )
        return event

    def _observable_events_for(self, name: str, agent) -> list[ObservationEvent]:
        return filter_observable_events(
            self._observation_events,
            observer_name=name,
            observer_x=agent.x,
            observer_y=agent.y,
            now=time.time(),
            radius=self._observation_radius(),
            ttl_seconds=self._observation_ttl_seconds(),
        )

    def _build_observation_packet(self, name: str, agent) -> dict:
        nearby_people = []
        radius = self._observation_radius()
        for other_name, other in self.agents.items():
            if other_name == name or not other.is_alive:
                continue

            dist = abs(agent.x - other.x) + abs(agent.y - other.y)
            if dist <= radius:
                nearby_people.append(
                    f"- {display_name_for_person(other_name)}在{other.current_location or '某处'}"
                    f"（正在{localize_visible_character_names(other.current_action or '活动')}）"
                )

        nearby_objects = get_nearby_objects(
            agent.x,
            agent.y,
            3,
            self.sector_maze,
            self.arena_maze,
            self.go_maze,
            self.sector_dict,
            self.arena_dict,
            self.go_dict,
        )
        scene = get_tile_scene(
            agent.x,
            agent.y,
            self.sector_maze,
            self.arena_maze,
            self.go_maze,
            self.sector_dict,
            self.arena_dict,
            self.go_dict,
        )
        visible_events = self._observable_events_for(name, agent)
        query = " ".join(
            [
                str(agent.current_location or ""),
                str(agent.current_action or ""),
                " ".join(event.text for event in visible_events[-5:]),
            ]
        )
        memory_text = ""
        if hasattr(agent, "get_retrieved_memory_text"):
            try:
                memory_text = agent.get_retrieved_memory_text(query, 800)
            except Exception:
                memory_text = ""
        action_history = getattr(agent, "action_history", [])[-5:]
        history_lines = [
            f"- {item.get('location', '?')}: {item.get('action', '?')}"
            for item in reversed(action_history)
        ]
        public_lines = [
            f"第{self.day}天 {self.game_hour:.1f}点，阶段{self.phase.value}。",
            f"已死亡：{', '.join(display_name_for_person(item) for item in self.dead_list) if self.dead_list else '暂无'}。",
        ]
        return {
            "self_state_text": (
                f"我在{agent.current_location or self._reverse_lookup_location(agent.x, agent.y) or '某处'}；"
                f"当前行动：{localize_visible_character_names(agent.current_action or '空闲')}。"
            ),
            "nearby_people_text": "\n".join(nearby_people) if nearby_people else "附近没有人",
            "nearby_objects_text": "、".join(nearby_objects) if nearby_objects else "附近没有可互动物件",
            "scene_text": f"{scene.get('sector', '')} {scene.get('arena', '')}".strip(),
            "observable_events_text": "\n".join(f"- {event.text}" for event in visible_events) if visible_events else "暂时没有新的可见事件",
            "relevant_memory_text": memory_text or "暂时没有检索到相关记忆",
            "current_goal_text": str(getattr(agent, "scratch", {}).get("currently", "") or ""),
            "current_action_text": str(agent.current_action or ""),
            "action_history_text": "\n".join(history_lines) if history_lines else "暂无近期行动记录",
            "public_world_text": "\n".join(public_lines),
            "visible_events": [
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "subject": event.subject,
                    "text": event.text,
                    "day": event.day,
                    "game_hour": event.game_hour,
                }
                for event in visible_events
            ],
        }

    def _format_observation_for_decision(self, packet: dict) -> tuple[str, str]:
        nearby = "\n".join(
            [
                "【自身】",
                packet.get("self_state_text", ""),
                "【附近的人】",
                packet.get("nearby_people_text", ""),
                "【当前可见事件】",
                packet.get("observable_events_text", ""),
                "【相关记忆】",
                packet.get("relevant_memory_text", ""),
                "【近期行动】",
                packet.get("action_history_text", ""),
            ]
        )
        scene = "\n".join(
            [
                packet.get("scene_text", ""),
                f"可见物件：{packet.get('nearby_objects_text', '')}",
                packet.get("public_world_text", ""),
            ]
        )
        return nearby, scene

    def _default_grounded_action_status(self, name: str, agent, packet: dict) -> str:
        objects = str(packet.get("nearby_objects_text", "") or "")
        current = str(agent.current_action or "").strip()
        if objects and objects != "附近没有可互动物件":
            first_object = objects.split("、")[0].strip()
            if first_object:
                return f"整理{first_object}"[:16]
        if current:
            return current[:16]
        return "整理手头事务"

    def _ground_action_status(self, name: str, agent, action_status: str, packet: dict) -> str:
        status = str(action_status or "").strip()
        nearby = str(packet.get("nearby_people_text", "") or "")
        if not status:
            return self._default_grounded_action_status(name, agent, packet)
        status = re.sub(r"^.*?[说講讲][:：]\s*", "", status)
        status = re.sub(r"^(正在|正|在|和|并|同时)\s*", "", status)
        for marker in ("，也", "，还", "，并", "，再", "，准备", "，等待", "，观察", "，检查", "，留意", "。", "；", ";"):
            if marker in status:
                status = status.split(marker, 1)[0].strip()
        status = re.sub(r"^(和|并|同时)\s*", "", status).strip()
        if not status:
            return self._default_grounded_action_status(name, agent, packet)
        empty_people = "附近没有人" in nearby
        invented_people_terms = ("客人", "顾客", "镇民", "对方")
        if empty_people and any(term in status for term in invented_people_terms):
            return self._default_grounded_action_status(name, agent, packet)
        return status.rstrip("。！？.!")[:10]

    def _enqueue_memory_task(self, agent_name: str, payload: dict) -> MemoryTask:
        task = MemoryTask(
            task_id=f"memq_{self._memory_task_id:06d}",
            agent_name=agent_name,
            payload=dict(payload or {}),
        )
        self._memory_task_id += 1
        self._memory_queue.enqueue(task)
        return task

    def _enqueue_conversation_memory(self, speaker: str, listener: str, transcript) -> None:
        for agent_name in (speaker, listener):
            self._enqueue_memory_task(
                agent_name,
                {
                    "kind": "conversation_completed",
                    "speaker": speaker,
                    "listener": listener,
                    "transcript": list(transcript or []),
                    "day": self.day,
                    "game_hour": self.game_hour,
                },
            )

    def _process_next_memory_task(self) -> bool:
        if self._memory_worker_active:
            return False
        task = self._memory_queue.pop_next()
        if not task:
            return False
        self._memory_worker_active = True
        t = threading.Thread(target=self._run_memory_task, args=(task,), daemon=True)
        self.llm_threads.append(t)
        t.start()
        return True

    def _run_memory_task(self, task: MemoryTask) -> None:
        try:
            agent = self.agents.get(task.agent_name)
            if not agent or not hasattr(agent, "consolidate_memory"):
                return
            try:
                parsed = agent.consolidate_memory(task.payload)
            except Exception as exc:
                with self._lock:
                    self._log(f"[记忆整理] {display_name_for_person(task.agent_name)} 整理失败：{exc}", "system")
                return
            with self._lock:
                current_agent = self.agents.get(task.agent_name)
                if not current_agent:
                    return
                for memory in parsed.get("memories", []):
                    text = str(memory.get("text", "")).strip()
                    if not text:
                        continue
                    if hasattr(current_agent, "add_typed_memory"):
                        current_agent.add_typed_memory(memory_type=memory.get("type", "event"), text=text, payload=memory)
                        if hasattr(current_agent, "add_memory"):
                            current_agent.add_memory(f"memory_consolidation[{memory.get('type', 'event')}]: {text}", self.day)
                    else:
                        current_agent.add_memory(f"记忆整理[{memory.get('type', 'event')}]：{text}", self.day)
                current_goal = str(parsed.get("current_goal", "") or "").strip()
                if current_goal:
                    current_agent.update_scratch(currently=current_goal)
        finally:
            with self._lock:
                self._memory_worker_active = False

    def _init_agents(self):

        """遍历 AGENT_CONFIGS，创建 Agent 对象，初始位置围成圆圈在室外尸体点。"""

        all_names = list(AGENT_CONFIGS.keys())





        # 圆形站位：8 人在尸体旁室外空地均匀分布

        import math as _math

        gather_x = INITIAL_BODY_SITE["x"]

        gather_y = INITIAL_BODY_SITE["y"]

        gather_loc = INITIAL_BODY_SITE["location"]

        if getattr(self, "bodies", None):

            discovered_bodies = [b for b in self.bodies if getattr(b, "discovered", False)]

            if discovered_bodies:

                latest_body = max(discovered_bodies, key=lambda b: getattr(b, "created_day", 0))

                gather_x, gather_y = latest_body.x, latest_body.y

                gather_loc = getattr(latest_body, "location", INITIAL_BODY_SITE["location"])

        radius = 7

        n = len(all_names)

        circle_positions = [

            (round(gather_x + radius * _math.cos(i * 2 * _math.pi / n)),

             round(gather_y + radius * _math.sin(i * 2 * _math.pi / n)))

            for i in range(n)

        ]

        gathering_component = self._reachable_component((gather_x, gather_y))





        occupied_spawn_tiles = set()

        for i, name in enumerate(all_names):

            if name in self.werewolf_names:

                role = "werewolf"

            elif name == self.detective_name:

                role = "detective"

            else:

                role = "villager"





            agent = Agent(name, role)

            agent.init_files()

            agent.init_scratch_from_soul()





            cx, cy = circle_positions[i]

            spawn_tile = self._nearest_walkable_tile_in_component(

                (cx, cy),

                gathering_component,

                radius=6,

                blocked=occupied_spawn_tiles,

            )

            if not spawn_tile:

                spawn_tile = self._nearest_walkable_tile(

                    (cx, cy),

                    radius=6,

                    blocked=occupied_spawn_tiles,

                )

            if spawn_tile:

                cx, cy = spawn_tile

            occupied_spawn_tiles.add((cx, cy))

            agent.x = cx

            agent.y = cy

            agent.target_x = cx

            agent.target_y = cy

            agent.current_action = ""

            agent.current_emoji = "\U0001f4ac"

            agent.current_location = gather_loc

            agent.runtime_state = "idle"

            agent._is_thinking = False

            agent._last_llm_decision_time = 0

            agent._next_llm_retry_time = 0

            agent._departure_delay_until = 0





            self.agents[name] = agent





        # 引擎级单次扫描空间记忆，所有 NPC 共享

        shared_spatial_memory = self._build_shared_spatial_memory()

        for name, agent in self.agents.items():

            try:

                agent.load_shared_spatial_memory(shared_spatial_memory)

            except Exception as e:

                print(f"[Spatial Memory Error] {name}: {e}", file=sys.stderr, flush=True)

            # 初始化 pending action 和 action 完成标志

            agent._pending_action = None

            agent._action_completed = False





        self._log(f"游戏开始！小镇居民聚集在 {gather_loc} 的尸体附近。")





    def set_socketio(self, socketio_instance):

        """注入 SocketIO 实例，用于状态广播"""

        self._socketio = socketio_instance





    def _broadcast_state(self):

        """通过 SocketIO 广播当前游戏状态给所有客户端"""

        if self._socketio is not None:

            try:

                self._socketio.emit("game_state", self.get_status())

            except Exception:

                pass





    def _build_shared_spatial_memory(self) -> dict:

        """引擎级单次扫描：构建所有 NPC 共享的空间记忆树"""

        tree = {}

        for y in range(100):

            for x in range(140):

                info = get_tile_scene(x, y, self.sector_maze, self.arena_maze, self.go_maze,

                                      self.sector_dict, self.arena_dict, self.go_dict)

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

        return tree





    # ==================== 聚集讨论阶段（Day 1 开场，串行） ====================





    def _init_gathering(self):

        """初始化 Day 1 聚集讨论阶段 — 串行轮流发言。

        发言顺序：Crow 第一，其余 NPC 按逆时针环绕 INITIAL_BODY_SITE 排列。"""

        import math as _math

        alive = [n for n, a in self.agents.items() if a.is_alive]





        # 计算每个幸存者的角度并逆时针排序（Crow 排在最前）

        body_x = INITIAL_BODY_SITE["x"]

        body_y = INITIAL_BODY_SITE["y"]

        angle_name_pairs = []

        for name in alive:

            agent = self.agents[name]

            angle = _math.atan2(agent.y - body_y, agent.x - body_x)

            angle_name_pairs.append((angle, name))





        # 逆时针排序（atan2 返回 -π..π，逆时针即角度递增）

        angle_name_pairs.sort(key=lambda p: p[0])





        # Crow 置顶，其余居民从 Crow 的逆时针相邻位置继续绕圈，避免发言跳到圆圈另一侧。

        detective_angle = next(

            angle for angle, name in angle_name_pairs if name == self.detective_name

        )

        resident_pairs = [

            (angle, name)

            for angle, name in angle_name_pairs

            if name != self.detective_name

        ]

        split_idx = next(

            (idx for idx, (angle, _) in enumerate(resident_pairs) if angle > detective_angle),

            0,

        )

        ordered = [self.detective_name] + [

            name for _, name in resident_pairs[split_idx:] + resident_pairs[:split_idx]

        ]





        self._gathering_queue = ordered

        self._gathering_speech_history = []

        self._gathering_current_speech = ""

        self._gathering_left = {n: False for n in self._gathering_queue}

        self._gathering_active = True

        self._gathering_busy = False

        self._gathering_round = 1

        self._gathering_speaker_idx = 0

        self._gathering_next_tick = time.time() + 5  # 给用户 5 秒看到 NPC 聚集画面再开始发言

        self._gathering_speak_start_time = 0

        self._gathering_turn_seq = 0

        self._gathering_active_turn = None

        self._gathering_crow_intro_done = False

        self._gathering_crow_dismissal_done = False

        self._gathering_dismissal_ready_at = None

        self._body_burial = None

        self._log(f"🏘️ 聚集讨论开始！{len(self._gathering_queue)} 位居民聚集在尸体附近，Crow 将先发言")





    def _begin_gathering_turn(self, name: str, round_no: int) -> int:

        """Create a token for the currently pending LLM-backed gathering turn."""

        with self._lock:

            self._gathering_turn_seq = getattr(self, "_gathering_turn_seq", 0) + 1

            turn_id = self._gathering_turn_seq

            self._gathering_active_turn = {

                "id": turn_id,

                "name": name,

                "round": round_no,

                "completed": False,

            }

            self._gathering_speak_start_time = time.time()

            return turn_id





    def _complete_gathering_turn(self, turn_id: int, name: str, round_no: int) -> bool:

        """Return False if a delayed LLM response belongs to an expired turn."""

        with self._lock:

            turn = getattr(self, "_gathering_active_turn", None)

            if not turn:

                return False

            if turn.get("id") != turn_id or turn.get("name") != name or turn.get("round") != round_no:

                return False

            if turn.get("completed"):

                return False

            turn["completed"] = True

            return True





    def _expire_gathering_turn(self) -> None:

        with self._lock:

            turn = getattr(self, "_gathering_active_turn", None)

            if turn:

                turn["completed"] = True





    # Bubble timing/display helpers live in EngineBubbleMixin.



    def _departure_speech(self, name: str, location: str, model_speech: str = "") -> str:

        fallback = DEPARTURE_FALLBACKS.get(

            name,

            f"我要去{self._destination_label_zh(location)}处理事情，也会留意异常。",

        )

        speech = self._limit_gathering_speech(model_speech, fallback=fallback)

        if speech.startswith("前往"):

            speech = speech.replace("前往", "我要去", 1)

        location_label = self._destination_label_zh(location)

        generic_location_terms = {

            "Hobbs Cafe": ("咖啡馆", "咖啡店"),

            "The Rose and Crown Pub": ("酒馆", "酒吧"),

            "The Willows Market and Pharmacy": ("药房", "市场"),

            "Harvey Oak Supply Store": ("五金店",),

            "Johnson Park": ("公园",),

        }

        has_acceptable_location = (

            location_label in speech

            or any(term in speech for term in generic_location_terms.get(location, ()))

        )

        if location_label and location_label != location and not has_acceptable_location:

            speech = self._limit_gathering_speech(

                f"我要去{location_label}，{speech}",

                max_chars=78,

                soft_max=84,

                fallback=fallback,

            )

        return speech

    @staticmethod

    def _departure_object(name: str, location: str, model_object: str = "") -> str:

        primary_object = character_primary_object(name, location)

        return primary_object or str(model_object or "").strip() or DEFAULT_DEPARTURE_OBJECTS.get(
            (name, location),

            DEFAULT_DEPARTURE_OBJECTS.get(name, ""),

        )





    @staticmethod

    def _limit_gathering_speech(

        text: str,

        max_chars: int = 9999,

        soft_max: int = 9999,

        fallback: str = "命案很严重，我会如实配合调查。",

    ) -> str:

        """Sanitize visible NPC speech without hard-truncating model output.

        The model prompt should control length. UI/backend display code should
        preserve the model reply so players can distinguish short generation
        from fallback or code-side clipping.
        """

        speech = str(text or "").strip()

        if not speech:

            return fallback

        return speech



    @staticmethod
    def _sanitize_round_one_speech(name: str, text: str) -> str:

        """Keep the first gathering round focused on own whereabouts/unease/plans.



        Strips self-introductions, accusations against named residents, and

        wound/werewolf analysis. Neutral observation words（看见/听见/路过等）

        are preserved; they do NOT trigger a full-sentence fallback.

        Only proactive naming/accusing of other residents triggers removal.



        If the sanitized result is empty, garbled, or too short (<10 substantive

        chars), falls back entirely to the character's safe fallback line.

        """

        display_name = display_name_for_person(name)

        speech = localize_visible_character_names(text).strip()

        if not speech:

            return GATHERING_FALLBACKS.get(name, "命案很严重，我会如实配合调查。")



        # Remove self-introductions: "我是XXX"

        intro_patterns = [

            rf"^我是\s*{re.escape(display_name)}[，,。.\s]*",

            rf"^我是\s*{re.escape(name)}[，,。.\s]*",

        ]

        for pattern in intro_patterns:

            speech = re.sub(pattern, "", speech, count=1, flags=re.IGNORECASE).strip()

        speech = re.sub(r"^(大家好|各位好|各位早)[，,。.\s]*", "", speech).strip()



        # Remove proactive accusations against named residents

        accusation_patterns = [

            r"我怀疑\s*\S+[，,。.\s]*",

            r"我觉得\s*\S+\s*可疑[，,。.\s]*",

            r"\S+\s*很可疑[，,。.\s]*",

            r"\S+\s*最有嫌疑[，,。.\s]*",

            r"我指控\s*\S+[，,。.\s]*",

        ]

        for pattern in accusation_patterns:

            speech = re.sub(pattern, "", speech, count=1, flags=re.IGNORECASE).strip()



        # Strip other resident display names (proactive naming)

        other_display_names = []

        for other in ACTIVE_CHARACTERS.keys():

            if other == name or other == "Crow":

                continue

            other_display_names.append(display_name_for_person(other))

        for od in other_display_names:

            speech = speech.replace(od, "")



        # Remove wound/werewolf analysis phrases (strip the phrase, keep surrounding text)

        wound_patterns = [

            r"伤口\s*(像|是|疑似|看起来).{0,20}?(撕咬|抓伤|抓痕|咬痕|野兽|犬齿|动物)",

            r"(撕咬|抓伤|抓痕|咬痕|野兽|犬齿).{0,20}?(伤口|痕迹|创伤)",

            r"狼人.{0,15}(作案手法|咬痕|抓痕|伤|痕迹|攻击)",

            r"(像|疑似).{0,15}(狼人|野兽).{0,15}(杀|害|攻击|下手)",

        ]

        for pattern in wound_patterns:

            speech = re.sub(pattern, "", speech, count=1, flags=re.IGNORECASE).strip()



        # Remove forbidden content words — strip only the problematic portions,

        # do NOT fallback the entire sentence.

        forbidden_strip_terms = (

            "狼人", "伤口", "撕咬", "抓痕", "野兽", "凶手", "可疑", "怀疑",

            "咬痕", "爪痕", "尸检", "法医", "嫌疑", "指认", "目击",

        )

        for term in forbidden_strip_terms:

            speech = speech.replace(term, "")



        # Clean up double punctuation / space debris from removals

        speech = re.sub(r"[，,\s]{2,}", "，", speech).strip("，, \t\r\n")

        if not speech:

            return GATHERING_FALLBACKS.get(name, "昨晚我按自己的日常待着，今早听到命案后很不安。")



        # If the sanitized text is too short or has lost substantive content,

        # fallback entirely — the model's speech deviated too far from acceptable bounds.

        # Count actual Chinese characters (exclude punctuation/whitespace).

        content_chars = [ch for ch in speech if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿']

        if len(content_chars) < 8:

            return GATHERING_FALLBACKS.get(name, "昨晚我按自己的日常待着，今早听到命案后很不安。")



        return speech





    @staticmethod

    def _destination_label_zh(location: str) -> str:

        return LANDMARK_LABELS_ZH.get(location, location)





    # Bubble timing/display helpers live in EngineBubbleMixin.



    def _start_crow_scene_investigation(self) -> None:

        return



    def _bury_bodies_after_gathering(self) -> None:

        """散会后，警长 Crow 把前置尸体拖到左边公园埋葬，并说一句说明"""

        crow = self.agents.get(self.detective_name)

        if not crow:

            return





        bodies_to_bury = [b for b in self.bodies if not getattr(b, "buried", False)]

        if not bodies_to_bury:

            return





        body = bodies_to_bury[0]

        grave_x, grave_y = 12, 46

        body.burying = True

        body.burial_target_x = grave_x

        body.burial_target_y = grave_y

        self._body_burial = {

            "body_id": body.body_id,

            "stage": "to_body",

            "target_x": grave_x,

            "target_y": grave_y,

            "return_x": crow.x,

            "return_y": crow.y,

        }



        path_result = self._path_adjacent_to((crow.x, crow.y), (body.x, body.y))

        if path_result:

            adj_x, adj_y, path = path_result

            crow.target_x = adj_x

            crow.target_y = adj_y

            self.agent_paths[self.detective_name] = path

            crow.runtime_state = "moving"

        else:

            self._body_burial["stage"] = "dragging"

            self._send_crow_to_burial_target(body)





        text = "我先把尸体移到左侧的约翰逊公园安葬了，不能让它一直躺在广场上。"

        self.chat_bubbles[self.detective_name] = {"text": text, "time": time.time()}

        self._log(f"💬 [埋葬说明] {self.detective_name}: {text}", "chat")





    def _send_crow_to_burial_target(self, body: BodyRecord) -> None:

        crow = self.agents.get(self.detective_name)

        if not crow:

            return

        target = (getattr(body, "burial_target_x", 12), getattr(body, "burial_target_y", 46))

        path_result = self._nearest_reachable_path(

            (crow.x, crow.y),

            target,

            radius=6,

            blocked=self._occupied_tiles({self.detective_name}),

        )

        if path_result:

            tx, ty, path = path_result

            crow.target_x = tx

            crow.target_y = ty

            self.agent_paths[self.detective_name] = path

            crow.runtime_state = "moving"

        else:

            crow.target_x, crow.target_y = target

            self.agent_paths.pop(self.detective_name, None)

            crow.runtime_state = "moving"





    def _send_crow_to_burial_return(self, burial: dict) -> None:

        crow = self.agents.get(self.detective_name)

        if not crow:

            return

        target = (

            int(burial.get("return_x", INITIAL_BODY_SITE["x"])),

            int(burial.get("return_y", INITIAL_BODY_SITE["y"])),

        )

        path_result = self._nearest_reachable_path(

            (crow.x, crow.y),

            target,

            radius=4,

            blocked=self._occupied_tiles({self.detective_name}),

        )

        if path_result:

            tx, ty, path = path_result

            crow.target_x = tx

            crow.target_y = ty

            self.agent_paths[self.detective_name] = path

            crow.runtime_state = "moving"

        else:

            crow.target_x, crow.target_y = target

            self.agent_paths.pop(self.detective_name, None)

            crow.runtime_state = "moving"





    def _update_body_burial_sequence(self) -> None:

        burial = getattr(self, "_body_burial", None)

        if not burial:

            return

        crow = self.agents.get(self.detective_name)

        body = next((b for b in self.bodies if b.body_id == burial.get("body_id")), None)

        stage = burial.get("stage")

        if not crow or not body or (getattr(body, "buried", False) and stage != "returning"):

            self._body_burial = None

            return



        if stage == "to_body":

            if crow.x == crow.target_x and crow.y == crow.target_y and not self.agent_paths.get(self.detective_name):

                burial["stage"] = "dragging"

                body.x, body.y = crow.x, crow.y

                body.location = "Johnson Park"

                self._send_crow_to_burial_target(body)

            return



        if stage == "dragging":

            body.x, body.y = crow.x, crow.y

            body.location = "Johnson Park"

            reached_navigation_target = (

                crow.x == crow.target_x

                and crow.y == crow.target_y

                and not self.agent_paths.get(self.detective_name)

            )

            reached_burial_target = (

                abs(crow.x - getattr(body, "burial_target_x", 12))

                + abs(crow.y - getattr(body, "burial_target_y", 46))

            ) <= 1

            if reached_navigation_target or reached_burial_target:

                body.x = getattr(body, "burial_target_x", 12)

                body.y = getattr(body, "burial_target_y", 46)

                body.burying = False

                body.buried = True

                burial["stage"] = "returning"

                self._send_crow_to_burial_return(burial)

            return



        if stage == "returning":

            reached_return_target = (

                crow.x == crow.target_x

                and crow.y == crow.target_y

                and not self.agent_paths.get(self.detective_name)

            )

            if reached_return_target:

                crow.runtime_state = "idle"

                self._body_burial = None

                self._start_crow_scene_investigation()





    def _handle_gathering(self):

        """每 tick：检查是否该让下一个人发言（串行状态机）"""

        now = time.time()





        if not self._gathering_active:

            return

        if self._gathering_busy:

            speak_elapsed = now - getattr(self, '_gathering_speak_start_time', 0)

            if speak_elapsed > self.gathering_turn_timeout:

                idx = self._gathering_speaker_idx

                queue = self._gathering_queue

                active_turn = getattr(self, "_gathering_active_turn", None) or {}

                name = active_turn.get("name") or (queue[idx] if idx < len(queue) else "unknown")

                self._log(

                    f"[聚集超时] {name} 发言超过{self.gathering_turn_timeout}秒，强制跳过",

                    "system",

                )

                self._expire_gathering_turn()

                # Lock-guard the state mutation to avoid racing with the

                # LLM thread completing at the same instant.

                with self._lock:

                    if not self._gathering_busy:

                        return  # LLM thread already finished

                    if self._gathering_round >= 2:

                        fallback_to = DEFAULT_DESTINATIONS.get(name, "home")

                        fallback = self._departure_speech(name, fallback_to)

                        fallback_object = self._departure_object(name, fallback_to)

                        self._gathering_left[name] = True

                        if name != self.detective_name and name in self.agents:

                            agent = self.agents[name]

                            target_set = self._set_agent_target(agent, name, fallback_to, fallback_object)

                            if target_set:

                                agent._departure_delay_until = time.time() + self._departure_delay_seconds()

                                agent.runtime_state = "moving"

                            else:

                                agent.runtime_state = "idle"

                            agent.current_action = fallback

                        self._gathering_speaker_idx = (idx + 1) % len(queue)

                        self._gathering_speech_history.append({

                            "speaker": name, "speech": fallback,

                            "left": True, "leaving_to": fallback_to, "leaving_object": fallback_object,

                            "leaving_excuse": "处理必要事务（超时跳过）",

                        })

                    else:

                        fallback = self._sanitize_round_one_speech(

                            name,

                            GATHERING_FALLBACKS.get(name, "命案很严重，我会如实配合调查。"),

                        )

                        self._gathering_speaker_idx += 1

                        self._gathering_speech_history.append({"speaker": name, "speech": fallback})

                    self._gathering_current_speech = fallback

                    self._show_gathering_bubble(name, fallback)

                    gap = self._gathering_departure_gap_seconds()
                    self._gathering_next_tick = now + gap

                    self._gathering_busy = False

            return

        if now < self._gathering_next_tick:

            return  # 还没到下一个发言时间





        queue = self._gathering_queue

        n = len(queue)





        if self._gathering_round == 1:

            self._handle_round_one()

        else:

            self._handle_round_two_plus()





    def _handle_round_one(self):

        """第一圈：每人发言，不离开，不动。Crow 率先发言，其余按逆时针顺序。"""

        queue = self._gathering_queue

        idx = self._gathering_speaker_idx





        if idx >= len(queue):

            now = time.time()

            ready_at = getattr(self, "_gathering_dismissal_ready_at", None)

            if ready_at is None:

                delay = float(CONFIG.get("game", {}).get("crow_dismissal_delay_seconds", 1.8))

                self._gathering_dismissal_ready_at = now + delay

                return

            if now < ready_at:

                return

            # 第一圈结束 → 进入第二圈

            self._gathering_round = 2

            self._gathering_speaker_idx = 0

            self._gathering_left[self.detective_name] = True

            self._publish_crow_dismissal()

            self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()

            self._log("🔄 第一圈发言结束，进入第二圈 — 可以开始考虑离开了", "system")

            self._log("🔎 克罗留在案发现场，等待玩家操控", "system")

            return





        speaker = queue[idx]

        self._log(f"💬 轮到 {speaker} (第{idx+1}/{len(queue)}) 发言...", "system")

        self._gathering_busy = True

        self._trigger_round_one_speak(speaker)





    def _publish_crow_dismissal(self) -> None:

        """Crow formally dismisses the morning gathering before residents leave."""

        if getattr(self, "_gathering_crow_dismissal_done", False):

            return

        text = "好，先到这里。大家回到各自该去的地方，继续留意异常；黄昏我会再召集大家讨论。"

        self._gathering_crow_dismissal_done = True

        self._gathering_speech_history.append({

            "speaker": self.detective_name,

            "speech": text,

            "dismissal": True,

        })

        self._gathering_current_speech = text

        self._show_gathering_bubble(self.detective_name, text)

        self._log(f"💬 [散会说明] {self.detective_name}: {text}", "chat")





    def _handle_round_two_plus(self):

        """第二圈：轮流发言后各自离开，不留人"""

        queue = self._gathering_queue

        n = len(queue)

        idx = self._gathering_speaker_idx





        # 找到下一个还没离开的人

        for i in range(n):

            check_idx = (idx + i) % n

            name = queue[check_idx]

            if not self._gathering_left.get(name, False) and self.agents[name].is_alive:

                self._gathering_speaker_idx = check_idx

                self._log(f"💬 轮到 {name} (第{check_idx+1}/{n}) 决定去向...", "system")

                self._gathering_busy = True

                self._trigger_round_two_speak(name)

                return





        # 所有人都走了 → 聚集结束

        self._gathering_active = False

        # Day4: morning discussion ended → auto-start dusk discussion (no free activity)
        if getattr(self, "_day4_no_free_activity", False):
            self._log("🏁 第4天早晨讨论结束！直接进入黄昏投票阶段，无自由活动时间。", "system")
            self._day4_no_free_activity = False
            self._bury_bodies_after_gathering()
            # Auto-start dusk discussion on Day4
            self._transition_to_dusk()
            return

        self._log("🏁 聚集讨论结束！所有居民已分散开始各自的行动", "system")

        self._bury_bodies_after_gathering()

        if not getattr(self, "_body_burial", None):

            self._start_crow_scene_investigation()

        self.day_start_time = time.time()



    def _case_intro_text(self) -> str:

        bodies = [b for b in getattr(self, "bodies", []) if getattr(b, "discovered", False)]

        if bodies:

            body = max(bodies, key=lambda b: getattr(b, "created_day", 0))

            return f"大家安静一下。昨晚{display_name_for_person(body.victim_name)}遇害，请各位依次说明昨晚的行踪和异常动静。"

        return "大家安静一下。昨晚镇上发生了命案，请各位依次说明昨晚的行踪和异常动静。"





    def _case_intro_fallback_lines(self) -> list:

        bodies = [b for b in getattr(self, "bodies", []) if getattr(b, "discovered", False)]

        victim = "镇上的一名居民"

        location = "约翰逊公园东侧空地"

        if bodies:

            body = max(bodies, key=lambda b: getattr(b, "created_day", 0))

            victim = display_name_for_person(body.victim_name)

            location = self._destination_label_zh(getattr(body, "location", "") or location)

        return [

            f"我是克罗，本镇警长。昨夜{victim}在{location}遇害，今早我们才发现。",

            "伤口像是野兽撕咬和抓伤，但现场还没查清，附近的痕迹我也要逐一确认。",

            "现在先别急着猜凶手。请按顺序说清昨晚在哪、见过谁、听见过什么异常。",

            "今天我会逐一问话。谁想起新线索就立刻告诉我；黄昏我们再集合讨论。",

        ]





    def _parse_crow_intro_lines(self, raw: str) -> list:

        text = str(raw or "").strip()

        if not text:

            return []

        try:

            json_str = Agent._extract_json_text(text)

            if json_str:

                parsed = json.loads(json_str)

                if isinstance(parsed, dict):

                    lines = parsed.get("lines") or parsed.get("speech") or []

                else:

                    lines = parsed

                if isinstance(lines, str):

                    lines = [lines]

                if isinstance(lines, list):

                    return [str(line).strip() for line in lines if str(line).strip()]

        except Exception:

            pass

        lines = []

        for part in re.split(r"[\n]+", text):

            part = part.strip(" -\t\r")

            if part:

                lines.append(part)

        return lines



    def _balance_crow_intro_lines(

        self,

        lines: list,

        fallback_lines: list,

        immediate_line: str,

    ) -> list:

        """Keep Crow's intro bubbles close in length and pacing."""

        cleaned = []

        for line in lines:

            text = localize_visible_character_names(line).strip()

            if text and text != immediate_line:

                cleaned.append(text)

        if len(cleaned) < 3:

            existing = set(cleaned)

            cleaned.extend(line for line in fallback_lines[1:] if line not in existing)



        balanced = []

        for line in cleaned:

            if balanced and len(balanced[-1]) < 28 and len(balanced[-1] + line) <= 78:

                balanced[-1] = balanced[-1].rstrip("。！？") + "，" + line

            else:

                balanced.append(line)



        if len(balanced) > 4:

            tail = "，".join(part.strip("。！？") for part in balanced[3:])

            balanced = balanced[:3] + [tail]



        return [

            self._limit_gathering_speech(

                line,

                max_chars=78,

                fallback="昨夜发生命案，我会先调查现场和周边线索。",

            )

            for line in balanced[:4]

        ]





    def _trigger_crow_case_intro(self, name: str):

        agent = self.agents[name]

        fallback_lines = self._case_intro_fallback_lines()

        immediate_line = fallback_lines[0]

        self._gathering_crow_intro_done = True

        self._gathering_speech_history.append({

            "speaker": name,

            "speech": immediate_line,

            "intro": True,

        })

        self._gathering_current_speech = immediate_line

        self._show_gathering_bubble(name, immediate_line)

        self._log(f"💬 [案情说明] {name}: {immediate_line}", "chat")



        turn_id = self._begin_gathering_turn(name, 1)



        def _pause_after_intro_line(line: str):
            time.sleep(self._crow_intro_line_delay(line))
            with self._lock:
                bubble = self.chat_bubbles.get(name)
                if bubble and bubble.get("text") == line:
                    self.chat_bubbles.pop(name, None)
                if self._gathering_current_speech == line:
                    self._gathering_current_speech = ""
            time.sleep(self._crow_intro_line_delay(line))

        def _do_intro_preset():
            try:

                lines = self._balance_crow_intro_lines(fallback_lines[1:], fallback_lines, immediate_line)

                _pause_after_intro_line(immediate_line)
                if not self._complete_gathering_turn(turn_id, name, 1):

                    self._log(f"[聚集迟到响应] {name} 开场说明已过期，忽略预设台词", "system")

                    return

                for line in lines:

                    self._gathering_speech_history.append({

                        "speaker": name,

                        "speech": line,

                        "intro": True,

                    })

                    self._gathering_current_speech = line

                    self._show_gathering_bubble(name, line)

                    self._log(f"💬 [案情说明] {name}: {line}", "chat")

                    _pause_after_intro_line(line)
                self._gathering_speaker_idx += 1

                self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()

                self._gathering_busy = False

            except Exception as e:

                if not self._complete_gathering_turn(turn_id, name, 1):

                    self._log(f"[聚集迟到错误] {name} 开场说明已过期，忽略错误：{e}", "system")

                    return

                self._log(f"[案情说明错误] {name}: {e}，使用默认开场", "system")

                self._gathering_speaker_idx += 1

                self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()

                self._gathering_busy = False



        threading.Thread(target=_do_intro_preset, daemon=True).start()

        return





    def _trigger_round_one_speak(self, name: str):

        """第一圈发言：只说话，不允许离开"""

        agent = self.agents[name]

        soul = agent.read_soul()

        memory = agent.read_memory()





        if name.lower() == self.detective_name.lower() or name.lower() == "crow":

            self._trigger_crow_case_intro(name)

            return



        display_name = display_name_for_person(name)

        focus_options = [

            "重点说说你昨晚在什么地方、做了什么。",

            "重点说说你现在心里最不踏实的一件事。",

            "重点说说你今天准备去做什么。",

            "重点说说你昨晚有没有听到或看到什么异常动静。",

        ]

        focus_text = focus_options[(self.day + self._gathering_speaker_idx + len(name)) % len(focus_options)]



        history_lines = []

        for entry in self._gathering_speech_history:

            history_lines.append(f"{display_name_for_person(entry['speaker'])} 说：\"{entry['speech'][:120]}\"")

        history_text = "\n".join(history_lines) if history_lines else "(还没人说话，你是第一个)"





        role_hint = ""

        if agent.role == "werewolf":

            role_hint = "\n⚠️ 重要：你是狼人！在白天你必须伪装成一个普通居民。绝不能暴露你是狼人。"





        system_prompt = f"""你是{display_name}，一个小镇居民。

你的灵魂设定：{soul}{role_hint}

{active_town_people_rule()}

当前场景：现在是早晨，所有居民聚集在尸体附近。大家正在轮流发言，每人说一小段话。镇上刚发现命案，气氛应当严肃、紧张、克制。




之前大家的发言（按顺序）：

{history_text}





你的记忆：

{safe_truncate(memory, 500)}





## 任务（第一轮发言 — 只能说话，不能离开）

请发表你的第一轮发言。不要自我介绍，不要说”我是……”。直接说 1-2 句完整、自然、有个人细节的话（60个中文字左右，单句约30字以内，不要长复句，不要为了凑字数重复，不要像模板），谈谈：
- 昨晚你在哪里，做了什么

- 你现在心里最不踏实的是什么

- 你今天打算做什么

- 本次发言角度：{focus_text}





⚠️ 极其重要：

1. 第一轮只是发言，你还不能离开广场。

2. 不要提”我要走了”、”我先离开了”、”去忙了”等离开相关的话。

3. 只谈你昨晚的行踪、你现在的不安、你今天要做什么。

4. ❌ 禁止主动点名或指责其他居民，第一轮不是互相指认环节。可以说”我看到有人路过”但不提具体是谁。

5. ❌ 禁止分析伤口或讨论狼人作案手法。

6. 语气必须符合命案现场：严肃、担心、压抑或警惕；不要开心、玩笑、兴奋或轻松。

7. 不要介绍自己是谁，不要复述你的名字。

8. 所有人名只能使用中文名，不要输出英文名或全名。

9. 直接输出你的发言文本，不要返回 JSON 格式。"""




        turn_id = self._begin_gathering_turn(name, 1)





        def _do_speak():

            try:

                raw_holder = {"raw": None, "done": False}





                def _call_model():

                    try:

                        raw_holder["raw"] = chat_for_agent(

                            name, system_prompt, "请发表你的第一轮发言", max_retries=0, priority=True,

                        )

                    finally:

                        raw_holder["done"] = True





                llm_thread = threading.Thread(target=_call_model, daemon=True)

                llm_thread.start()

                llm_thread.join(timeout=self.gathering_per_speaker_timeout)





                if not self._complete_gathering_turn(turn_id, name, 1):

                    self._log(f"[聚集迟到响应] {name} 第一轮发言已过期，忽略模型返回", "system")

                    return

                raw = raw_holder["raw"]

                if raw:

                    speech = raw.strip()

                else:
                    if not raw_holder["done"]:
                        self._log(
                            f"[聚集发言超时保底] {display_name_for_person(name)} 模型未在{self.gathering_per_speaker_timeout}秒内返回，使用备用发言。",
                            "system",
                        )
                    self._log(
                        f"[模型超时/空结果，使用保底发言] {display_name_for_person(name)} 第一轮发言",
                        "system",
                    )
                    speech = GATHERING_FALLBACKS.get(name, "命案很严重，我会如实说明昨晚情况。")
                speech = self._sanitize_round_one_speech(name, speech)

                speech = self._limit_gathering_speech(

                    speech,

                    fallback=GATHERING_FALLBACKS.get(name, "命案很严重，我会如实说明昨晚情况。"),

                )





                self._gathering_speech_history.append({

                    "speaker": name, "speech": speech

                })

                self._gathering_current_speech = speech





                self._show_gathering_bubble(name, speech)

                self._log(f"💬 [聚集R1] {name}: {speech[:150]}", "chat")





                self._gathering_speaker_idx += 1

                self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()
                self._gathering_busy = False





            except Exception as e:

                if not self._complete_gathering_turn(turn_id, name, 1):

                    self._log(f"[聚集迟到错误] {name} 第一轮发言已过期，忽略错误：{e}", "system")

                    return

                self._log(f"[聚集R1错误] {name}: {e}，使用默认发言", "system")

                fallback = self._sanitize_round_one_speech(

                    name,

                    GATHERING_FALLBACKS.get(name, "命案很严重，我会如实配合调查。"),

                )

                self._gathering_speech_history.append({

                    "speaker": name, "speech": fallback

                })

                self._gathering_current_speech = fallback

                self._show_gathering_bubble(name, fallback)

                self._log(f"💬 [聚集R1] {name}: {fallback}", "chat")

                self._gathering_speaker_idx += 1

                self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()
                self._gathering_busy = False





        t = threading.Thread(target=_do_speak, daemon=True)

        t.start()





    def _trigger_round_two_speak(self, name: str):
        """第二圈发言：NPC说明离开理由，然后延迟片刻再去具体物件位置。"""
        if name.lower() == self.detective_name.lower() or name.lower() == "crow":
            with self._lock:
                self._gathering_left[name] = True
                if self._gathering_queue:
                    self._gathering_speaker_idx = (self._gathering_speaker_idx + 1) % len(self._gathering_queue)
                self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()
                self._gathering_busy = False
            return

        agent = self.agents[name]
        default_dest = DEFAULT_DESTINATIONS.get(name, "home")
        display_name = display_name_for_person(name)

        history_lines = []
        for entry in self._gathering_speech_history:
            left_note = f" [已离开，去{entry.get('leaving_to', '?')}]" if entry.get("left") else ""
            history_lines.append(f"{display_name_for_person(entry['speaker'])}说：{entry['speech'][:120]}{left_note}")
        history_text = "\n".join(history_lines) if history_lines else "暂无"

        left_list = [n for n, v in self._gathering_left.items() if v]
        left_text = "、".join(display_name_for_person(n) for n in left_list) if left_list else "还没人离开"
        role_hint = "\n你是狼人，必须像普通居民一样自然离开，不能暴露身份。" if agent.role == "werewolf" else ""

        system_prompt = f"""你是{display_name}，小镇居民。
角色设定：{agent.read_soul()}{role_hint}
{active_town_people_rule()}

当前是命案后的早晨，第一轮说明已经结束。你现在要离开广场，去做符合你身份和日程的具体事情。

之前发言：
{history_text}

已经离开的人：{left_text}

你的近期记忆：
{safe_truncate(agent.read_memory(), 500)}

只返回 JSON：
{{
  "speech": "向大家说明你要去做什么和为什么，60到72个中文字左右，完整句最多约75字，严肃克制。",
  "leaving_excuse": "一句自然理由",
  "leaving_to": "home/Hobbs Cafe/The Rose and Crown Pub/The Willows Market and Pharmacy/Oak Hill College/Harvey Oak Supply Store/Johnson Park 之一",
  "leaving_object": "抵达后要接近或操作的具体物件"
}}

不要编造小镇不存在的人、地点或物件。不要在这一步公开指控别人，只解释自己接下来要去做的事。"""

        turn_id = self._begin_gathering_turn(name, 2)

        def _advance_queue_locked():
            queue = self._gathering_queue
            n = len(queue)
            if not n:
                return
            for i in range(1, n + 1):
                next_idx = (self._gathering_speaker_idx + i) % n
                next_name = queue[next_idx]
                if not self._gathering_left.get(next_name, False) and self.agents[next_name].is_alive:
                    self._gathering_speaker_idx = next_idx
                    return
            self._gathering_speaker_idx = (self._gathering_speaker_idx + 1) % n

        def _fallback_result(reason: str = "") -> dict:
            fallback_to = default_dest
            fallback_speech = self._departure_speech(name, fallback_to, "")
            if reason:
                self._log(reason, "system")
            self._log(
                f"[模型超时/空结果，使用保底发言] {display_name} 第二轮去向",
                "system",
            )
            return {
                "speech": fallback_speech,
                "leaving_excuse": "处理自己的日常事务",
                "leaving_to": fallback_to,
                "leaving_object": "",
            }

        def _do_speak():
            try:
                raw_holder = {"raw": None, "done": False}

                def _call_model():
                    try:
                        raw_holder["raw"] = chat_for_agent(
                            name,
                            system_prompt,
                            "请决定你要去哪里并告别",
                            max_retries=0,
                            priority=True,
                        )
                    finally:
                        raw_holder["done"] = True

                llm_thread = threading.Thread(target=_call_model, daemon=True)
                llm_thread.start()
                llm_thread.join(timeout=self.gathering_per_speaker_timeout)

                if not self._complete_gathering_turn(turn_id, name, 2):
                    self._log(f"[聚集迟到响应] {display_name} 第二轮去向已过期，忽略模型返回", "system")
                    return

                raw = raw_holder["raw"]
                result = self._parse_gathering_json(raw, name) if raw else {}
                if not result:
                    if raw_holder["done"]:
                        result = _fallback_result(f"[聚集去向空结果保底] {display_name} 模型返回为空或无法解析，使用备用去向。")
                    else:
                        result = _fallback_result(
                            f"[聚集去向超时保底] {display_name} 模型未在{self.gathering_per_speaker_timeout}秒内返回，使用备用去向。"
                        )

                leaving_to = self._normalize_destination(name, result.get("leaving_to", default_dest))
                if leaving_to not in LANDMARKS and leaving_to != "home":
                    leaving_to = default_dest
                leaving_excuse = str(result.get("leaving_excuse") or "处理自己的日常事务").strip()
                speech = localize_visible_character_names(
                    self._departure_speech(name, leaving_to, result.get("speech", ""))
                )
                leaving_object = self._resolve_concrete_target_object(
                    agent,
                    leaving_to,
                    self._departure_object(name, leaving_to, result.get("leaving_object", "")),
                    "move_to",
                    speech,
                )

                with self._lock:
                    target_set = self._set_agent_target(agent, name, leaving_to, leaving_object)
                    if target_set:
                        agent._departure_delay_until = time.time() + self._departure_delay_seconds()
                        agent.runtime_state = "moving"
                    else:
                        agent.runtime_state = "idle"
                        self._log(f"[聚集R2移动失败] {display_name} 无法到达 {self._destination_label_zh(leaving_to)}，留在原地", "system")

                    self._gathering_left[name] = True
                    agent.current_action = speech
                    agent.current_emoji = "🚶"
                    self._gathering_speech_history.append({
                        "speaker": name,
                        "speech": speech,
                        "left": True,
                        "leaving_to": leaving_to,
                        "leaving_object": leaving_object,
                        "leaving_excuse": leaving_excuse,
                    })
                    self._gathering_current_speech = speech
                    self._show_gathering_bubble(name, speech)
                    self._log(f"🚶 [聚集R2] {display_name}: {speech}", "action")
                    agent.write_cognition(
                        f"### 第{self.day}天 早晨\n聚集讨论后离开。借口：{leaving_excuse}\n前往：{self._destination_label_zh(leaving_to)} / {leaving_object}"
                    )
                    _advance_queue_locked()
                    self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()
                    self._gathering_busy = False
            except Exception as exc:
                self._log(f"[聚集R2异常保底] {display_name}: {exc}", "system")
                with self._lock:
                    result = _fallback_result()
                    leaving_to = result["leaving_to"]
                    speech = localize_visible_character_names(result["speech"])
                    leaving_object = self._resolve_concrete_target_object(
                        agent,
                        leaving_to,
                        self._departure_object(name, leaving_to, ""),
                        "move_to",
                        speech,
                    )
                    if self._set_agent_target(agent, name, leaving_to, leaving_object):
                        agent._departure_delay_until = time.time() + self._departure_delay_seconds()
                        agent.runtime_state = "moving"
                    else:
                        agent.runtime_state = "idle"
                    self._gathering_left[name] = True
                    self._gathering_speech_history.append({
                        "speaker": name,
                        "speech": speech,
                        "left": True,
                        "leaving_to": leaving_to,
                        "leaving_object": leaving_object,
                        "leaving_excuse": result["leaving_excuse"],
                    })
                    self._gathering_current_speech = speech
                    self._show_gathering_bubble(name, speech)
                    self._log(f"🚶 [聚集R2] {display_name}: {speech}", "action")
                    _advance_queue_locked()
                    self._gathering_next_tick = time.time() + self._gathering_departure_gap_seconds()
                    self._gathering_busy = False

        threading.Thread(target=_do_speak, daemon=True).start()


    def _normalize_destination(self, name: str, location: str) -> str:

        """Keep LLM-selected destinations inside the known town map."""

        norm_location = "" if location is None else str(location).strip()

        if norm_location == "home" or norm_location in LANDMARKS:

            return norm_location





        location_lower = norm_location.lower()

        if "market" in location_lower or "pharmacy" in location_lower:

            return "The Willows Market and Pharmacy"

        if "supply" in location_lower or "harvey" in location_lower:

            return "Harvey Oak Supply Store"

        if "cafe" in location_lower or "hobbs" in location_lower:

            return "Hobbs Cafe"

        if "pub" in location_lower or "rose" in location_lower or "crown" in location_lower:

            return "The Rose and Crown Pub"

        if "college" in location_lower or "oak hill" in location_lower:

            return "Oak Hill College"

        if "park" in location_lower or "johnson" in location_lower:

            return "Johnson Park"

        return DEFAULT_DESTINATIONS.get(name, "home")





    def _set_agent_target(self, agent, name: str, location: str, target_object: str = ""):

        """设置 NPC 移动目标"""

        norm_location = self._normalize_destination(name, location)

        location = norm_location

        if location != "home" and location not in LANDMARKS:

            location_lower = location.lower()

            if "market" in location_lower or "pharmacy" in location_lower:

                norm_location = "The Willows Market and Pharmacy"

            elif "supply" in location_lower or "harvey" in location_lower or "oak supply" in location_lower:

                norm_location = "Harvey Oak Supply Store"

            elif "cafe" in location_lower or "hobbs" in location_lower:

                norm_location = "Hobbs Cafe"

            elif "pub" in location_lower or "rose" in location_lower or "crown" in location_lower:

                norm_location = "The Rose and Crown Pub"

            elif "college" in location_lower or "oak hill" in location_lower:

                norm_location = "Oak Hill College"

            elif "park" in location_lower or "johnson" in location_lower:

                norm_location = "Johnson Park"

            else:

                norm_location = list(LANDMARKS.keys())[0]





        if norm_location == "home":

            home_cfg = AGENT_CONFIGS.get(name, {}).get("home", {"x": 70, "y": 40})

            obj_coord = self._find_object_in_spatial_memory(agent, "home", target_object) if target_object else None

            if obj_coord:

                path_result = self._path_adjacent_to(

                    (agent.x, agent.y),

                    obj_coord,

                    blocked=self._occupied_tiles({name}),

                )

                if path_result:

                    agent.target_x, agent.target_y, path = path_result

                    self.agent_paths[name] = path

                else:

                    obj_coord = None

            if not obj_coord:

                if not self._assign_reachable_target_near(
                    agent,
                    name,
                    (
                        home_cfg["x"] + self._rng.randint(-2, 2),
                        home_cfg["y"] + self._rng.randint(-2, 2),
                    ),
                    radius=12,
                ):

                    return False

            if (agent.target_x, agent.target_y) == (agent.x, agent.y):
                neighbor = self._neighbor_action_path(name, agent)
                if neighbor:
                    nx, ny, path = neighbor
                    agent.target_x, agent.target_y = nx, ny
                    self.agent_paths[name] = path
            agent.current_location = "home"

            return True

        elif norm_location in LANDMARKS:

            lm = LANDMARKS[norm_location]

            obj_coord = self._find_object_in_spatial_memory(agent, norm_location, target_object) if target_object else None

            if obj_coord:

                path_result = self._path_adjacent_to(

                    (agent.x, agent.y),

                    obj_coord,

                    blocked=self._occupied_tiles({name}),

                )

                if path_result:

                    agent.target_x, agent.target_y, path = path_result

                    self.agent_paths[name] = path

                else:

                    obj_coord = None

            if not obj_coord:

                if not self._assign_reachable_target_near(
                    agent,
                    name,
                    (
                        lm["x"] + self._rng.randint(-2, 2),
                        lm["y"] + self._rng.randint(-2, 2),
                    ),
                    radius=12,
                ):

                    return False

            if (agent.target_x, agent.target_y) == (agent.x, agent.y):
                neighbor = self._neighbor_action_path(name, agent)
                if neighbor:
                    nx, ny, path = neighbor
                    agent.target_x, agent.target_y = nx, ny
                    self.agent_paths[name] = path
            agent.current_location = norm_location

            return True

        return False





    def _resolve_concrete_target_object(

        self,

        agent,

        location: str,

        requested_object: str,

        action_type: str,

        action: str = "",

    ) -> str:

        """Resolve physical actions to a real map object instead of a landmark center."""

        if action_type not in {"move_to", "inspect", "investigate", "work"}:

            return str(requested_object or "").strip()





        primary_object = character_primary_object(getattr(agent, "name", ""), location)
        if primary_object and self._find_object_in_spatial_memory(agent, location, primary_object):

            return primary_object


        requested = str(requested_object or "").strip()

        if requested and self._find_object_in_spatial_memory(agent, location, requested):

            return requested





        fallback = LANDMARK_DEFAULT_OBJECTS.get(location, "")

        if fallback and self._find_object_in_spatial_memory(agent, location, fallback):

            return fallback

        return ""

    def _parse_gathering_json(self, raw: str, name: str) -> dict:

        """解析聚集讨论的 JSON 响应"""

        try:

            json_str = Agent._extract_json_text(raw)

            if not json_str:

                raise ValueError("no valid JSON object found")

            result = json.loads(json_str)

            if not isinstance(result, dict):

                return {}

            return result

        except Exception:

            self._log(f"[聚集JSON解析错误] {name}: {raw[:200]}", "system")

            return {}





    def _log(self, message: str, log_type: str = "system"):

        """记录日志（线程安全，带自增id）"""

        with self._lock:

            entry = {"day": self.day, "phase": self.phase.value, "message": message, "time": time.time(), "type": log_type, "id": self._log_id}

            self._log_id += 1

            self.game_log.append(entry)

        try:

            print(f"[Day{self.day}/{self.phase.value}] [{log_type}] {message}", file=sys.stderr, flush=True)

        except UnicodeEncodeError:

            pass





    @staticmethod
    def _is_player_visible_log_entry(entry) -> bool:
        """Return whether a log entry belongs in the player-facing agent log."""
        log_type = str(entry.get("type") or "system")
        message = str(entry.get("message") or "")
        stripped = message.strip()

        if log_type == "llm_raw":
            return False

        if "超时" in stripped and (
            "LLM" in stripped or "模型" in stripped or "大模型" in stripped
        ):
            return True

        debug_markers = (
            "LLM请求",
            "大模型请求",
            "模型原始输出",
            "行动解析",
            "行动理由",
            "路径失败",
            "NPC聊天",
            "聚集迟到",
            "聚集JSON解析错误",
        )
        if any(marker in stripped for marker in debug_markers):
            return False

        if log_type == "system":
            return False

        if log_type == "think":
            return stripped.startswith("💭")

        if log_type == "action":
            if stripped.startswith("["):
                return stripped.startswith(("[行动计划]", "[开始行动]", "[行动结果]"))
            return stripped.startswith(("📋", "🚶", "🔎", "🔧", "💍", "🔨", "⚠️"))

        return log_type in {"chat", "kill", "error"}

    # ==================== 生命周期 ====================




    def start(self):

        """设 _running=True，启动 _game_loop 线程"""

        self._running = True

        self.phase = GamePhase.DAY

        self.day_start_time = time.time()

        self.game_hour = 7

        self._init_gathering()

        if CONFIG.get("llm", {}).get("enable_daily_plan_on_start", False):

            self._generate_daily_plans(wait=False)

        for name, agent in self.agents.items():

            self._log(f"🚀 {name}: 状态=idle，等待LLM决策", "system")

        # 聚集阶段不触发自主行动决策，等聚集结束后再开始

        # self._update_agent_schedules()

        self._log(f"第{self.day}天白天开始 — 居民们在尸体附近聚集讨论")





        self._thread = threading.Thread(target=self._game_loop, daemon=True)

        self._thread.start()





    def stop(self):

        self._running = False



    def new_game(self, random_seed=None):

        """Reset all game state for a fresh start. Clears agents, logs, runtime state.



        Caller must re-set socketio and re-start the game loop via start().

        """

        # Clear game-level runtime

        self.day = 1

        self.phase = GamePhase.DAY

        self.game_hour = 7

        self.game_log.clear()

        self.dead_list.clear()

        self.clues.clear()

        self.game_over = False

        self.winner = None

        self.day_start_time = None

        self.night_start_time = None

        self.day_time_expired = False

        self.dusk_start_time = None

        self._daily_interviewed = set()

        self._daily_normal_chats = {}

        self._jailed = set()

        self._dusk_votes.clear()
        self._dusk_vote_reasons.clear()
        self._dusk_vote_active = False
        self._dusk_discussion_active = False
        self._dusk_discussion_statements = []
        self._dusk_crow_statement = ""
        self._dusk_jail_target = None
        self._vote_history.clear()

        self.chat_bubbles.clear()

        self.agent_paths.clear()

        self.llm_threads.clear()

        self.llm_tick_counter = 0

        self.llm_reflect_idx = 0

        self._chat_round_count = {}

        self._silver_bullet_acquired = False

        self._silver_jewelry_acquired = False

        self._silver_bullet_crafted = False

        self._silver_bullet_used = False

        self._silver_knife_used = False
        self._silver_knife_night_checked = False
        self._silver_knife_phase_started_at = 0.0
        self._silver_knife_scrapped_tonight = False
        self._silver_knife_target_tonight = ""
        self._silver_knife_killed_werewolf_tonight = False

        self._day4_no_free_activity = False
        self._pending_silver_wolf = ""

        self._silver_task_done_today = None

        self._detective_chat_active_target = None
        self._detective_chat_pending_target = None
        self._detective_chat_job_id = 0
        self._observation_events = []
        self._observation_event_id = 1
        self._memory_queue = MemoryQueue()
        self._memory_task_id = 1
        self._memory_worker_active = False
        self._silver_jewelry_holder = ""

        self._silver_knife_holder = ""

        # Reset gathering state

        self._gathering_active = False

        self._gathering_busy = False

        self._gathering_round = 1

        self._gathering_queue = []

        self._gathering_speech_history = []

        self._gathering_current_speech = ""

        self._gathering_left = {}

        self._gathering_speaker_idx = 0

        self._gathering_next_tick = 0

        self._gathering_speak_start_time = 0

        self._gathering_turn_seq = 0

        self._gathering_active_turn = None

        self._gathering_crow_intro_done = False

        self._gathering_crow_dismissal_done = False

        self._gathering_dismissal_ready_at = None

        self._body_burial = None

        self._log_id = 0

        self._npc_chat_tokens.clear()



        # Regenerate wolf selection and re-init agents with fresh positions

        if random_seed is not None:

            self._rng = random.Random(random_seed)

        non_crow = [k for k in ACTIVE_CHARACTERS.keys() if k != "Crow"]

        self.werewolf_names = self._rng.sample(non_crow, 2)

        self.werewolf_name = self.werewolf_names[0]

        self._rng.shuffle(non_crow)  # re-randomize for silver holders



        # Re-assign roles and positions

        body_victim = self._rng.choice(AMBIENT_RESIDENT_SPRITES)

        self.bodies = [BodyRecord(

            body_id=f"body_{body_victim.replace(' ', '_')}",

            victim_name=body_victim,

            x=INITIAL_BODY_SITE["x"],

            y=INITIAL_BODY_SITE["y"],

            location=INITIAL_BODY_SITE["location"],

            discovered=True,

            created_day=1,

        )]

        self._silver_jewelry_holder = non_crow[0]

        non_crow_non_wolf = [n for n in non_crow if n not in self.werewolf_names]

        self._silver_knife_holder = self._rng.choice(non_crow_non_wolf) if non_crow_non_wolf else None

        # Clear and re-init agents

        self.agents.clear()

        self._init_agents()

        self._log("🔄 游戏已重置为全新状态")

        return self





    def _game_loop(self):

        """while running: sleep(tick) → DAY→_day_tick / NIGHT→_night_tick → broadcast state"""

        while self._running and not self.game_over:

            time.sleep(self.tick_interval)

            try:

                with self._lock:

                    if self.phase == GamePhase.DAY:

                        self._day_tick()

                    elif self.phase == GamePhase.DUSK_DISCUSSION:

                        self._dusk_tick()

                    elif self.phase == GamePhase.NIGHT:

                        self._night_tick()

                    self._process_next_memory_task()

                # 锁外广播状态，避免阻塞游戏循环

                self._broadcast_state()

            except Exception as e:

                print(f"[FATAL] 游戏循环异常: {e}", file=sys.stderr, flush=True)

                import traceback

                traceback.print_exc()





    def _start_stage_reflection(self, stage: str) -> None:
        if not getattr(self, "_running", False):
            return
        if stage != "night_start":
            return

        def _reflect(agent_name: str, agent) -> None:
            try:
                if hasattr(agent, "daily_reflection"):
                    agent.daily_reflection(self.day, getattr(self, "dead_agents", []))
            except Exception as exc:
                with self._lock:
                    self._log(f"[阶段反思] {display_name_for_person(agent_name)} 失败：{exc}", "system")

        for agent_name, agent in list(self.agents.items()):
            if agent_name == self.detective_name or not getattr(agent, "is_alive", False):
                continue
            thread = threading.Thread(target=_reflect, args=(agent_name, agent), daemon=True)
            self.llm_threads.append(thread)
            thread.start()

    def _day_tick(self):

        """1.更新时间(game_hour) 2._handle_gathering(仅Day1) 3._update_agent_schedules() 4._move_agents() 5.LLM tick"""

        self._expire_chat_bubbles()

        elapsed = time.time() - self.day_start_time





        if elapsed >= self.day_duration:

            self.day_time_expired = True





        game_seconds_per_real = (17 * 3600) / self.day_duration

        game_elapsed = elapsed * game_seconds_per_real

        self.game_hour = 7 + game_elapsed / 3600

        if self.game_hour >= 24:

            self.game_hour = 24

            self.day_time_expired = True





        # === 聚集讨论阶段（仅在Day 1，且聚集未结束） ===

        if getattr(self, '_gathering_active', False):

            self._handle_gathering()

            # 第二圈才允许移动（NPC决定离开后需要走向目的地）

            if getattr(self, '_gathering_round', 1) >= 2:

                self._move_agents()

            return





        self._update_agent_schedules()

        self._move_agents()





        self.llm_tick_counter += 1

        if self.llm_tick_counter >= self.llm_interval:

            self.llm_tick_counter = 0

            self.llm_reflect_idx += 1

            # Stage reflection is triggered by explicit phase transitions, not the day tick.





    def _night_tick(self):
        """Night phase machine: werewolf hunt → silver knife (60s) → complete.

        Stage 1 (werewolf): Wolf selects targets and kills. Advances until hunt completes.
        Stage 2 (silver_knife): Always runs for exactly _silver_knife_phase_duration seconds,
        regardless of whether the silver knife holder is dead, knife already used,
        or holder chooses not to kill. The UI must not leak secret info by skipping this phase.
        Stage 3 (complete): Night done, waiting for player confirmation.
        """
        progress = getattr(self, "_night_progress", {})
        current_stage = progress.get("stage", "werewolf")

        if current_stage == "werewolf":
            self._advance_night_hunt()
            hunt = getattr(self, "night_hunt", None)
            # Transition to silver_knife stage when hunt completes (killed or deadline reached)
            if hunt and hunt.killed_name:
                # Wolf has killed. Check if the victim was the silver knife holder.
                if hunt.killed_name == self._silver_knife_holder and not self._silver_knife_used:
                    self._silver_knife_scrapped_tonight = True
                    self._log("⚠️ 银质小刀阶段仍会照常记录。", "system")
                # Move to silver knife stage
                self._silver_knife_phase_started_at = time.time()
                progress.update({"active": True, "stage": "silver_knife", "complete": False})
                self._night_progress = progress
                self._log("🔪 银质小刀阶段开始（无论持刀者是否存活或是否使用，此阶段都会记录60秒）")
                self._maybe_use_silver_knife_at_night()
            else:
                # Check if overall night_duration time has passed (wolf phase timeout fallback)
                elapsed = time.time() - self.night_start_time
                if elapsed >= self.night_duration:
                    # Timeout: force the wolf kill
                    self._advance_night_hunt(now=self.night_hunt.deadline_at if self.night_hunt else time.time())
                    self._silver_knife_phase_started_at = time.time()
                    progress.update({"active": True, "stage": "silver_knife", "complete": False})
                    self._night_progress = progress
                    self._maybe_use_silver_knife_at_night()

        elif current_stage == "silver_knife":
            # Silver knife phase: always runs for _silver_knife_phase_duration seconds
            knife_elapsed = time.time() - self._silver_knife_phase_started_at
            # Execute the knife logic at the start of this phase (one-shot)
            self._maybe_use_silver_knife_at_night()
            if knife_elapsed >= self._silver_knife_phase_duration:
                progress.update({"active": False, "stage": "complete", "complete": True})
                self._night_progress = progress
                self._log("🌙 夜晚结束（所有阶段已完成）")

    def confirm_night_transition(self) -> dict:
        with self._lock:
            if self.phase != GamePhase.NIGHT:
                return {"success": False, "error": "当前不是夜晚阶段"}
            progress = getattr(self, "_night_progress", {})
            if not progress.get("complete"):
                return {"success": False, "error": "夜晚尚未结束"}
            self._transition_to_day()
            return {"success": True, "phase": self.phase.value, "day": self.day}





    # Dusk discussion/vote helpers live in EngineDuskMixin.



    # Daily task helpers live in EngineTasksMixin.



    def acquire_silver_bullet(self) -> dict:

        """Crow attempts to acquire the silver bullet tool from Arthur at Harvey Oak Supply Store.





        Returns dict with success/failure, and clues/suspicion if blocked.

        If Arthur is a werewolf or blocked by a werewolf, acquisition can fail.

        """

        with self._lock:

            if self._silver_bullet_acquired:

                return {"success": True, "message": "银子弹工具已获取", "already_acquired": True}

            if self._silver_task_done_today:

                return {"success": False, "error": "今天已经完成过一项关键银器行动，明天再继续"}





            arthur = self.agents.get("Arthur Burton")

            if not arthur or not arthur.is_alive:

                return {"success": False, "error": "亚瑟·伯顿已死亡或不存在"}

            if "Arthur Burton" in self._jailed:

                return {"success": False, "error": "亚瑟·伯顿已被拘留，无法获取银子弹"}





            # Check if Crow is near Harvey Oak Supply Store

            crow = self.agents.get(self.detective_name)

            supply_coords = PUBLIC_LANDMARKS["Harvey Oak Supply Store"]

            dist_to_store = abs(crow.x - supply_coords["x"]) + abs(crow.y - supply_coords["y"])

            if dist_to_store > 8:

                return {"success": False, "error": "需要前往哈维橡树五金店才能获取银子弹工具"}





            # Deterministic fallback: acquisition succeeds unless Arthur is a werewolf

            if arthur.role == "werewolf":

                # Arthur refuses, produces clues

                self._log("⚠️ 亚瑟拒绝提供银子弹工具，行为可疑！", "action")

                self.create_clue(

                    clue_type="suspicious_behavior",

                    summary="亚瑟·伯顿拒绝提供银子弹工具，声称店里没有。但他的态度非常紧张不安。",

                    source=self.detective_name,

                    related_person="Arthur Burton",

                    location="Harvey Oak Supply Store",

                )

                return {

                    "success": False,

                    "error": "亚瑟拒绝提供银子弹工具",

                    "suspicious": True,

                    "clue": "亚瑟·伯顿的行为非常可疑，他似乎在隐瞒什么。",

                }





            # Success

            self._silver_bullet_acquired = True

            self._silver_task_done_today = "silver_bullet"

            self._log("🔧 Crow 从亚瑟处获得了银子弹工具！", "action")

            return {

                "success": True,

                "message": "从亚瑟·伯顿处获得了银子弹工具",

                "silver_bullet_acquired": True,

            }





    def acquire_silver_jewelry(self, target_name: str = None) -> dict:

        """Crow attempts to acquire silver jewelry from the hidden holder.





        Crow must specify who they think the holder is (or the system uses the known holder).

        Returns dict with success/failure.

        """

        with self._lock:

            if self._silver_jewelry_acquired:

                return {"success": True, "message": "银饰物已获取", "already_acquired": True}





            holder_name = self._silver_jewelry_holder

            holder = self.agents.get(holder_name)

            if self._silver_task_done_today:

                return {"success": False, "error": "今天已经完成过一项关键银器行动，明天再继续"}

            if not holder or not holder.is_alive:

                return {"success": False, "error": "银饰物持有者已死亡或不存在"}

            if holder_name in self._jailed:

                return {"success": False, "error": f"{display_name_for_person(holder_name)}已被拘留"}





            # If target is specified, check if it matches the holder

            if target_name and target_name != holder_name:

                return {

                    "success": False,

                    "error": f"{display_name_for_person(target_name)}不是银饰物持有者",

                    "hint": "银饰物在其他居民手中",

                }





            # Check proximity

            crow = self.agents.get(self.detective_name)

            dist = abs(crow.x - holder.x) + abs(crow.y - holder.y)

            if dist > 5:

                return {"success": False, "error": f"需要靠近{display_name_for_person(holder_name)}才能获取银饰物"}





            # Deterministic: holder gives jewelry unless they are a werewolf

            if holder.role == "werewolf":

                self._log(f"⚠️ {display_name_for_person(holder_name)}拒绝交出银饰物！", "action")

                self.create_clue(

                    clue_type="suspicious_behavior",

                    summary=f"{display_name_for_person(holder_name)}声称没有银饰物，但神色慌张，似乎在隐藏什么。",

                    source=self.detective_name,

                    related_person=holder_name,

                    location=holder.current_location or "unknown",

                )

                return {

                    "success": False,

                    "error": f"{display_name_for_person(holder_name)}拒绝交出银饰物",

                    "suspicious": True,

                    "clue": f"{display_name_for_person(holder_name)}的行为可疑。",

                }





            # Check if the holder is being blocked by a nearby werewolf

            nearby_wolves = [w for w in self.werewolf_names

                           if w in self.agents and self.agents[w].is_alive

                           and abs(self.agents[w].x - holder.x) + abs(self.agents[w].y - holder.y) <= 4]

            if nearby_wolves:

                wolf_name = nearby_wolves[0]

                self._log(f"⚠️ {display_name_for_person(wolf_name)}在附近干扰，{display_name_for_person(holder_name)}不敢交出银饰物", "action")

                return {

                    "success": False,

                    "error": f"{display_name_for_person(holder_name)}看起来想说什么，但似乎被附近的人震慑住了",

                    "suspicious": True,

                }





            # Success

            self._silver_jewelry_acquired = True

            self._silver_task_done_today = "silver_jewelry"

            self._log(f"💍 Crow 从{display_name_for_person(holder_name)}处获得了银饰物！", "action")

            return {

                "success": True,

                "message": f"从{display_name_for_person(holder_name)}处获得了银饰物",

                "silver_jewelry_acquired": True,

            }





    def craft_silver_bullet(self) -> dict:

        """Craft the silver bullet from the tool and jewelry. Only available Day 4+."""

        with self._lock:

            if self._silver_bullet_crafted:

                return {"success": True, "message": "银子弹已制作完成", "already_crafted": True}

            if not self._silver_bullet_acquired:

                return {"success": False, "error": "需要先获取银子弹工具"}

            if not self._silver_jewelry_acquired:

                return {"success": False, "error": "需要先获取银饰物"}

            if self.day < 4:

                return {"success": False, "error": f"第{self.day}天还不能制作银子弹，需要第4天及以后"}

            if self._silver_task_done_today:

                return {"success": False, "error": "今天已经完成过一项关键银器行动，明天再继续"}





            self._silver_bullet_crafted = True

            self._silver_task_done_today = "craft_silver_bullet"

            self._log("🔨 Crow 制作了真正的银子弹！", "action")

            return {

                "success": True,

                "message": "成功制作了银子弹！现在可以在夜晚对抗狼人了。",

                "silver_bullet_crafted": True,

            }





    def _silver_kill_target(self, target_name: str, actor_name: str, method: str) -> dict:

        target = self.agents.get(target_name)

        if not target or not target.is_alive:

            return {"success": False, "error": "目标不存在或已经失去行动能力"}

        if target_name in self._jailed:

            return {"success": False, "error": "目标已经被关押，不能再作为银器目标"}





        target.is_alive = False

        if target_name not in self.dead_list:

            self.dead_list.append(target_name)

        self.agent_paths.pop(target_name, None)

        target.runtime_state = "dead"

        target.current_action = "死亡"

        target.current_emoji = "☠️"





        body = BodyRecord(

            body_id=f"body_silver_{target_name.replace(' ', '_')}_{self.day}_{len(self.bodies) + 1}",

            victim_name=target_name,

            location=target.current_location or "unknown",

            x=target.x,

            y=target.y,

            created_day=self.day,

            discovered=False,

            is_werewolf_corpse=target_name in self.werewolf_names,

        )

        self.bodies.append(body)

        if method == "银质小刀":
            self._log("夜里发生了一次银器袭击，具体结果将在天亮后确认。", "kill")
        else:
            self._log(
                f"银器击杀：{display_name_for_person(actor_name)} 用{method}杀死了 {display_name_for_person(target_name)}。",
                "kill",
            )

        self._check_win_after_silver_action()

        return {

            "success": True,

            "target": target_name,

            "target_display": display_name_for_person(target_name),

            "target_was_werewolf": target_name in self.werewolf_names,

            "winner": self.winner,

            "game_over": self.game_over,

        }





    def _check_win_after_silver_action(self) -> None:

        alive_wolves = [

            n for n in self.werewolf_names

            if n in self.agents and self.agents[n].is_alive and n not in self._jailed

        ]

        alive_good = [

            n for n, a in self.agents.items()

            if a.is_alive and n not in self.werewolf_names and n not in self._jailed

        ]

        if not alive_wolves:

            self.game_over = True

            self.winner = "villagers"

            self.phase = GamePhase.GAME_OVER

            self._log("两名狼人都已被排除，小镇居民获胜。", "system")

        elif len(alive_wolves) >= len(alive_good):

            self.game_over = True

            self.winner = "werewolf"

            self.phase = GamePhase.GAME_OVER

            self._log("狼人已取得人数优势，狼人获胜。", "system")



    def _resolve_day4_after_vote(self) -> str:
        """Resolve Day4 game outcome after dusk vote.

        Day4 win rules:
        - Both wolves alive → werewolves win
        - No wolves alive → villagers win
        - One wolf alive + silver bullet available (crafted, not used) → pending_silver_shot
        - One wolf alive + no silver bullet → werewolves win

        Returns the new phase value.
        """
        alive_wolves = [
            n for n in self.werewolf_names
            if n in self.agents and self.agents[n].is_alive and n not in self._jailed
        ]
        if not alive_wolves:
            self.game_over = True
            self.winner = "villagers"
            self.phase = GamePhase.GAME_OVER
            self._log("🏆 第4天黄昏投票结束，所有狼人已被排除！小镇居民获胜！", "system")
            return "game_over"

        if len(alive_wolves) >= 2:
            self.game_over = True
            self.winner = "werewolf"
            self.phase = GamePhase.GAME_OVER
            self._log("🏆 第4天黄昏投票结束，双狼均存活，狼人获胜！", "system")
            return "game_over"

        # Exactly one wolf alive
        if len(alive_wolves) == 1:
            has_silver_bullet = (
                self._silver_bullet_acquired
                and self._silver_jewelry_acquired
                and self._silver_bullet_crafted
                and not self._silver_bullet_used
            )
            if has_silver_bullet:
                self.phase = GamePhase.PENDING_SILVER_SHOT
                self._pending_silver_wolf = alive_wolves[0]
                self._log(
                    "⚠️ 第4天黄昏投票结束，还剩一个狼人。"
                    "克罗持有银子弹，需要在仍然存活的村民中做出最终射击选择。",
                    "system",
                )
                return "pending_silver_shot"
            else:
                self.game_over = True
                self.winner = "werewolf"
                self.phase = GamePhase.GAME_OVER
                self._log("🏆 第4天黄昏投票结束，剩下一个狼人且无银子弹可用，狼人获胜！", "system")
                return "game_over"

        return "unknown"





    def shoot_silver_bullet(self, target_name: str) -> dict:
        """Crow fires the single crafted silver bullet at a suspected target.

        During PENDING_SILVER_SHOT phase (Day4 endgame), applies special win rules:
        - Hits werewolf → villagers win
        - Hits villager → werewolves win
        """
        with self._lock:
            if self._silver_bullet_used:
                return {"success": False, "error": "银子弹已经使用过"}
            if not self._silver_bullet_crafted:
                return {"success": False, "error": "还没有制作银子弹"}
            if target_name == self.detective_name:
                return {"success": False, "error": "不能射击警长自己"}
            target = self.agents.get(target_name)
            if not target or not target.is_alive:
                return {"success": False, "error": "目标不存在或已经失去行动能力"}
            if target_name in self._jailed:
                return {"success": False, "error": "目标已经被关押，不能射击"}

            # Check if this is a Day4 endgame silver shot
            if self.phase == GamePhase.PENDING_SILVER_SHOT:
                is_wolf = target_name in self.werewolf_names
                if is_wolf:
                    # Kill the wolf with silver bullet
                    result = self._silver_kill_target(target_name, self.detective_name, "银子弹")
                    if not result.get("success"):
                        return result
                    self._silver_bullet_used = True
                    self.game_over = True
                    self.winner = "villagers"
                    self.phase = GamePhase.GAME_OVER
                    self._log("🎯 银子弹命中狼人！小镇居民获胜！", "system")
                    result["day4_silver_shot"] = True
                    result["hit_werewolf"] = True
                    result["winner"] = "villagers"
                    return result
                else:
                    # Hit a villager → werewolves win
                    result = self._silver_kill_target(target_name, self.detective_name, "银子弹")
                    if not result.get("success"):
                        return result
                    self._silver_bullet_used = True
                    self.game_over = True
                    self.winner = "werewolf"
                    self.phase = GamePhase.GAME_OVER
                    self._log(f"💔 银子弹命中了无辜的 {display_name_for_person(target_name)}！狼人获胜！", "system")
                    result["day4_silver_shot"] = True
                    result["hit_werewolf"] = False
                    result["winner"] = "werewolf"
                    return result

            result = self._silver_kill_target(target_name, self.detective_name, "银子弹")
            if result.get("success"):
                self._silver_bullet_used = True
            return result





    def use_silver_knife(self, holder_name: str, target_name: str) -> dict:

        """Hidden good NPC uses the one-use silver knife at night."""

        with self._lock:

            if self._silver_knife_used:

                return {"success": False, "error": "银质小刀已经使用过"}

            if holder_name != self._silver_knife_holder:

                return {"success": False, "error": "该角色没有银质小刀"}

            holder = self.agents.get(holder_name)

            if not holder or not holder.is_alive or holder_name in self._jailed:

                return {"success": False, "error": "银质小刀持有者无法行动"}

            if self.phase != GamePhase.NIGHT:

                return {"success": False, "error": "银质小刀只能在夜晚使用"}

            if target_name == holder_name:

                return {"success": False, "error": "不能对自己使用银质小刀"}

            result = self._silver_kill_target(target_name, holder_name, "银质小刀")
            if result.get("success"):
                self._silver_knife_used = True
            return result





    def _maybe_use_silver_knife_at_night(self) -> None:
        """Attempt to use silver knife at night. Runs exactly once per night.

        If the holder was killed by the werewolf earlier this same night, the knife
        is scrapped (cannot be used) but the phase still displays for 60s.
        If the knife was already used in a previous night, it cannot be used again.
        """
        if self._silver_knife_night_checked:
            return
        self._silver_knife_night_checked = True

        if self._silver_knife_used:
            self._log("🗡️ 银质小刀阶段完成。", "system")
            return

        holder_name = self._silver_knife_holder
        holder = self.agents.get(holder_name) if holder_name else None

        # Check if holder was killed by wolf earlier tonight
        if self._silver_knife_scrapped_tonight:
            self._log("🗡️ 银质小刀阶段完成。", "system")
            return

        if not holder or not holder.is_alive or holder_name in self._jailed:
            self._log("🗡️ 银质小刀阶段完成。", "system")
            return

        candidates = [
            name for name, agent in self.agents.items()
            if name != holder_name
            and name != self.detective_name
            and agent.is_alive
            and name not in self._jailed
        ]
        if not candidates:
            self._log("🗡️ 银质小刀阶段完成。", "system")
            return

        clue_targets = [
            clue.related_person for clue in getattr(self, "clues", [])
            if clue.related_person in candidates
        ]
        if clue_targets:
            target_name = clue_targets[-1]
        else:
            target_name = self._rng.choice(candidates)

        result = self.use_silver_knife(holder_name, target_name)
        if result.get("success"):
            self._silver_knife_target_tonight = target_name
            if target_name in self.werewolf_names:
                self._silver_knife_killed_werewolf_tonight = True
                # Mark the body as a werewolf corpse
                for body in reversed(self.bodies):
                    if body.victim_name == target_name:
                        body.is_werewolf_corpse = True
                        break
            self._log("🗡️ 银质小刀阶段完成。", "system")
        else:
            self._log("🗡️ 银质小刀阶段完成。", "system")





    def enter_night(self):

        """玩家手动进入夜晚。支持从 DAY 或 DUSK_DISCUSSION 阶段触发。

        从 DAY 触发时自动跳过黄昏讨论；从 DUSK_DISCUSSION 触发时直接进入夜晚。"""

        with self._lock:

            if self.phase == GamePhase.DAY:

                self._log("⚠️ 跳过黄昏讨论，直接进入夜晚...", "system")

                self._transition_to_night()

            elif self.phase == GamePhase.DUSK_DISCUSSION:

                self._log("黄昏讨论和投票流程尚未完成，不能直接进入夜晚。", "system")

            # 其他阶段忽略





    def _transition_to_night(self):

        """phase=NIGHT → 所有人回家 → 狼人杀人"""

        self.phase = GamePhase.NIGHT

        self.night_start_time = time.time()

        self.day_time_expired = False

        self._chat_round_count = {}  # 新一天重置对话轮数

        self._silver_knife_night_checked = False
        self._silver_knife_phase_started_at = 0.0
        self._silver_knife_scrapped_tonight = False
        self._silver_knife_target_tonight = ""
        self._silver_knife_killed_werewolf_tonight = False

        self._night_progress = {"active": True, "stage": "werewolf", "complete": False}

        self._log("夜幕降临...")
        if (
            self.day == 3
            and self._silver_bullet_acquired
            and self._silver_jewelry_acquired
            and not self._silver_bullet_crafted
        ):
            self._silver_bullet_crafted = True
            self._log("🔨 你已经收集了银质项链和制造子弹的工具。今晚，克罗成功制造了一颗银质子弹。", "system")





        for name, agent in self.agents.items():

            if agent.is_alive:

                # Jailed residents stay in prison, not sent home

                if name in self._jailed:

                    agent.current_action = "被拘留中"

                    agent.current_emoji = "🔒"

                    continue

                cfg = AGENT_CONFIGS[name]

                target = self._nearest_walkable_tile(

                    (cfg["home"]["x"], cfg["home"]["y"]),

                    blocked=self._occupied_tiles({name}),

                )

                if target:

                    agent.target_x, agent.target_y = target

                agent.current_action = "sleeping"

                agent.current_emoji = "\U0001f634"

                agent.current_location = "home"





        self.agent_paths.clear()

        self.night_hunt = NightHuntState(

            started_at=self.night_start_time,

            deadline_at=self.night_start_time + self.night_duration,

        )

        self._night_last_replan_at = 0.0





    def _discover_latest_body(self) -> BodyRecord:

        new_bodies = []

        for candidate in self.bodies:

            if not candidate.discovered:

                candidate.discovered = True

                new_bodies.append(candidate)

        if new_bodies:
            body_parts = []
            for body in new_bodies:
                label = display_name_for_person(body.victim_name)
                if getattr(body, "is_werewolf_corpse", False):
                    label = f"{label}（狼人尸体）"
                body_parts.append(f"{label}，地点：{self._destination_label_zh(body.location)}")

            self._log(

                f"发现尸体：{'；'.join(body_parts)}。",

                "kill",

            )

            for body in new_bodies:
                body_text = f"发现尸体：{display_name_for_person(body.victim_name)}，地点：{self._destination_label_zh(body.location)}。"
                if getattr(body, "is_werewolf_corpse", False):
                    body_text += "尸体呈现明显狼人特征。"
                self._record_observation_event(
                    event_type="body_discovered",
                    subject=body.victim_name,
                    text=body_text,
                    x=body.x,
                    y=body.y,
                    public=True,
                    hidden=False,
                    source="public_event",
                )

        return new_bodies[-1] if new_bodies else None





    def _place_alive_agents_near_body(self, body: BodyRecord) -> None:

        if not body:

            return

        import math as _math





        alive = [agent for agent in self.agents.values()

                 if agent.is_alive and agent.name not in self._jailed]

        radius = 5

        occupied_tiles = set()

        for index, agent in enumerate(alive):

            angle = index * 2 * _math.pi / max(1, len(alive))

            target = (

                round(body.x + radius * _math.cos(angle)),

                round(body.y + radius * _math.sin(angle)),

            )

            spawn_tile = self._nearest_walkable_tile(

                target,

                radius=6,

                blocked=occupied_tiles,

            )

            if spawn_tile:

                agent.x, agent.y = spawn_tile

            occupied_tiles.add((agent.x, agent.y))

            agent.target_x = agent.x

            agent.target_y = agent.y

            agent.current_location = body.location

            agent.current_action = "discussing the discovered body"

            agent.current_emoji = "\U0001f4ac"

            agent.runtime_state = "idle"

        self.agent_paths.clear()





    def _transition_to_day(self):

        """day+=1 → 检查胜负 → compress_memory → 生成每日计划 → 更新日程"""

        hunt = getattr(self, "night_hunt", None)

        if hunt and not hunt.killed_name:

            self._advance_night_hunt(now=hunt.deadline_at)

        discovered_body = self._discover_latest_body()

        self.day += 1

        self.phase = GamePhase.DAY

        self.day_start_time = time.time()

        self.game_hour = 7

        self.day_time_expired = False

        self.dusk_start_time = None  # 清除上一轮的黄昏状态

        self._daily_interviewed = set()  # 新一天重置每日采访追踪

        self._daily_normal_chats = {}    # 新一天重置每日正常对话追踪

        self._reset_daily_deep_dive_quota()

        self._silver_task_done_today = None  # 新一天重置银器任务进度

        # Note: jailed people stay jailed; they don't auto-release daily





        # 检查胜负：两只狼人都死亡则好人获胜；存活狼人数量 >= 存活好人数量则狼人获胜

        # Jailed wolves count as removed; jailed villagers count as removed from active play

        alive_wolves = [n for n in self.werewolf_names if n in self.agents and self.agents[n].is_alive and n not in self._jailed]

        alive_good = [n for n, a in self.agents.items()

                      if a.is_alive and n not in self.werewolf_names and n not in self._jailed]

        if not alive_wolves:

            self.game_over = True

            self.winner = "villagers"

            self.phase = GamePhase.GAME_OVER

            self._log("所有狼人已被消灭！小镇居民获胜！")

            return

        if len(alive_wolves) >= len(alive_good):

            self.game_over = True

            self.winner = "werewolf"

            self.phase = GamePhase.GAME_OVER

            self._log("狼人数量已达半数以上，狼人胜利！")

            return





        if self.day > CONFIG["game"]["max_days"]:

            self.game_over = True

            self.winner = "werewolf"

            self.phase = GamePhase.GAME_OVER

            self._log(f"超过{CONFIG['game']['max_days']}天，狼人胜利！")

            return





        # 记忆压缩

        for name, agent in self.agents.items():

            if agent.is_alive:

                agent.compress_memory(self.day)





        # 生成每日计划（异步，不阻塞）

        # Day4 skips daily plans — no free activity
        if self.day < 4:
            self._generate_daily_plans()





        self._place_alive_agents_near_body(discovered_body)

        # Day4: morning discussion only, no free activity
        if self.day == 4:
            self._day4_no_free_activity = True
            self._log(f"第{self.day}天早晨 — 最后一天，早晨讨论后将直接进行黄昏投票，无自由活动时间。")

        self._init_gathering()

        self._log(f"第{self.day}天白天开始")





    # ==================== 狼人 ====================





    def _eligible_night_targets(self) -> list[str]:

        """Return non-wolf, non-detective, non-jailed alive residents as hunt candidates.

        Both werewolves are excluded from being targets of their own pack."""

        residents = [

            name for name, agent in self.agents.items()

            if agent.is_alive

            and name not in self.werewolf_names

            and name != self.detective_name

            and name not in self._jailed

        ]

        if residents:

            return residents

        detective = self.agents.get(self.detective_name)

        return [self.detective_name] if detective and detective.is_alive else []





    def _night_witnesses(self, victim_name: str, radius: int = 6) -> list[str]:

        victim = self.agents[victim_name]

        return sorted(

            name for name, agent in self.agents.items()

            if agent.is_alive

            and name not in self.werewolf_names

            and name not in self._jailed

            and name != victim_name

            and abs(agent.x - victim.x) + abs(agent.y - victim.y) <= radius

        )





    def _build_hunt_candidates(self) -> list[HuntCandidate]:

        if (

            self.werewolf_name not in self.agents

            or not self.agents[self.werewolf_name].is_alive

            or self.werewolf_name in self._jailed

        ):

            active_wolves = [

                name for name in self.werewolf_names

                if name in self.agents and self.agents[name].is_alive and name not in self._jailed

            ]

            if not active_wolves:

                return []

            self.werewolf_name = active_wolves[0]

        werewolf = self.agents[self.werewolf_name]

        candidates = []

        for name in self._eligible_night_targets():

            target = self.agents[name]

            path = self._find_navigation_path(

                (werewolf.x, werewolf.y),

                (target.x, target.y),

            )

            reachable = path is not None

            candidates.append(HuntCandidate(

                name=name,

                path_length=len(path) if reachable else 10 ** 6,

                witness_risk=len(self._night_witnesses(name)),

                reachable=reachable,

            ))

        return candidates





    def _select_night_target(self, forced: bool = False) -> str:

        candidates = self._build_hunt_candidates()

        fallback = choose_forced_target(candidates)

        if not fallback:

            return ""





        selected_name = fallback.name

        reachable_names = {candidate.name for candidate in candidates if candidate.reachable}

        if not forced:

            try:

                requested = self.agents[self.werewolf_name].werewolf_choose_target(

                    sorted(reachable_names), self.day

                )

                if requested in reachable_names:

                    selected_name = requested

            except Exception as exc:

                self._log(f"[night hunt target fallback] {exc}", "system")





        previous = self.night_hunt.target_name

        if previous and previous != selected_name:

            self.night_hunt.target_changes.append(selected_name)

        self.night_hunt.target_name = selected_name

        self.night_hunt.stage = "hunting"

        self._night_last_replan_at = time.time()

        self.agent_paths.pop(self.werewolf_name, None)

        return selected_name





    def _assign_clue_source(self, preferred_source: str = "") -> str:

        preferred = self.agents.get(preferred_source)

        if preferred and preferred.is_alive and preferred_source not in self.werewolf_names:

            return preferred_source

        residents = [

            name for name, agent in self.agents.items()

            if agent.is_alive and name not in self.werewolf_names and name != self.detective_name

        ]

        return residents[0] if residents else self.detective_name





    def _kill_night_target(self, target_name: str, forced: bool = False) -> None:

        if self.night_hunt.killed_name:

            return

        victim = self.agents[target_name]

        if not victim.is_alive:

            return





        witnesses = self._night_witnesses(target_name)

        victim.is_alive = False

        self.dead_list.append(target_name)

        self.night_hunt.killed_name = target_name

        self.night_hunt.stage = "withdrawing"

        self.night_hunt.witnessed_by.update(witnesses)

        self.night_hunt.forced_completion = forced





        location = self._reverse_lookup_location(victim.x, victim.y)

        if not location:

            location = victim.current_location or "unknown location"
        self._record_observation_event(
            event_type="night_kill",
            subject=target_name,
            text=f"{display_name_for_person(target_name)}在夜里遭到袭击。",
            x=victim.x,
            y=victim.y,
            public=False,
            hidden=True,
            witnesses=set(witnesses),
            source="night",
        )

        self.bodies.append(BodyRecord(

            body_id=f"body_{self.day}_{target_name.replace(' ', '_')}",

            victim_name=target_name,

            location=location,

            x=victim.x,

            y=victim.y,

            created_day=self.day,

            discovered=False,

        ))





        for trace in build_trace_clues(target_name, location, witnesses, forced):

            self.create_clue(

                clue_type=trace["clue_type"],

                summary=trace["summary"],

                source=self._assign_clue_source(trace.get("source", "")),

                related_person=trace.get("related_person", target_name),

                location=trace.get("location", location),

            )



        for name, agent in self.agents.items():

            if agent.is_alive and name not in self.werewolf_names:

                agent.add_memory(f"{target_name} was killed during the night.", self.day)

        for wolf_name in self.werewolf_names:

            if wolf_name in self.agents and self.agents[wolf_name].is_alive:

                self.agents[wolf_name].add_memory(

                    f"I killed {target_name} during the night.", self.day

                )





        wolf = self.agents[self.werewolf_name]

        home = AGENT_CONFIGS[self.werewolf_name]["home"]

        wolf.target_x = home["x"]

        wolf.target_y = home["y"]

        wolf.current_action = "withdrawing after the hunt"

        wolf.current_emoji = "\U0001f43e"

        self.agent_paths.pop(self.werewolf_name, None)

        self._log(f"Werewolf killed {target_name} near {location}.", "kill")





    def _advance_night_hunt(self, now: float = None) -> None:

        hunt = getattr(self, "night_hunt", None)

        if not hunt:

            return

        now = time.time() if now is None else now

        behavior = CONFIG.get("night_behavior", {})

        forced_seconds = behavior.get("forced_completion_seconds", 20)

        replan_seconds = behavior.get("replan_interval_seconds", 20)

        move_steps = behavior.get("night_move_steps_per_tick", 3)





        wolf = self.agents[self.werewolf_name]

        if hunt.killed_name:

            for _ in range(move_steps):

                self._move_agents()

            if wolf.x == wolf.target_x and wolf.y == wolf.target_y:

                hunt.withdrawal_complete = True

                hunt.stage = "complete"

            return





        forced = now >= hunt.deadline_at - forced_seconds

        hunt.forced_completion = forced

        target = self.agents.get(hunt.target_name)

        should_replan = (

            not target

            or not target.is_alive

            or not hunt.target_name

            or now - self._night_last_replan_at >= replan_seconds

        )

        if should_replan:

            self._select_night_target(forced=forced)

            target = self.agents.get(hunt.target_name)

        if not target:

            return





        if now >= hunt.deadline_at:

            approach = self._path_adjacent_to(

                (wolf.x, wolf.y),

                (target.x, target.y),

                blocked=self._occupied_tiles({self.werewolf_name, target.name}),

            )

            if approach:

                wolf.x, wolf.y = approach[0], approach[1]

            self._kill_night_target(target.name, forced=True)

            return





        wolf.target_x = target.x

        wolf.target_y = target.y

        wolf.current_action = f"hunting {target.name}"

        wolf.current_emoji = "\U0001f43a"

        if abs(wolf.x - target.x) + abs(wolf.y - target.y) <= 1:

            self._kill_night_target(target.name, forced=forced)

            return

        for _ in range(move_steps):

            self._move_agents()

        if abs(wolf.x - target.x) + abs(wolf.y - target.y) <= 1:

            self._kill_night_target(target.name, forced=forced)





    def _werewolf_kill_night(self):

        """狼人选目标(LLM)→杀→更新deep_dive_quota(3→2→1)→记录记忆→log type=kill"""

        werewolf = self.agents[self.werewolf_name]

        if not werewolf.is_alive:

            return





        targets = [n for n, a in self.agents.items()

                   if a.is_alive and n not in self.werewolf_names and n != self.detective_name]

        if not targets:

            return





        target_name = werewolf.werewolf_choose_target(targets, self.day)

        if target_name not in targets:

            target_name = random.choice(targets)





        self.agents[target_name].is_alive = False

        self.dead_list.append(target_name)

        self._log(f"狼人在夜间杀害了 {target_name}！", "kill")





        # 更新侦探深度挖掘配额

        for name, agent in self.agents.items():

            if agent.is_alive and name not in self.werewolf_names:

                agent.add_memory(f"听说{target_name}在夜间被杀害了！小镇上有狼人！", self.day)

        for wolf_name in self.werewolf_names:

            if wolf_name in self.agents and self.agents[wolf_name].is_alive:

                self.agents[wolf_name].add_memory(f"我在夜间杀死了{target_name}。", self.day)





    # ==================== 移动 ====================





    def _generate_daily_plans(self, wait=False):

        """为所有存活NPC生成每日计划

        wait=True: 同步生成（阻塞等待所有NPC计划完成）

        wait=False: 异步生成（后台线程）

        """

        threads = []

        for name, agent in self.agents.items():

            if not agent.is_alive:

                continue

            # Crow is controlled by the player; residents alone choose autonomous movement.

            if name == self.detective_name:

                continue

            # Jailed residents don't need daily plans

            if name in self._jailed:

                continue

            def _plan_thread(n, a):

                try:

                    a.generate_daily_plan(self.day)

                    plan_summary = "；".join(

                        [f"{p.get('hour', '?')}点{p.get('action', '')}"

                         for p in getattr(a, 'daily_plan', [])[:8]]

                    )

                    self._log(f"📋 {n} 计划：{plan_summary}", "action")

                except Exception as e:

                    print(f"[Plan Error] {n}: {e}", file=sys.stderr, flush=True)

            t = threading.Thread(target=_plan_thread, args=(name, agent), daemon=True)

            t.start()

            threads.append(t)





        if wait:

            for t in threads:

                t.join(timeout=30)  # 最多等30秒





    def _planning_order(self) -> list[str]:
        active_order = CONFIG.get("game", {}).get("active_agents", list(self.agents.keys()))
        return [
            name for name in active_order
            if name in self.agents and name != self.detective_name
            and self.agents[name].is_alive and name not in self._jailed
        ]

    def _current_planning_candidate(self) -> str | None:
        order = self._planning_order()
        if not order:
            return None
        if not hasattr(self, "_planning_turn_index"):
            self._planning_turn_index = 0
        if not hasattr(self, "_planning_cycle_started_at"):
            self._planning_cycle_started_at = time.time()
        self._planning_turn_index %= len(order)
        return order[self._planning_turn_index]

    def _advance_planning_turn(self, name: str | None = None) -> None:
        order = self._planning_order()
        if not order:
            self._planning_turn_index = 0
            self._planning_cycle_started_at = time.time()
            return
        self._planning_turn_index %= len(order)
        if name is not None and order[self._planning_turn_index] != name:
            return
        old_index = self._planning_turn_index
        self._planning_turn_index = (self._planning_turn_index + 1) % len(order)
        if self._planning_turn_index <= old_index:
            now = time.time()
            self._last_planning_cycle_seconds = max(0.0, now - getattr(self, "_planning_cycle_started_at", now))
            self._planning_cycle_started_at = now

    def _skip_planning_turn_if_current(self, name: str) -> None:
        if getattr(self, "_active_planning_agent", None):
            return
        if self._current_planning_candidate() == name:
            self._advance_planning_turn(name)

    def _game_minutes_to_real_seconds(self, minutes: int | float) -> float:
        day_duration = float(getattr(self, "day_duration", CONFIG.get("game", {}).get("day_duration_seconds", 600)) or 600)
        return max(0.0, float(minutes) * day_duration / 1440.0)

    def _action_duration_minutes(self, pending_action: dict | None) -> int:
        pending_action = pending_action or {}
        try:
            planned = int(float(pending_action.get("duration_minutes", 30)))
        except (TypeError, ValueError):
            planned = 30
        planned = max(5, min(30, planned))
        cycle_seconds = float(getattr(self, "_last_planning_cycle_seconds", 0.0) or 0.0)
        if cycle_seconds <= 0:
            planned = max(planned, 30)
        else:
            day_duration = float(getattr(self, "day_duration", CONFIG.get("game", {}).get("day_duration_seconds", 600)) or 600)
            planned = max(planned, int(math.ceil(cycle_seconds * 1440.0 / day_duration)))
        return max(5, min(30, planned))

    def _action_duration_seconds(self, pending_action: dict | None) -> float:
        configured_min = float(CONFIG.get("agent", {}).get("min_act_seconds", 5) or 0)
        configured_max = float(CONFIG.get("agent", {}).get("max_act_seconds", 15) or 0)
        if configured_min <= 0 and configured_max <= 0:
            return 0.0
        return max(6.0, self._game_minutes_to_real_seconds(self._action_duration_minutes(pending_action)))

    def _action_start_bubble_seconds(self) -> float:
        return max(0.0, float(CONFIG.get("game", {}).get("bubble_lifetime_seconds", 6) or 0))

    def _mark_action_started(self, agent, now: float | None = None) -> None:
        started_at = float(now if now is not None else time.time())
        agent._action_started_at = started_at
        agent._action_status_visible_at = 0
        visible_until = started_at + self._action_start_bubble_seconds()
        agent._action_start_visible_until = visible_until
        agent._action_move_ready_at = visible_until

    def _bump_agent_action_generation(self, agent) -> int:
        generation = int(getattr(agent, "_action_generation_id", 0) or 0) + 1
        agent._action_generation_id = generation
        return generation

    def _agent_action_generation(self, agent) -> int:
        return int(getattr(agent, "_action_generation_id", 0) or 0)

    def _mark_action_arrived(self, agent, now: float | None = None) -> float:
        arrived_at = float(now if now is not None else time.time())
        agent._arrived_at_time = arrived_at
        started_at = float(getattr(agent, "_action_started_at", 0) or arrived_at)
        visible_at = max(arrived_at, started_at + self._action_start_bubble_seconds())
        agent._action_status_visible_at = visible_at
        return visible_at

    def _neighbor_action_path(self, name: str, agent) -> tuple[int, int, list[tuple[int, int]]] | None:
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            tx, ty = agent.x + dx, agent.y + dy
            if (
                ty < 0
                or ty >= len(self.collision_maze)
                or tx < 0
                or tx >= len(self.collision_maze[ty])
                or self.collision_maze[ty][tx] != 0
                or not self._is_tile_free_of_blocking_objects(tx, ty)
            ):
                continue
            path = self._find_navigation_path((agent.x, agent.y), (tx, ty), blocked=self._occupied_tiles({name}))
            if path is not None:
                return tx, ty, path or [(tx, ty)]
        return None

    def _random_walkable_around_target(
        self,
        name: str,
        agent,
        center_x: int,
        center_y: int,
        blocked_names: set[str] | None = None,
    ) -> tuple[int, int, list[tuple[int, int]]] | None:
        offsets = [
            (-1, -1), (0, -1), (1, -1),
            (-1, 0), (1, 0),
            (-1, 1), (0, 1), (1, 1),
        ]
        self._rng.shuffle(offsets)
        blocked = self._occupied_tiles(set(blocked_names or {name}))
        for dx, dy in offsets:
            tx, ty = center_x + dx, center_y + dy
            if (
                ty < 0
                or ty >= len(self.collision_maze)
                or tx < 0
                or tx >= len(self.collision_maze[ty])
                or self.collision_maze[ty][tx] != 0
                or not self._is_tile_free_of_blocking_objects(tx, ty)
                or (tx, ty) in blocked
            ):
                continue
            path = self._find_navigation_path((agent.x, agent.y), (tx, ty), blocked=blocked)
            if path is not None:
                return tx, ty, path or [(tx, ty)]
        return None

    def _default_continuing_action(self, name: str, location: str = "") -> str:
        defaults = {
            "Arthur Burton": "整理工具架",
            "Isabella Rodriguez": "整理咖啡杯盘",
            "Klaus Mueller": "整理课堂资料",
            "Maria Lopez": "清点药房货架",
            "Sam Moore": "擦拭吧台",
            "Jane Moreno": "修剪花枝",
            "Mei Lin": "整理书架",
        }
        return defaults.get(name, "整理手头事务")

    def _action_status_text(self, agent, pending_action: dict | None = None) -> str:
        pending_action = pending_action or getattr(agent, "_pending_action", {}) or {}
        text = str(pending_action.get("action_status") or "").strip()
        if not text:
            text = str(pending_action.get("action") or getattr(agent, "current_action", "") or "").strip()
        text = re.sub(r"^.*?[说講讲][:：]\s*", "", text)
        text = re.sub(r"^(正在|正|在)\s*", "", text)
        text = re.sub(r"^(要回|回到|返回|前往|去|留在)\S+\s+", "", text)
        for marker in ("，也", "，还", "，并", "，再", "，检查", "，等待", "，留意", "。", "；", ";"):
            if marker in text:
                text = text.split(marker, 1)[0].strip()
        for prefix in ("前往", "去", "留在"):
            if text.startswith(prefix) and "，" in text:
                text = text.split("，", 1)[1].strip()
        text = text or self._default_continuing_action(getattr(agent, "name", ""))
        return localize_visible_character_names(text[:10].rstrip("。！？.!") + "...")

    def _show_action_status_bubble(self, name: str, agent, pending_action: dict | None = None) -> None:
        pending_action = pending_action or getattr(agent, "_pending_action", None)
        if not pending_action or str(pending_action.get("action_type", "")).lower() in {"talk", "socialize"}:
            return
        self.chat_bubbles[name] = {"text": self._action_status_text(agent, pending_action), "target": "", "time": time.time(), "kind": "action_status"}

    def _redirect_to_visible_continue_current(self, name: str, agent, reason: str = "") -> None:
        loc_now = agent.current_location or self._reverse_lookup_location(agent.x, agent.y) or "某处"
        action = self._default_continuing_action(name, loc_now)
        self.agent_paths.pop(name, None)
        agent.target_x = agent.x
        agent.target_y = agent.y
        agent.current_location = loc_now
        agent.current_action = action
        agent.current_action_type = "continue_current"
        agent.current_emoji = self._get_emoji(action)
        agent._pending_action = {
            "action_type": "continue_current",
            "target_location": loc_now,
            "target_object": "",
            "target_person": "",
            "action": action,
            "action_status": action,
            "thought": reason or "目标暂时不适合交谈",
            "expected_result": "完成当前事务",
        }
        agent.runtime_state = "starting_action"
        self._bump_agent_action_generation(agent)
        self._mark_action_started(agent, time.time())
        self._clear_action_status_bubble(name)

    def _clear_action_status_bubble(self, name: str) -> None:
        bubble = self.chat_bubbles.get(name)
        if isinstance(bubble, dict) and bubble.get("kind") == "action_status":
            self.chat_bubbles.pop(name, None)

    def _arrive_at_pending_action(self, name: str, agent) -> None:
        pending_action = getattr(agent, "_pending_action", None)
        if not pending_action:
            agent.runtime_state = "idle"
            return
        action_type = str(pending_action.get("action_type", "")).lower()
        target_person = pending_action.get("target_person", "")
        target_text = " ".join(
            str(pending_action.get(key, "") or "")
            for key in ("action", "action_status", "expected_result")
        )
        is_chat_like = action_type in {"talk", "socialize"} or (
            target_person and any(word in target_text for word in ("打招呼", "询问", "聊天", "交谈", "说话"))
        )
        if is_chat_like and target_person:
            target = self.agents.get(target_person)
            threshold = 1 if target_person == self.detective_name else 2
            if target and target.is_alive and self._agent_distance(agent, target) <= threshold:
                if target_person != self.detective_name and getattr(target, "in_conversation_with", None) is not None:
                    self._redirect_to_visible_continue_current(name, agent, "对方正在交谈，先避开等待")
                    return
                if target_person == self.detective_name:
                    if not self._trigger_npc_to_detective_chat(name, pending_action.get("action", "")):
                        self._redirect_to_visible_continue_current(name, agent, "克罗正在交谈，暂不插话")
                        return
                else:
                    self._trigger_npc_chat(name, target_person)
                agent._pending_action = None
                return
            if target and target.is_alive:
                path_res = self._path_adjacent_to((agent.x, agent.y), (target.x, target.y), blocked=self._occupied_tiles({name, target_person}), preferred_distance=threshold)
                if path_res:
                    tx, ty, path = path_res
                    agent.target_x, agent.target_y = tx, ty
                    self.agent_paths[name] = path
                    agent.runtime_state = "moving"
                    return
        agent.runtime_state = "acting"
        self._mark_action_arrived(agent)
        self._show_action_status_bubble(name, agent, pending_action)

    def _start_pending_action_execution_if_ready(self, name: str, agent, now: float | None = None) -> bool:
        if getattr(agent, "runtime_state", "") != "starting_action":
            return False
        pending_action = getattr(agent, "_pending_action", None)
        if not pending_action:
            agent.runtime_state = "idle"
            return True
        now = float(now if now is not None else time.time())
        if now < float(getattr(agent, "_action_start_visible_until", 0) or 0):
            return True
        pending_type = str(pending_action.get("action_type", "")).lower()
        target_person = pending_action.get("target_person", "")
        if pending_type in {"talk", "socialize"} and target_person:
            target = self.agents.get(target_person)
            threshold = 1 if target_person == self.detective_name else 2
            if target and target.is_alive and self._agent_distance(agent, target) <= threshold:
                self.agent_paths.pop(name, None)
                agent.target_x, agent.target_y = agent.x, agent.y
                self._arrive_at_pending_action(name, agent)
                return True
        if self.agent_paths.get(name) or agent.x != agent.target_x or agent.y != agent.target_y:
            agent.runtime_state = "moving"
            return True
        self._arrive_at_pending_action(name, agent)
        return True

    def _update_agent_schedules(self):

        """遍历存活NPC：先看每日计划，计划没有新目标再等LLM决策

        行为闭环：一次思考 → 一个目标 → 一条路径 → 走到终点 → 再思考

        runtime_state: idle / thinking / moving / acting

        """

        if getattr(self, '_gathering_active', False):

            return





        hour = int(self.game_hour)

        now = time.time()





        for name, agent in self.agents.items():

            if not agent.is_alive:

                continue
            if getattr(agent, "runtime_state", "") == "idle" and str(getattr(agent, "current_thought", "")).strip() == "我想适应小镇生活":
                agent.current_thought = ""
                agent.current_thought_time = 0

            # Crow 由玩家操控移动和交谈，不参与居民自主行动决策。

            if name == self.detective_name:
                continue
            if self._detective_chat_target_reserved(name):
                agent.runtime_state = "acting"
                self._skip_planning_turn_if_current(name)
                continue
            pending_action_for_crow = getattr(agent, "_pending_action", None) or {}
            if (
                getattr(self, "_detective_chat_active_target", None)
                and pending_action_for_crow.get("target_person") == self.detective_name
            ):
                self._redirect_to_visible_continue_current(name, agent, "克罗正在交谈，暂不插话")
                self._skip_planning_turn_if_current(name)
                continue
            # Jailed residents cannot move or act on their own
            if name in self._jailed:
                continue

            if float(getattr(agent, "_report_busy_until", 0) or 0) > now:
                self._skip_planning_turn_if_current(name)
                continue




            # 初始化 runtime_state

            if not hasattr(agent, 'runtime_state'):

                agent.runtime_state = "idle"



            stale_timeout = int(CONFIG.get("llm", {}).get("request_timeout_seconds", 60)) + 10

            if getattr(agent, '_is_thinking', False):

                thinking_started = getattr(agent, '_thinking_started_at', now)

                if now - thinking_started > stale_timeout:

                    agent._is_thinking = False

                    agent.runtime_state = "idle"

                    agent._next_llm_retry_time = now + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                    self._log(f"[LLM状态] {name}: 思考超时释放，稍后重试", "think")

            partner_name = getattr(agent, 'in_conversation_with', None)

            if partner_name is not None:

                conversation_started = getattr(agent, '_conversation_started_at', now)

                if partner_name != self.detective_name and self._clear_conversation_if_too_far(name, partner_name):

                    agent.runtime_state = "idle"

                    self._log(f"[NPC聊天] {name} 与 {partner_name} 距离过远，对话终止", "system")

                elif now - conversation_started > stale_timeout:

                    self._clear_conversation_pair(name, partner_name)

                    agent.runtime_state = "idle"

                    self._log(f"[NPC聊天] {name} 与 {partner_name} 对话超时释放", "system")

                elif partner_name == self.detective_name:

                    detective = self.agents.get(self.detective_name)

                    if getattr(self, "_detective_chat_active_target", None) == name:
                        self._skip_planning_turn_if_current(name)
                        continue
                    if detective and getattr(detective, "in_conversation_with", None) != name:

                        agent.in_conversation_with = None

                        agent._conversation_started_at = 0

                        agent.runtime_state = "idle"

                        self._log(f"[NPC聊天] {name} 与警长的对话锁已孤立，自动释放", "system")





            if self._start_pending_action_execution_if_ready(name, agent, now):
                self._skip_planning_turn_if_current(name)
                continue

            # 正在移动 → 跳过，不思考不决策

            path = self.agent_paths.get(name)

            is_moving = bool(path) or (agent.x != agent.target_x or agent.y != agent.target_y)

            if is_moving:

                agent.runtime_state = "moving"
                self._skip_planning_turn_if_current(name)

                continue





            # 正在思考（LLM线程还没返回）→ 跳过

            if getattr(agent, '_is_thinking', False):

                continue





            # 正在对话中 → 跳过自主决策和行动更新

            if getattr(agent, 'in_conversation_with', None) is not None:
                self._skip_planning_turn_if_current(name)

                continue





            # 有 pending action 但不在执行状态：先走 starting_action / arrival 流程
            pending_action = getattr(agent, '_pending_action', None)
            if pending_action:
                state = getattr(agent, 'runtime_state', '')
                if state in ("planning", "moving", "starting_action"):
                    self._skip_planning_turn_if_current(name)
                    continue
                if (
                    str(pending_action.get("action_type", "")).lower() in {"talk", "socialize"}
                    and pending_action.get("target_person")
                    and state != "acting"
                ):
                    self._arrive_at_pending_action(name, agent)
                    self._skip_planning_turn_if_current(name)
                    continue
                if state != "acting":
                    action_type = pending_action.get("action_type", "continue_current")
                    if action_type == "stay":
                        action_type = "continue_current"
                    action_text = pending_action.get("action") or "继续当前事务"
                    agent.current_action = action_text
                    agent.current_action_type = action_type
                    agent.current_emoji = self._get_emoji(action_text)
                    self._mark_action_started(agent, now)
                    agent.runtime_state = "starting_action"
                    pending_action["duration_minutes"] = self._action_duration_minutes(pending_action)
                    pending_action["duration_seconds"] = self._action_duration_seconds(pending_action)
                    agent.current_thought = ""
                    agent.current_thought_time = 0
                    self._log(
                        f"[开始行动] {display_name_for_person(name)}: 执行既定行动，"
                        f"{localize_visible_character_names(action_text)}"
                        f"（{ACTION_TYPE_LABELS_ZH.get(action_type, action_type)}）",
                        "action",
                    )
                    self._record_observation_event(
                        "action_start",
                        name,
                        f"{display_name_for_person(name)}开始行动：{action_text}",
                        x=agent.x,
                        y=agent.y,
                        object=str(pending_action.get("target_object", "") or ""),
                        source="action",
                    )
                    self._skip_planning_turn_if_current(name)
                    continue

            # acting 状态：使用 duration helpers 计时

            if getattr(agent, 'runtime_state', '') == "acting":

                arrived_at = getattr(agent, '_arrived_at_time', 0)

                pending_action = getattr(agent, '_pending_action', None)

                if pending_action and "duration_seconds" in pending_action:
                    try:
                        act_duration = max(6.0, float(pending_action.get("duration_seconds") or 0))
                    except (TypeError, ValueError):
                        act_duration = float(self._action_duration_seconds(pending_action))
                else:
                    act_duration = float(self._action_duration_seconds(pending_action))

                visible_at = float(getattr(agent, "_action_status_visible_at", 0) or 0)
                if visible_at <= 0:
                    started_at = float(getattr(agent, "_action_started_at", 0) or arrived_at)
                    visible_at = max(float(arrived_at or now), started_at + self._action_start_bubble_seconds())
                    agent._action_status_visible_at = visible_at

                if now - visible_at < act_duration:
                    self._skip_planning_turn_if_current(name)

                    continue  # 还在做事

                else:

                    self._complete_agent_action(name, agent)

                    agent.runtime_state = "idle"

                    continue



            # == 第一步：每日计划仅作参考，不强制移动 ==

            # daily_plan 不再直接设置 target_x/target_y

            # NPC 的移动完全由 LLM 决策驱动，daily_plan 只在 prompt 中作为参考



            # == 第二步：LLM 决策（按配置间隔） ==

            llm_interval = CONFIG.get("llm", {}).get("action_decision_interval_seconds", 20)

            if False:

                max_act = CONFIG.get("agent", {}).get("max_act_seconds", 15)

                act_duration = min_act + (hash(name) % (max_act - min_act + 1))

                if now - arrived_at < act_duration:

                    continue  # 还在做事

                else:

                    self._complete_agent_action(name, agent)

                    agent.runtime_state = "idle"

                    continue





            # == 第一步：每日计划仅作参考，不强制移动 ==

            # daily_plan 不再直接设置 target_x/target_y

            # NPC 的移动完全由 LLM 决策驱动，daily_plan 只在 prompt 中作为参考





            # == 第二步：LLM 决策（按配置间隔） ==

            llm_interval = CONFIG.get("llm", {}).get("action_decision_interval_seconds", 20)

            last_decision = getattr(agent, '_last_llm_decision_time', 0)

            time_since = now - last_decision





            # 如果之前失败设了重试时间，必须等到那个时间

            next_retry = getattr(agent, '_next_llm_retry_time', 0)

            if now < next_retry:

                continue





            if time_since < llm_interval:

                continue

            agent._last_llm_decision_time = now





            # 构建附近人物信息

            nearby_lines = []

            for other_name, other in self.agents.items():

                if other_name == name or not other.is_alive:

                    continue

                dist = abs(agent.x - other.x) + abs(agent.y - other.y)

                if dist <= 20:

                    nearby_lines.append(

                        f"- {display_name_for_person(other_name)} 在{other.current_location or '某处'}"

                        f"（正在{localize_visible_character_names(other.current_action or '活动')}）"

                    )

            nearby_info = "\n".join(nearby_lines) if nearby_lines else "附近没有人"





            # 场景物件信息

            scene = get_tile_scene(agent.x, agent.y,

                                   self.sector_maze, self.arena_maze, self.go_maze,

                                   self.sector_dict, self.arena_dict, self.go_dict)

            scene_parts = []

            if scene["arena"]:

                arena_name = scene["arena"].split(",")[-1].strip()

                if arena_name != scene["sector"]:

                    scene_parts.append(f"具体位置：{arena_name}")

            nearby_objs = get_nearby_objects(agent.x, agent.y, 3,

                                             self.sector_maze, self.arena_maze, self.go_maze,

                                             self.sector_dict, self.arena_dict, self.go_dict)

            if nearby_objs:

                scene_parts.append(f"你看到：{'、'.join(nearby_objs)}")

            scene_info = "。".join(scene_parts)
            obs_packet = self._build_observation_packet(name, agent)
            nearby_info, scene_info = self._format_observation_for_decision(obs_packet)





            # 标记正在思考

            agent._is_thinking = True

            agent._thinking_started_at = now

            agent.runtime_state = "thinking"
            decision_generation = self._bump_agent_action_generation(agent)





            # 异步调用 LLM

            def _llm_thread(n, a, nearby, si, packet, generation):

                try:
                    def _decision_cancelled() -> bool:
                        return (
                            self._agent_action_generation(a) != generation
                            or getattr(a, "in_conversation_with", None) is not None
                            or getattr(self, "_detective_chat_active_target", None) == n
                            or not getattr(a, "is_alive", True)
                            or n in getattr(self, "_jailed", set())
                        )

                    model_name = getattr(a, 'model', '?')

                    actor_label = display_name_for_person(n)

                    self._log(f"[LLM请求] {actor_label} -> {model_name}：发送行动决策请求", "think")

                    decision = a.decide_next_action(self.game_hour, str(self.day), list(self.dead_list), nearby, si)
                    if _decision_cancelled():
                        return





                    # 保存到 agent 供 status 查询

                    a._last_raw_response = decision.get("raw_response", "")

                    a._last_decision = decision





                    # 记录模型原始输出

                    raw = decision.get("raw_response", "")

                    if raw:

                        self._log(f"[模型原始输出] {n}: {raw}", "llm_raw")

                    else:

                        self._log(f"[模型原始输出] {n}: <空输出>", "llm_raw")





                    # 检查 ok 字段

                    def _fallback_continue_current(reason: str):
                        if _decision_cancelled():
                            return
                        loc_now = a.current_location or self._reverse_lookup_location(a.x, a.y) or "某处"
                        a.current_location = loc_now
                        a.current_action = self._default_continuing_action(n, loc_now)
                        a.current_action_type = "continue_current"
                        a.current_emoji = self._get_emoji(a.current_action)
                        a._pending_action = {
                            "action_type": "continue_current",
                            "target_location": loc_now,
                            "target_object": "",
                            "target_person": "",
                            "action": a.current_action,
                            "action_status": a.current_action,

                            "thought": reason,

                            "expected_result": "完成当前事务",

                        }

                        a.runtime_state = "starting_action"

                        self._mark_action_started(a, time.time())
                        self._log(
                            f"[行动解析] {actor_label}: 地点={self._destination_label_zh(loc_now)}；"
                            f"行动={a.current_action}；类型=continue_current；原因={reason}",
                            "think",
                        )

                    if not decision.get("ok", False):
                        err = decision.get("error", "unknown")
                        self._log(f"[LLM状态] {actor_label}: 决策失败（{err}），转为continue_current，稍后重试", "think")
                        _fallback_continue_current(f"模型暂时没有给出可执行计划：{err}")
                        a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)
                        return




                    # 提取决策字段

                    def _text(value):

                        return "" if value is None else str(value).strip()





                    loc = _text(decision.get("target_location"))

                    target_obj = _text(decision.get("target_object"))

                    model_target_obj_empty = not target_obj

                    target_person = resolve_character_name(_text(decision.get("target_person")))

                    action = _text(decision.get("action"))

                    action_type = _text(decision.get("action_type"))

                    thought = _text(decision.get("thought"))

                    expected_result = _text(decision.get("expected_result"))

                    action_status = self._ground_action_status(n, a, _text(decision.get("action_status")), packet)



                    if not target_person and self._should_infer_detective_target(
                        action_type, loc, target_obj, action, thought, expected_result
                    ):
                        target_person = self.detective_name
                        if action_type not in {"talk", "socialize"}:
                            action_type = "talk"
                    if target_person and str(action_type or "").lower() not in {"talk", "socialize"}:
                        chat_text = " ".join([action, action_status, thought, expected_result])
                        if any(word in chat_text for word in ("打招呼", "询问", "聊天", "交谈", "说话", "说明", "汇报")):
                            action_type = "talk"


                    if target_person:

                        target_agent = self.agents.get(target_person)

                        if target_agent and not loc:
                            loc = target_agent.current_location or self._reverse_lookup_location(target_agent.x, target_agent.y) or "Johnson Park"




                    # 不需移动（原地执行）的动作类型

                    if action_type == "stay":
                        action_type = "continue_current"

                    _IN_PLACE_ACTIONS = {"continue_current", "stay", "observe", "work", "rest", "hide", "socialize", "talk", "inspect", "investigate"}




                    # 空地点处理：原地动作使用当前语义位置；移动类动作必须提供地点

                    if not loc:

                        if action_type in _IN_PLACE_ACTIONS:

                            loc = a.current_location or self._reverse_lookup_location(a.x, a.y) or "某处"

                        else:

                            self._log(f"[LLM状态] {actor_label}: 模型未返回有效地点（类型={ACTION_TYPE_LABELS_ZH.get(action_type, action_type)}），转为continue_current，稍后重试", "think")
                            _fallback_continue_current("模型没有说明要去哪里")
                            a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                            return





                    # 行动解析日志

                    loc_log = self._destination_label_zh(loc) if loc else ""

                    obj_part = f"；物件={localize_visible_character_names(target_obj)}" if target_obj else ""

                    pers_part = f"；人物={display_name_for_person(target_person)}" if target_person else ""

                    type_part = f"；类型={ACTION_TYPE_LABELS_ZH.get(action_type, action_type)}" if action_type else ""

                    expect_part = f"；预期={localize_visible_character_names(expected_result)}" if expected_result else ""

                    self._log(

                        f"[行动解析] {actor_label}: 地点={loc_log}{obj_part}{pers_part}；"

                        f"行动={localize_visible_character_names(action)}{type_part}{expect_part}",

                        "think",

                    )

                    if thought:

                        self._log(f"[行动理由] {actor_label}: {localize_visible_character_names(thought)}", "think")





                    # 模糊匹配地点名

                    loc_lower = loc.lower().strip(".,!?。，！？")

                    matched_loc = None

                    if loc_lower in ("home", "家"):

                        matched_loc = "home"

                    else:

                        strict_mapping = {

                            "blacksmith": "Harvey Oak Supply Store",

                            "workshop": "Harvey Oak Supply Store",

                            "forge": "Harvey Oak Supply Store",

                            "supply": "Harvey Oak Supply Store",

                            "college": "Oak Hill College",

                            "school": "Oak Hill College",

                            "cafe": "Hobbs Cafe",

                            "coffee": "Hobbs Cafe",

                            "pub": "The Rose and Crown Pub",

                            "bar": "The Rose and Crown Pub",

                            "tavern": "The Rose and Crown Pub",

                            "market": "The Willows Market and Pharmacy",

                            "grocery": "The Willows Market and Pharmacy",

                            "store": "The Willows Market and Pharmacy",

                            "park": "Johnson Park",

                        }

                        # 1. 优先使用严格关键词映射

                        for kw, target_lm in strict_mapping.items():

                            if kw in loc_lower:

                                matched_loc = target_lm

                                break

                        # 2. 其次尝试精确子串匹配

                        if not matched_loc:

                            for lm_name in LANDMARKS:

                                if lm_name.lower() in loc_lower or loc_lower in lm_name.lower():

                                    matched_loc = lm_name

                                    break





                    # 3. 兜底高容错：如果 matched_loc 不在 LANDMARKS 中且不是 home，尝试进行包含比对映射为标准名

                    if matched_loc and matched_loc != "home" and matched_loc not in LANDMARKS:

                        for lm_name in LANDMARKS:

                            if matched_loc.lower() in lm_name.lower() or lm_name.lower() in matched_loc.lower():

                                matched_loc = lm_name

                                break





                    # 地点匹配失败的处理：原地动作使用当前语义位置；移动类动作回退到角色默认目的地

                    if not matched_loc:

                        if action_type in _IN_PLACE_ACTIONS:

                            matched_loc = a.current_location or self._reverse_lookup_location(a.x, a.y) or "某处"

                        else:

                            # Fallback to character-specific default destination and object

                            matched_loc = DEFAULT_DESTINATIONS.get(n, "home")

                            target_obj = DEFAULT_DEPARTURE_OBJECTS.get(n, "")

                            action_type = "work"

                            action = f"前往{self._destination_label_zh(matched_loc)}处理日常事务"

                            expected_result = expected_result or "保持正常生活节奏"

                            thought = f"{thought or '地点解析失败'}；回到{self._destination_label_zh(matched_loc)}做日常事务。"

                            self._log(

                                f"[行动修正] {actor_label}: 未知地点「{loc}」→ 回退到{self._destination_label_zh(matched_loc)}（角色默认）",

                                "action",

                            )





                    if not target_person:

                        target_obj = self._resolve_concrete_target_object(

                            a,

                            matched_loc,

                            target_obj,

                            action_type,

                            action,

                        )

                    if (

                        str(action_type).lower() in {"continue_current", "stay", "observe"}
                        and not target_person

                        and model_target_obj_empty

                        and self._recent_passive_action_count(a) >= 1

                    ):

                        daily_dest = DEFAULT_DESTINATIONS.get(n, matched_loc)

                        daily_obj = DEFAULT_DEPARTURE_OBJECTS.get(n, "")

                        matched_loc = daily_dest

                        target_obj = self._resolve_concrete_target_object(

                            a,

                            matched_loc,

                            daily_obj,

                            "work",

                            action,

                        ) or daily_obj

                        action_type = "work"

                        action = f"回到{self._destination_label_zh(matched_loc)}处理日常事务"

                        expected_result = "保持正常生活节奏"

                        thought = f"{thought or '不能一直站着观察'}；继续正常生活，避免显得反常。"

                        self._log(

                            f"[行动修正] {actor_label}: 连续原地观察，改为前往{self._destination_label_zh(matched_loc)}处理日常事务",

                            "action",

                        )

                    if action_type in {"move_to", "inspect", "investigate", "work"} and not target_person and not target_obj:

                        # Fallback to character-specific default object for the matched location

                        character_default_obj = DEFAULT_DEPARTURE_OBJECTS.get(n, "")

                        if character_default_obj:

                            target_obj = self._resolve_concrete_target_object(

                                a, matched_loc, character_default_obj, action_type, action

                            ) or character_default_obj

                            if not target_obj:

                                target_obj = LANDMARK_DEFAULT_OBJECTS.get(matched_loc, "")

                        if not target_obj:

                            self._log(

                                f"[LLM状态] {actor_label}: 行动缺少可验证的真实物件（地点={self._destination_label_zh(matched_loc)}），转为continue_current，稍后重试",
                                "think",

                            )

                            _fallback_continue_current("模型没有给出具体可交互物件且无默认物件可用")
                            a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                            return

                        self._log(

                            f"[行动修正] {actor_label}: 使用角色默认物件 {localize_visible_character_names(target_obj)}",

                            "action",

                        )



                    if target_person:

                        available, busy_reason = self._target_available_for_approach(n, target_person)

                        if not available:

                            self._log(

                                f"[LLM状态] {actor_label}: 暂不接近{display_name_for_person(target_person)}，{busy_reason}",

                                "think",

                            )

                            _fallback_continue_current(f"目标暂时不适合交谈：{busy_reason}")
                            a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                            return





                    # 保存 pending action

                    a._pending_action = {

                        "action_type": action_type or "continue_current",
                        "target_location": matched_loc,

                        "target_object": target_obj,

                        "target_person": target_person,

                        "action": action,

                        "action_status": action_status,

                        "thought": thought,

                        "expected_result": expected_result,

                        "observation_before": packet,

                    }





                    # 更新 agent 状态字段

                    a.current_action = action or "doing something"

                    a.current_action_type = action_type or "continue_current"
                    a.current_emoji = self._get_emoji(a.current_action)
                    self._record_observation_event(
                        event_type="action_start",
                        subject=n,
                        text=f"{display_name_for_person(n)}开始：{localize_visible_character_names(action_status or action)}",
                        x=a.x,
                        y=a.y,
                        public=False,
                    )

                    a.runtime_state = "planning"

                    plan_delay = float(CONFIG.get("agent", {}).get("planning_display_seconds", 3.5))

                    a._action_plan_ready_at = time.time() + plan_delay





                    # 记录思维到 cognition（在行动之前）

                    if thought:

                        a.write_cognition(f"### 第{self.day}天 {self.game_hour:.1f}点\n决策思考：{thought}\n计划行动：{action_type} -> {matched_loc}，{action}")



                    self._log(

                        f"[行动计划] {actor_label}: 思考={localize_visible_character_names(thought or '正在判断下一步')}；"

                        f"计划={localize_visible_character_names(expected_result or action or '等待行动')}",

                        "action",

                    )



                    # 展示节奏：模型一次性给出思考/计划/行动，但玩家先看到思考与计划，

                    # 短暂停顿后再看到 NPC 实际开始行动。

                    time.sleep(plan_delay)
                    if _decision_cancelled():
                        return





                    # 判断是否需要移动

                    needs_movement = self._action_needs_movement(a, action_type, matched_loc, target_obj, target_person)





                    if needs_movement:

                        # 确定目标参考中心 (tx, ty)

                        tx, ty = a.x, a.y

                        path_found = False
                        skip_repeat_target_offset = False

                        target_agent = self.agents.get(target_person) if target_person else None

                        if target_agent and target_agent.is_alive:

                            if target_person == self.detective_name:
                                tx, ty = target_agent.x, target_agent.y
                            available, busy_reason = self._target_available_for_approach(n, target_person)

                            if not available:

                                self._log(f"[LLM状态] {actor_label}: 暂不接近 {display_name_for_person(target_person)}，{busy_reason}", "think")

                                _fallback_continue_current(f"目标暂时不适合交谈：{busy_reason}")

                                a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                                return

                            if target_person != self.detective_name:

                                tx, ty = target_agent.x, target_agent.y

                            prefer_h = target_person != self.detective_name
                            preferred_distance = 2 if prefer_h else 1

                            if action_type in {"talk", "socialize"} and self._agent_distance(a, target_agent) <= preferred_distance:
                                a.target_x, a.target_y = a.x, a.y
                                self.agent_paths.pop(n, None)
                                path_found = True
                                skip_repeat_target_offset = True
                                path_res = None
                            elif not path_found:
                                path_res = self._path_adjacent_to(
                                    (a.x, a.y),
                                    (tx, ty),
                                    blocked=self._occupied_tiles({n, target_person}),
                                    prefer_horizontal=prefer_h,
                                    preferred_distance=preferred_distance,
                                )

                            if path_res:

                                best_tx, best_ty, path = path_res

                                a.target_x, a.target_y = best_tx, best_ty

                                self.agent_paths[n] = path

                                path_found = True

                            elif not path_found:

                                self._log(f"[路径失败] {display_name_for_person(n)}: 无法接近 {display_name_for_person(target_person)}，稍后重试", "think")

                                _fallback_continue_current(f"暂时无法接近{display_name_for_person(target_person)}")

                                a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                                return

                        elif matched_loc == "home":

                            home_cfg = AGENT_CONFIGS.get(n, {}).get("home", {"x": 70, "y": 40})

                            tx, ty = home_cfg["x"], home_cfg["y"]

                            if target_obj and hasattr(a, 'spatial_memory') and a.spatial_memory:

                                obj_coord = self._find_object_in_spatial_memory(a, "home", target_obj)

                                if obj_coord:

                                    tx, ty = obj_coord

                        elif matched_loc in LANDMARKS:

                            lm = LANDMARKS[matched_loc]

                            tx, ty = lm["x"], lm["y"]

                            if target_obj and hasattr(a, 'spatial_memory') and a.spatial_memory:

                                obj_coord = self._find_object_in_spatial_memory(a, matched_loc, target_obj)

                                if obj_coord:

                                    tx, ty = obj_coord

                        else:

                            # 其它地点（如特定公寓房间），从空间记忆查找

                            if target_obj and hasattr(a, 'spatial_memory') and a.spatial_memory:

                                obj_coord = self._find_object_in_spatial_memory(a, matched_loc, target_obj)

                                if obj_coord:

                                    tx, ty = obj_coord



                        # 精准物件互动必须停在物件邻格，不能与物件重叠。

                        if target_obj and hasattr(a, 'spatial_memory') and a.spatial_memory:

                            obj_coord = self._find_object_in_spatial_memory(a, matched_loc, target_obj)

                            if obj_coord:

                                tx, ty = obj_coord

                                path_res = self._path_adjacent_to((a.x, a.y), (tx, ty))

                                if path_res:

                                    best_tx, best_ty, path = path_res

                                    a.target_x, a.target_y = best_tx, best_ty

                                    self.agent_paths[n] = path

                                    path_found = True

                                else:

                                    self._log(f"[路径失败] {actor_label}: 无法站到 {localize_visible_character_names(target_obj)} 附近，稍后重试", "think")

                                    _fallback_continue_current(f"暂时无法接近{localize_visible_character_names(target_obj)}")

                                    a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                                    return





                        if not path_found:

                            # 兜底：地标中心点寻路，增加 ±5 随机偏移以防止重叠，

                            # 关键修复：按到目标中心 (tx, ty) 的曼哈顿距离升序排序，使 NPC 尽量走到核心中心/内部，而不是卡在入口！

                            best_tx, best_ty = tx, ty

                            if self.collision_maze:

                                candidates = []

                                for _ in range(20):

                                    cx = tx + random.randint(-5, 5)

                                    cy = ty + random.randint(-5, 5)

                                    h = len(self.collision_maze)

                                    w = len(self.collision_maze[0]) if h else 0

                                    if (0 <= cx < w and 0 <= cy < h

                                            and self.collision_maze[cy][cx] == 0

                                            and self._is_tile_free_of_blocking_objects(cx, cy)):

                                        path = self._find_navigation_path((a.x, a.y), (cx, cy))

                                        if path:

                                            # 计算与真正目标中心 (tx, ty) 的距离，而不是起点距离！

                                            dist_to_target = abs(cx - tx) + abs(cy - ty)

                                            candidates.append((cx, cy, dist_to_target))

                                if candidates:

                                    candidates.sort(key=lambda c: c[2])

                                    best_tx, best_ty = candidates[0][0], candidates[0][1]

                                    a.target_x, a.target_y = best_tx, best_ty

                                    self.agent_paths.pop(n, None)  # 由 _move_agents 重新 BFS 寻路

                                else:

                                    a.target_x, a.target_y = tx + random.randint(-2, 2), ty + random.randint(-2, 2)

                                    self.agent_paths.pop(n, None)

                            else:

                                a.target_x, a.target_y = tx + random.randint(-2, 2), ty + random.randint(-2, 2)

                                self.agent_paths.pop(n, None)





                        center_coord = (int(tx), int(ty))
                        if not skip_repeat_target_offset and getattr(a, "_last_plan_target_coord", None) == center_coord:
                            repeat_target = self._random_walkable_around_target(
                                n,
                                a,
                                center_coord[0],
                                center_coord[1],
                                blocked_names={n, target_person} if target_person else {n},
                            )
                            if repeat_target:
                                nx, ny, path = repeat_target
                                a.target_x, a.target_y = nx, ny
                                self.agent_paths[n] = path
                                path_found = True
                        a._last_plan_target_coord = center_coord

                        a.runtime_state = "starting_action"
                        self._mark_action_started(a, time.time())

                        a.current_thought = ""

                        a.current_thought_time = 0

                        obj_log = f"，目标物件：{target_obj}" if target_obj else ""

                        self._log(

                            f"[开始行动] {actor_label}: 前往 {self._destination_label_zh(matched_loc)}{localize_visible_character_names(obj_log)}，"

                            f"准备：{localize_visible_character_names(a.current_action)}（{ACTION_TYPE_LABELS_ZH.get(action_type, action_type)}）",

                            "action",

                        )

                    else:

                        # 不需要移动：原地执行

                        a.runtime_state = "starting_action"

                        a.current_thought = ""

                        a.current_thought_time = 0

                        current_center = (int(a.x), int(a.y))
                        if getattr(a, "_last_plan_target_coord", None) == current_center or (a.target_x, a.target_y) == (a.x, a.y):
                            neighbor = self._neighbor_action_path(n, a)
                            if neighbor:
                                nx, ny, path = neighbor
                                a.target_x, a.target_y = nx, ny
                                self.agent_paths[n] = path
                        a._last_plan_target_coord = current_center

                        self._mark_action_started(a, time.time())

                        # 确保 current_location 是正确的

                        if not a.current_location:

                            a.current_location = self._reverse_lookup_location(a.x, a.y)

                        self._log(

                            f"[开始行动] {actor_label}: 在原地 {self._destination_label_zh(a.current_location)} "

                            f"执行：{localize_visible_character_names(a.current_action)}（{ACTION_TYPE_LABELS_ZH.get(action_type, action_type)}）",

                            "action",

                        )





                except Exception as e:

                    loc_now = a.current_location or self._reverse_lookup_location(a.x, a.y) or "当前位置"
                    fallback_action = self._default_continuing_action(n, loc_now)
                    a.current_location = loc_now
                    a.current_action = fallback_action
                    a.current_action_type = "continue_current"
                    a.current_emoji = self._get_emoji(fallback_action)
                    a._pending_action = {
                        "action_type": "continue_current",
                        "target_location": loc_now,
                        "target_object": "",
                        "target_person": "",
                        "action": fallback_action,
                        "thought": f"模型暂时无法给出计划：{e}",
                        "expected_result": "完成当前事务",
                    }
                    a.runtime_state = "starting_action"
                    self._mark_action_started(a, time.time())
                    self._log(f"[LLM状态] {display_name_for_person(n)}: 行动决策失败：{e}，转为continue_current，稍后重试", "think")

                    a._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)

                finally:

                    a._is_thinking = False





            t = threading.Thread(target=_llm_thread, args=(name, agent, nearby_info, scene_info, obs_packet, decision_generation), daemon=True)

            t.start()





    def _get_emoji(self, action: str) -> str:

        action_lower = action.lower()

        for key, emoji in ACTION_EMOJIS.items():

            if key in action_lower:

                return emoji

        # 根据 action_type 返回默认 emoji

        if "investigat" in action_lower or "调查" in action_lower:

            return "\U0001f50d"

        if "observ" in action_lower or "观察" in action_lower:

            return "\U0001f440"

        if "work" in action_lower or "工作" in action_lower:

            return "\U0001f4bc"

        if "rest" in action_lower or "休息" in action_lower:

            return "\U0001f634"

        if "social" in action_lower or "社交" in action_lower:

            return "\U0001f5e3"

        if "talk" in action_lower or "交谈" in action_lower:

            return "\U0001f4ac"

        if "hide" in action_lower or "隐藏" in action_lower:

            return "\U0001f575"

        if "inspect" in action_lower or "检查" in action_lower:

            return "\U0001f50e"

        return "\U0001f4cd"





    def _find_object_in_spatial_memory(self, agent, location_name: str, object_name: str):

        """从空间记忆中查找物件坐标，返回 (x, y) 或 None"""

        sm = getattr(agent, 'spatial_memory', {})

        if not sm:

            return None

        obj_lower = object_name.lower()





        # 1. 兼容 "home" 等通用语义映射，提取空间记忆中的实际住宅键名

        actual_locations = [location_name]

        if location_name == "home":

            actual_locations.extend([k for k in sm.keys() if agent.name in k or "Home" in k or "apartment" in k])





        # 2. 遍历记忆树确认角色是否确实记得该地点有该物体种类（支持地标名模糊包含匹配）

        has_object = False

        target_loc = location_name

        for loc in actual_locations:

            for sm_key in sm.keys():

                if loc.lower() in sm_key.lower() or sm_key.lower() in loc.lower():

                    arenas = sm[sm_key]

                    for arena_name, objects in arenas.items():

                        for obj in objects:

                            if obj_lower in obj.lower() or obj.lower() in obj_lower:

                                has_object = True

                                target_loc = sm_key

                                break

                        if has_object:

                            break

                if has_object:

                    break

            if has_object:

                break





        if not has_object:

            return None





        # 3. 在 100x140 物理网格地图数据中反查属于该特定区域内且包含 object_name 的具体交互物件的真实坐标

        best_coord = None

        best_dist = float('inf')





        ref_x, ref_y = agent.x, agent.y

        if target_loc in LANDMARKS:

            ref_x, ref_y = LANDMARKS[target_loc]["x"], LANDMARKS[target_loc]["y"]

        else:

            # 兼容模糊匹配获取地标中心点

            for lm_name, lm in LANDMARKS.items():

                if target_loc.lower() in lm_name.lower() or lm_name.lower() in target_loc.lower():

                    ref_x, ref_y = lm["x"], lm["y"]

                    break





        h = len(self.go_maze)

        w = len(self.go_maze[0]) if h > 0 else 0





        for y in range(h):

            for x in range(w):

                # 检查该格点是否在目标区域内（高容错模糊包含匹配！）

                sec_val = self.sector_maze[y][x]

                tile_sec = self.sector_dict.get(sec_val, "")

                if not tile_sec:

                    continue

                if not (target_loc.lower() in tile_sec.lower() or tile_sec.lower() in target_loc.lower()):

                    continue





                # 检查该格点是否有对应物品

                val = self.go_maze[y][x]

                if val in self.go_dict:

                    tile_obj = self.go_dict[val]

                    if obj_lower in tile_obj.lower() or tile_obj.lower() in obj_lower:

                        # 找到了该地标下的该物体！计算与参考点的曼哈顿距离就近匹配

                        dist = abs(x - ref_x) + abs(y - ref_y)

                        if dist < best_dist:

                            best_dist = dist

                            best_coord = (x, y)





        if best_coord:

            return best_coord





        return None





    def _reverse_lookup_location(self, x: int, y: int) -> str:

        """根据坐标反查最近的地点名"""

        best_name = ""

        best_dist = float('inf')

        for lm_name, lm in LANDMARKS.items():

            dist = abs(x - lm["x"]) + abs(y - lm["y"])

            if dist < best_dist:

                best_dist = dist

                best_name = lm_name

        if best_name:
            return best_name
        return "当前位置附近"




    # ── blocking-object keywords used by _is_tile_free_of_blocking_objects ──

    _BLOCKING_OBJECT_KEYWORDS = [

        "shelf", "counter", "table", "desk", "bed", "closet",

        "sofa", "podium", "piano", "refrigerator", "toaster",

        "sink", "toilet", "shower", "easel", "blackboard",

        "computer", "cooking area", "bar customer seating",

        "cafe customer seating", "classroom student seating",

        "common room table", "common room sofa",

    ]





    def _is_tile_free_of_blocking_objects(self, x: int, y: int) -> bool:

        """Return True if tile (x,y) has no furniture-type game object that agents

        should not stand on top of (shelves, counters, tables, etc.)."""

        if not hasattr(self, "go_maze") or self.go_maze is None:

            return True

        h = len(self.go_maze)

        w = len(self.go_maze[0]) if h else 0

        if not (0 <= x < w and 0 <= y < h):

            return False

        val = self.go_maze[y][x]

        if val == 0 or val not in self.go_dict:

            return True

        obj_name = self.go_dict[val].lower()

        # "behind" zones are walkable spaces behind counters where agents stand to work
        if "behind" in obj_name:
            return True

        # In Hobbs Cafe kitchen counter corridor, cooking area & sink are on the only path to the apartment
        if hasattr(self, "sector_maze") and self.sector_maze is not None:
            if y == 19 and 75 <= x <= 77:
                sid = self.sector_maze[y][x]
                if hasattr(self, "sector_dict") and self.sector_dict is not None:
                    if sid in self.sector_dict and "Hobbs Cafe" in self.sector_dict[sid]:
                        return True

        for kw in self._BLOCKING_OBJECT_KEYWORDS:

            if kw in obj_name:

                return False

        return True





    def _navigation_maze(self, start=None, blocked=None):

        """Combine wall and furniture collisions for pathfinding."""

        if not self.collision_maze:

            return self.collision_maze

        blocked = set(blocked or ())

        maze = [row[:] for row in self.collision_maze]

        for y, row in enumerate(maze):

            for x, value in enumerate(row):

                if value == 0 and not self._is_tile_free_of_blocking_objects(x, y):

                    row[x] = 1

        for bx, by in blocked:

            if 0 <= by < len(maze) and 0 <= bx < len(maze[by]):

                maze[by][bx] = 1

        if start:

            sx, sy = start

            if 0 <= sy < len(maze) and 0 <= sx < len(maze[sy]):

                maze[sy][sx] = 0

        return maze





    def _find_navigation_path(self, start, target, blocked=None):

        """Find a path without walking through walls or blocking furniture."""

        return bfs_path(self._navigation_maze(start, blocked=blocked), start, target)





    def _occupied_tiles(self, exclude_names=None):

        excluded = set(exclude_names or ())

        return {

            (agent.x, agent.y)

            for name, agent in self.agents.items()

            if name not in excluded and agent.is_alive

        }





    def _reachable_component(self, start) -> set:

        """Return all walkable tiles connected to start in the collision maze."""

        if not self.collision_maze:

            return {start}

        height = len(self.collision_maze)

        width = len(self.collision_maze[0]) if height else 0

        sx, sy = start

        if not (0 <= sx < width and 0 <= sy < height):

            return set()

        if self.collision_maze[sy][sx] != 0:

            nearest = self._nearest_walkable_tile(start, radius=8)

            if not nearest:

                return set()

            sx, sy = nearest





        visited = {(sx, sy)}

        queue = deque([(sx, sy)])

        while queue:

            x, y = queue.popleft()

            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):

                nx, ny = x + dx, y + dy

                if (

                    0 <= nx < width

                    and 0 <= ny < height

                    and (nx, ny) not in visited

                    and self.collision_maze[ny][nx] == 0

                ):

                    visited.add((nx, ny))

                    queue.append((nx, ny))

        return visited





    def _nearest_walkable_tile_in_component(self, target, component: set, radius=8, blocked=None):

        blocked = set(blocked or ())

        if not component:

            return None

        tx, ty = target

        for distance in range(radius + 1):

            for dx in range(-distance, distance + 1):

                dy = distance - abs(dx)

                for sign in (1, -1):

                    candidate = (tx + dx, ty + (dy * sign))

                    if candidate in component and candidate not in blocked:

                        # Exclude tiles occupied by blocking furniture objects

                        cx, cy = candidate

                        if not self._is_tile_free_of_blocking_objects(cx, cy):

                            continue

                        return candidate

        return None





    def _nearest_walkable_tile(self, target, radius=8, blocked=None):

        if not self.collision_maze:

            return target

        blocked = set(blocked or ())

        height = len(self.collision_maze)

        width = len(self.collision_maze[0]) if height else 0

        tx, ty = target

        for distance in range(radius + 1):

            for dx in range(-distance, distance + 1):

                dy = distance - abs(dx)

                for sign in (1, -1):

                    nx, ny = tx + dx, ty + (dy * sign)

                    if not (0 <= nx < width and 0 <= ny < height):

                        continue

                    if (nx, ny) in blocked:

                        continue

                    if self.collision_maze[ny][nx] == 0:

                        # Exclude tiles occupied by blocking furniture objects

                        if not self._is_tile_free_of_blocking_objects(nx, ny):

                            continue

                        return nx, ny

        return None





    def _assign_reachable_target_near(self, agent, name: str, target, radius=12, blocked=None) -> bool:

        blocked_tiles = set(blocked or self._occupied_tiles({name}))

        path_result = self._nearest_reachable_path(
            (agent.x, agent.y),
            target,
            radius=radius,
            blocked=blocked_tiles,
        )

        if not path_result:

            return False

        nx, ny, path = path_result

        agent.target_x, agent.target_y = nx, ny

        self.agent_paths[name] = path

        return True




    def _nearest_reachable_path(self, start, target, radius=12, blocked=None):

        """Find a walkable nearby target and path without teleporting."""

        if not self.collision_maze:

            return None

        blocked = set(blocked or ())

        height = len(self.collision_maze)

        width = len(self.collision_maze[0]) if height else 0

        sx, sy = start

        tx, ty = target

        if not (0 <= sx < width and 0 <= sy < height):

            return None

        if self.collision_maze[sy][sx] != 0:

            return None





        seen = set()

        candidates = []

        for r in range(radius + 1):

            for dx in range(-r, r + 1):

                dy = r - abs(dx)

                for sign in (1, -1):

                    nx, ny = tx + dx, ty + (dy * sign)

                    if (nx, ny) in seen:

                        continue

                    seen.add((nx, ny))

                    if (

                        0 <= nx < width

                        and 0 <= ny < height

                        and (nx, ny) not in blocked

                        and self.collision_maze[ny][nx] == 0

                        and self._is_tile_free_of_blocking_objects(nx, ny)

                    ):

                        candidates.append((nx, ny))





        for nx, ny in candidates:

            path = self._find_navigation_path(start, (nx, ny), blocked=blocked)

            if path is not None:

                return nx, ny, path

        return None





    def _path_adjacent_to(self, start, target, blocked=None, prefer_horizontal=False, preferred_distance=1):
        """Find a reachable walkable tile adjacent to *target* and return (adj_x, adj_y, path).





        Used so NPCs / Crow stop in front of a target coordinate rather than on top of it.

        Searches 4-directional neighbours first; expands search if all are blocked.

        When prefer_horizontal=True, left/right tiles are prioritized over up/down.
        preferred_distance=2 is used for NPC-NPC conversation so one empty tile
        can remain between the two character models.
        Falls back to nearest-reachable if no adjacent tile can be reached.

        Returns None when no reachable walkable tile exists at all.





        IMPORTANT: adjacent tiles that contain blocking game objects (shelves,

        counters, etc.) are excluded so agents never stop on top of furniture.

        """

        if not self.collision_maze:

            return None

        blocked = set(blocked or ())

        height = len(self.collision_maze)

        width = len(self.collision_maze[0]) if height else 0

        sx, sy = start

        tx, ty = target

        if not (0 <= sx < width and 0 <= sy < height):

            return None





        # helper: tile is valid to stand on

        def _valid_stand_tile(nx, ny):

            if not (0 <= nx < width and 0 <= ny < height):

                return False

            if (nx, ny) in blocked:

                return False

            if self.collision_maze[ny][nx] != 0:

                return False

            if not self._is_tile_free_of_blocking_objects(nx, ny):

                return False

            return True





        # 1. Collect preferred stand tiles around the target.
        adjacent = []
        if prefer_horizontal:
            offsets = [
                (-preferred_distance, 0),
                (preferred_distance, 0),
                (-1, 0),
                (1, 0),
                (0, -preferred_distance),
                (0, preferred_distance),
                (0, -1),
                (0, 1),
            ]
        else:
            offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        seen_offsets = set()
        for dx, dy in offsets:
            if (dx, dy) in seen_offsets:
                continue
            seen_offsets.add((dx, dy))
            nx, ny = tx + dx, ty + dy
            if _valid_stand_tile(nx, ny):
                adjacent.append((nx, ny))




        # 2. Expand search if no direct adjacent walkable tile exists

        if not adjacent:

            for r in range(2, 7):

                for dx in range(-r, r + 1):

                    for dy in range(-r, r + 1):

                        if abs(dx) + abs(dy) != r:

                            continue

                        nx, ny = tx + dx, ty + dy

                        if _valid_stand_tile(nx, ny):

                            adjacent.append((nx, ny))

                if adjacent:

                    break





        if not adjacent:

            return None





        # 3. Choose the stand tile with the shortest reachable path.
        # When prefer_horizontal=True, prefer left/right at the requested
        # distance, then left/right adjacent, then vertical alternatives.
        best = None
        best_score = None
        for nx, ny in adjacent:
            path = self._find_navigation_path(start, (nx, ny), blocked=blocked)
            if path is not None:
                if prefer_horizontal:
                    dx = nx - tx
                    dy = ny - ty
                    gap = abs(dx) + abs(dy)
                    is_horizontal = dy == 0 and dx != 0
                    is_vertical = dx == 0 and dy != 0
                    if is_horizontal and gap == preferred_distance:
                        rank = 0
                    elif is_horizontal:
                        rank = 1
                    elif is_vertical and gap == preferred_distance:
                        rank = 2
                    elif is_vertical:
                        rank = 3
                    else:
                        rank = 4
                    score = (rank, len(path))
                else:
                    score = (0, len(path))
                if best is None or score < best_score:

                    best = (nx, ny, path)

                    best_score = score





        return best





    def _best_manual_move_path(self, start, target, radius=4, blocked=None):

        """Choose a nearby click destination without forcing a long walk around walls."""

        if not self.collision_maze:

            return None

        blocked = set(blocked or ())

        height = len(self.collision_maze)

        width = len(self.collision_maze[0]) if height else 0

        sx, sy = start

        tx, ty = target

        if not (0 <= sx < width and 0 <= sy < height):

            return None

        if self.collision_maze[sy][sx] != 0:

            return None





        best = None

        for ny in range(ty - radius, ty + radius + 1):

            for nx in range(tx - radius, tx + radius + 1):

                if not (0 <= nx < width and 0 <= ny < height):

                    continue

                if self.collision_maze[ny][nx] != 0:

                    continue

                if (nx, ny) in blocked and (nx, ny) != start:

                    continue

                if not self._is_tile_free_of_blocking_objects(nx, ny):

                    continue

                path = self._find_navigation_path(start, (nx, ny))

                if path is None:

                    continue

                click_distance = abs(nx - tx) + abs(ny - ty)

                score = len(path) + click_distance * 2

                candidate = (score, click_distance, len(path), nx, ny, path)

                if best is None or candidate[:3] < best[:3]:

                    best = candidate

        if best is None:

            return None

        _, _, _, nx, ny, path = best

        return nx, ny, path





    def _move_agents(self):

        """BFS寻路移动（每tick移1格），寻路失败直接传送；到达后进入acting状态"""

        now = time.time()

        for name, agent in self.agents.items():

            if not agent.is_alive:

                continue

            # Jailed residents cannot move

            if name in self._jailed:

                continue

            # Delayed departure gate: NPC shows speech first, walks later

            departure_delay = getattr(agent, '_departure_delay_until', 0)

            if departure_delay > 0 and now < departure_delay:

                continue
            move_ready_at = getattr(agent, "_action_move_ready_at", 0)
            if move_ready_at > 0 and now < move_ready_at:
                continue





            if agent.x == agent.target_x and agent.y == agent.target_y:

                if getattr(agent, "runtime_state", "") == "moving" and getattr(agent, "_pending_action", None):
                    self._arrive_at_pending_action(name, agent)
                    loc = self._reverse_lookup_location(agent.x, agent.y)
                    agent.current_location = loc
                    continue

                if self.agent_paths.pop(name, None):

                    # 刚到达目标 → 进入 acting 状态

                    agent.runtime_state = "acting"

                    agent._arrived_at_time = time.time()

                    # 更新 current_location 为反查地名（避免坐标泄漏到日志）

                    loc = self._reverse_lookup_location(agent.x, agent.y)

                    agent.current_location = loc

                continue





            path = self.agent_paths.get(name)

            need_repath = False

            if not path:

                need_repath = True

            else:

                if path[-1] != (agent.target_x, agent.target_y):

                    need_repath = True





            if need_repath:

                blocked_tiles = self._occupied_tiles({name})

                new_path = self._find_navigation_path(

                    (agent.x, agent.y),

                    (agent.target_x, agent.target_y),

                    blocked=blocked_tiles,

                )

                if new_path:

                    self.agent_paths[name] = new_path

                else:

                    # BFS 寻路失败，直接传送

                    self.agent_paths.pop(name, None)

                    fallback = self._nearest_reachable_path(

                        (agent.x, agent.y),

                        (agent.target_x, agent.target_y),

                        blocked=self._occupied_tiles({name}),

                    )

                    if fallback:

                        nx, ny, fallback_path = fallback

                        agent.target_x = nx

                        agent.target_y = ny

                        self.agent_paths[name] = fallback_path

                    else:

                        agent.target_x = agent.x

                        agent.target_y = agent.y

                        agent.runtime_state = "idle"

                        self._log(f"[路径失败] {name}: 无法到达目标，停止移动并等待下一次决策", "think")

                        continue





            path = self.agent_paths.get(name)

            if path:

                agent.runtime_state = "moving"

                steps_per_tick = CONFIG.get("game", {}).get("move_steps_per_tick", 3)

                steps = min(steps_per_tick, len(path))

                for _ in range(steps):

                    if not path:

                        break

                    next_pos = path[0]

                    if next_pos in self._occupied_tiles({name}):

                        self.agent_paths.pop(name, None)

                        break

                    if not self._is_tile_free_of_blocking_objects(*next_pos):

                        self.agent_paths.pop(name, None)

                        break

                    agent.x, agent.y = next_pos

                    path.pop(0)

                if not path:

                    self.agent_paths.pop(name, None)

                    loc = self._reverse_lookup_location(agent.x, agent.y)

                    agent.current_location = loc

                    if getattr(agent, "_pending_action", None):
                        self._arrive_at_pending_action(name, agent)
                    else:
                        agent.runtime_state = "acting"
                        agent._arrived_at_time = time.time()



        self._update_body_burial_sequence()





    def _action_needs_movement(self, agent, action_type: str, target_location: str,

                               target_object: str = "", target_person: str = "") -> bool:

        """判断行动是否需要物理移动"""

        # move_to 始终需要移动

        if action_type in ("move_to", "移动", "move", "walking"):

            return True



        if action_type in ("talk", "socialize", "交谈", "社交") and target_person:

            target_agent = self.agents.get(target_person)

            if target_agent and target_agent.is_alive:

                if target_person == self.detective_name:
                    return self._agent_distance(agent, target_agent) > 1
                return self._agent_distance(agent, target_agent) > 2





        # 如果指定了目标物体，且智能体离该物体的曼哈顿距离 > 1，则需要移动到物体旁！

        if target_object and hasattr(agent, 'spatial_memory') and agent.spatial_memory:

            obj_coord = self._find_object_in_spatial_memory(agent, target_location or agent.current_location or "", target_object)

            if obj_coord:

                dist = abs(agent.x - obj_coord[0]) + abs(agent.y - obj_coord[1])

                if dist > 1:

                    return True





        # 如果目标地点和当前位置不同，也需要移动

        current_loc = agent.current_location or ""

        if target_location and current_loc:

            tl = target_location.lower().strip()

            cl = current_loc.lower().strip()

            # 模糊比较

            if tl != cl and not (tl in cl or cl in tl):

                return True





        # 同一地点或无需移动的类型：原地执行

        return False





    def _complete_agent_action(self, name: str, agent) -> None:

        """完成当前 pending action：生成结果句子、日志[行动结果]、写入记忆和 cognition"""

        pending = getattr(agent, '_pending_action', None)

        if not pending:

            # 无待完成行动是正常状态（侦探手动操作、空闲等），静默返回

            return





        action_type = pending.get("action_type", "continue_current")
        if action_type == "stay":
            action_type = "continue_current"
        action = pending.get("action", "")

        location = pending.get("target_location", agent.current_location or "某处")

        target_object = pending.get("target_object", "")

        target_person = pending.get("target_person", "")

        expected_result = pending.get("expected_result", "")



        if action_type in ("talk", "socialize") and target_person:

            target_agent = self.agents.get(target_person)

            if target_agent and target_agent.is_alive:

                threshold = 1 if target_person == self.detective_name else 2

                if self._agent_distance(agent, target_agent) <= threshold:
                    if target_person == self.detective_name:
                        detective = self.agents.get(self.detective_name)
                        if detective and getattr(detective, "in_conversation_with", None) is not None:
                            self._log(
                                f"[行动结果] {display_name_for_person(name)}: 想与{display_name_for_person(target_person)}交谈，"
                                f"但对方正在与{display_name_for_person(detective.in_conversation_with)}聊天，稍候再试",
                                "action",
                            )
                            self._redirect_to_visible_continue_current(name, agent, "克罗正在交谈，暂不插话")
                            agent._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)
                            return

                        agent.current_thought = ""
                        agent.current_thought_time = 0
                        agent.current_action = ""
                        agent.current_action_type = ""
                        if not self._trigger_npc_to_detective_chat(name, action, expected_result):
                            self._redirect_to_visible_continue_current(name, agent, "克罗正在交谈，暂不插话")
                            return
                        agent._pending_action = None
                        agent.add_memory(
                            f"第{self.day}天 {self.game_hour:.1f}点，我接近警长并主动说明：{action}",
                            self.day
                        )
                        return

                    # NPC-to-NPC chat: verify target is not already busy
                    if getattr(target_agent, "in_conversation_with", None) is not None:
                        self._log(
                            f"[行动结果] {display_name_for_person(name)}: 想与{display_name_for_person(target_person)}交谈，"
                            f"但对方正在与{display_name_for_person(target_agent.in_conversation_with)}聊天，稍候再试",
                            "action",
                        )
                        self._redirect_to_visible_continue_current(name, agent, "对方正在交谈，先避开等待")
                        agent._next_llm_retry_time = time.time() + CONFIG.get("llm", {}).get("retry_delay_seconds", 5)
                        return
                    self._log(
                        f"[行动结果] {display_name_for_person(name)}: 接近{display_name_for_person(target_person)}，开始交谈。",
                        "action",
                    )
                    # Clear stale thought/plan for initiator before NPC-NPC chat
                    agent.current_thought = ""
                    agent.current_thought_time = 0
                    agent.add_memory(
                        f"第{self.day}天 {self.game_hour:.1f}点，我接近{display_name_for_person(target_person)}并准备交谈：{action}",
                        self.day
                    )
                    agent._pending_action = None
                    self._trigger_npc_chat(name, target_person)
                    return
                else:
                    # Out of range: ordinary completion should not claim a chat happened.
                    return
        # 代码生成结果句子

        result_sentence = agent.get_action_result(

            action_type, action, location,

            target_object, target_person, expected_result

        )





        # 日志

        self._log(

            f"[行动结果] {display_name_for_person(name)}: {localize_visible_character_names(result_sentence)}",

            "action",

        )





        # 写入记忆（使用 add_memory，也会记录到 memory_index）

        agent.add_memory(

            f"第{self.day}天 {self.game_hour:.1f}点，{result_sentence}",

            self.day

        )





        # 更新 cognition 和 scratch

        agent.update_scratch(currently=f"刚完成：{result_sentence[:100]}")

        observation_after = self._build_observation_packet(name, agent)
        self._record_observation_event(
            event_type="action_complete",
            subject=name,
            text=f"{display_name_for_person(name)}完成：{localize_visible_character_names(result_sentence)}",
            x=agent.x,
            y=agent.y,
            public=False,
        )
        self._enqueue_memory_task(
            name,
            {
                "kind": "action_completed",
                "day": self.day,
                "game_hour": self.game_hour,
                "action_type": action_type,
                "target_location": location,
                "target_object": target_object,
                "target_person": target_person,
                "action": action,
                "action_status": pending.get("action_status", ""),
                "thought": pending.get("thought", ""),
                "expected_result": expected_result,
                "action_result": result_sentence,
                "observation_before": pending.get("observation_before", {}),
                "observation_after": observation_after,
                "visible_events": observation_after.get("visible_events", []),
            },
        )





        # 记录到行动历史（用于防止重复行为循环）

        if not hasattr(agent, 'action_history'):

            agent.action_history = []

        agent.action_history.append({

            "action_type": action_type,

            "location": location,

            "action": action,

            "time": time.time()

        })

        if len(agent.action_history) > 10:

            agent.action_history = agent.action_history[-10:]





        # 清除 pending

        agent._pending_action = None

        agent._action_completed = True
        self._clear_action_status_bubble(name)





    # ==================== 侦探交互 ====================





    def move_detective_to(self, x, y, location=""):

        """玩家点击地图移动侦探"""

        with self._lock:

            if getattr(self, "_body_burial", None):
                return False
            self._detective_chat_pending_target = None
            if self.phase == GamePhase.DUSK_DISCUSSION:
                return False
            if self.phase not in (GamePhase.DAY, GamePhase.DUSK_DISCUSSION) or self.game_over or getattr(self, "_gathering_active", False):
                return False
            detective = self.agents.get(self.detective_name)

            if not detective or not detective.is_alive:

                return False

            requested_x = int(x)

            requested_y = int(y)

            manual_path = self._best_manual_move_path(

                (detective.x, detective.y),

                (requested_x, requested_y),

                blocked=self._occupied_tiles({self.detective_name}),

            )

            if manual_path:

                target_x, target_y, path = manual_path

                detective.target_x = target_x

                detective.target_y = target_y

                self.agent_paths[self.detective_name] = path

            else:

                detective.target_x = requested_x

                detective.target_y = requested_y

                self.agent_paths.pop(self.detective_name, None)

            # 反查地点名，避免显示坐标

            raw_location = "" if location is None else str(location).strip()

            looks_like_coord = raw_location.startswith("(") and raw_location.endswith(")")

            if not raw_location or looks_like_coord:

                location = self._reverse_lookup_location(requested_x, requested_y)

            else:

                location = raw_location

            if not location:
                location = "当前位置附近"
            detective.current_location = location

            detective.current_action = "investigating"

            detective.current_emoji = "🔍"

            self._log(f"[开始行动] {self.detective_name}: 前往 {location}，准备调查", "action")

            return True





    def move_detective_to_agent(self, target_name: str) -> bool:

        """Move Crow toward a living resident selected in the side panel.





        Crow stops adjacent to the target NPC rather than overlapping coordinates.

        """

        with self._lock:

            if getattr(self, "_body_burial", None):
                self._detective_chat_pending_target = None
                return False
            target = self.agents.get(target_name)
            if not target or not target.is_alive or target_name == self.detective_name:
                self._detective_chat_pending_target = None
                return False




            detective = self.agents.get(self.detective_name)
            if not detective or not detective.is_alive:
                self._detective_chat_pending_target = None
                return False




            if self.phase not in (GamePhase.DAY, GamePhase.DUSK_DISCUSSION) or self.game_over or getattr(self, "_gathering_active", False):
                self._detective_chat_pending_target = None
                return False




            # Try to stop adjacent to the target agent

            result = self._path_adjacent_to(

                (detective.x, detective.y),

                (target.x, target.y),

                blocked=self._occupied_tiles({self.detective_name, target_name}),

            )

            if result:

                adj_x, adj_y, path = result

                detective.target_x = adj_x

                detective.target_y = adj_y

                self.agent_paths[self.detective_name] = path

                location = target.current_location or self._reverse_lookup_location(adj_x, adj_y)

                if not location:
                    location = "当前位置附近"
                detective.current_location = location

                detective.current_action = "investigating"
                detective.current_emoji = "🔍"
                self._detective_chat_pending_target = target_name
                self._log(f"[开始行动] {self.detective_name}: 前往 {location}，接近 {target_name}", "action")
                return True



            self._detective_chat_pending_target = None
            return False




    def create_clue(self, clue_type: str, summary: str, source: str,

                    related_person: str = "", location: str = "") -> ClueRecord:

        """Record a factual clue discovered by one resident."""

        if source not in self.agents:

            raise ValueError(f"Unknown clue source: {source}")

        clue = ClueRecord(

            clue_id=f"clue_{self.day}_{len(self.clues) + 1}",

            clue_type=clue_type,

            summary=summary,

            source=source,

            related_person=related_person,

            location=location or self.agents[source].current_location,

            created_day=self.day,

        )

        self.clues.append(clue)

        return clue





    def _deliver_pending_clues_to_crow(self, source: str) -> list[ClueRecord]:

        pending = undelivered_clues_for(self.clues, source)

        for clue in pending:

            clue.delivered_to_crow = True

            self.agents[self.detective_name].add_memory(

                f"Clue from {source}: {clue.summary}", self.day

            )

        return pending





    @staticmethod
    def _text_suggests_new_clue(*parts: str) -> bool:
        text = " ".join(str(part or "") for part in parts)
        if not text:
            return False
        keywords = ("线索", "证据", "异常", "可疑", "怀疑", "痕迹", "目击", "发现", "不对劲")
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _action_for_display(action: str) -> str:
        """Keep the visible action field focused on the concrete action, not reasoning."""
        text = " ".join(str(action or "").strip().split())
        if not text:
            return ""

        if text in {"适应小镇生活", "正常生活", "日常活动", "继续生活"}:
            return ""

        text = re.sub(r"^(Thought|Thinking|Reasoning)\s*[:：]\s*", "", text, flags=re.IGNORECASE)

        for marker in ("行动：", "行动:", "Action:", "action:"):
            if marker in text:
                text = text.split(marker, 1)[1].strip()

        split_markers = ("所以", "因此", "于是", "接下来", "然后", "现在")
        for marker in split_markers:
            if marker in text:
                candidate = text.rsplit(marker, 1)[1].strip(" ，,。.;；")
                if len(candidate) >= 4:
                    text = candidate
                    break

        sentences = [part.strip(" ，,。.;；") for part in re.split(r"[。！？.!?；;]+", text) if part.strip()]
        if len(sentences) > 1:
            first = sentences[0]
            reasoning_markers = ("我想", "我觉得", "我计划", "我认为", "因为", "为了", "需要先")
            if any(marker in first for marker in reasoning_markers):
                text = sentences[-1]

        text = re.sub(r"^(我会|我要|我准备|我打算|我将|开始|准备)\s*", "", text).strip()
        if re.match(r"^(去|前往|回到|返回|要回|留在)", text):
            verb_match = re.search(r"(检查|整理|准备|清点|修剪|擦拭|询问|调查|查看|记录).+", text)
            if verb_match:
                text = verb_match.group(0).strip()
            else:
                text = re.sub(r"^(去|前往|回到|返回|要回|留在)\S+\s*", "", text).strip()
        text = re.sub(r"^(检查|整理|准备|清点|修剪|擦拭|询问|调查)", r"\1", text).strip()
        if text in {"适应小镇生活", "正常生活", "日常活动", "继续生活"}:
            return ""
        if len(text) > 36:
            text = text[:36].rstrip("，,。.;；")
        return text or str(action or "").strip()




    def _agent_has_visible_clue_hint(self, name: str, agent) -> bool:

        if undelivered_clues_for(getattr(self, "clues", []), name):

            return True

        if name == self.detective_name or not getattr(agent, "is_alive", False):

            return False

        pending = getattr(agent, "_pending_action", {})

        if not isinstance(pending, dict):

            pending = {}

        last_decision = getattr(agent, "_last_decision", {})

        if not isinstance(last_decision, dict):

            last_decision = {}

        explicit_hint = (
            pending.get("has_detective_hint")
            or pending.get("has_visible_clue_hint")
            or last_decision.get("has_detective_hint")
            or last_decision.get("has_visible_clue_hint")
        )
        return explicit_hint is True




    @staticmethod

    def _agent_distance(a, b) -> int:

        return abs(a.x - b.x) + abs(a.y - b.y)



    @staticmethod
    def _decision_mentions_detective(*parts: str) -> bool:
        text = " ".join(str(part or "") for part in parts)
        return any(word in text for word in ("Crow", "crow", "克罗", "警长", "侦探"))

    @classmethod
    def _should_infer_detective_target(cls, action_type: str, *parts: str) -> bool:
        """Infer Crow only for urgent/direct reports when target_person is missing."""
        if str(action_type or "").strip().lower() not in {"talk", "socialize", "report"}:
            return False

        text = " ".join(str(part or "") for part in parts)
        if not cls._decision_mentions_detective(text):
            return False

        negative_urgent_markers = (
            "不是必须立即", "不是必须马上", "不必立即", "不必马上",
            "不用立即", "不用马上", "不需要立即", "不需要马上",
            "暂时不汇报", "暂不汇报", "先不汇报", "不是明确线索",
            "not urgent", "not immediate", "no need to report immediately",
        )
        if any(marker in text for marker in negative_urgent_markers):
            return False

        report_markers = (
            "主动汇报", "向警长汇报", "告诉警长", "找警长", "报告警长",
            "report to Crow", "tell Crow", "tell the sheriff",
        )
        urgent_markers = (
            "必须马上", "必须立即", "马上", "立即", "立刻", "紧急", "重要事情",
            "明确线索", "直接证据", "亲眼看到", "正在杀", "杀人", "凶手", "狼人", "weapon",
            "murderer", "werewolf", "direct evidence", "urgent",
        )
        return any(marker in text for marker in report_markers) and any(
            marker in text for marker in urgent_markers
        )

    def _target_area_is_clear_for_approach(self, actor_name: str, target_name: str, radius: int = 1) -> bool:
        """Avoid NPC queues around a target who is already effectively occupied."""

        target = self.agents.get(target_name)

        if not target:

            return False

        for other_name, other in self.agents.items():

            if other_name in {actor_name, target_name}:

                continue

            if not getattr(other, "is_alive", False) or other_name in self._jailed:

                continue

            if self._agent_distance(other, target) <= radius:

                return False

        return True



    def _target_available_for_approach(self, actor_name: str, target_name: str) -> tuple[bool, str]:

        target = self.agents.get(target_name)

        if not target or not getattr(target, "is_alive", False):

            return False, "目标不存在或已经无法交谈"

        if getattr(target, "in_conversation_with", None) is not None:
            return False, f"{display_name_for_person(target_name)}正在交谈"
        if self._detective_chat_target_reserved(target_name):
            return False, f"{display_name_for_person(target_name)}正等待克罗问话"
        if target_name == self.detective_name and getattr(self, "_detective_chat_active_target", None):
            return False, "克罗正在询问其他人"
        if not self._target_area_is_clear_for_approach(actor_name, target_name):

            return False, f"{display_name_for_person(target_name)}身边已经有人"

        return True, ""



    @staticmethod

    def _recent_passive_action_count(agent, limit: int = 3) -> int:

        passive = {"continue_current", "stay", "observe", "rest"}
        history = list(getattr(agent, "action_history", []) or [])[-limit:]

        return sum(1 for item in history if str(item.get("action_type", "")).lower() in passive)





    def _npc_chat_key(self, name1: str, name2: str) -> tuple[str, str]:

        return tuple(sorted((name1, name2)))





    def _clear_conversation_pair(self, name1: str, name2: str) -> None:

        a1 = self.agents.get(name1)

        a2 = self.agents.get(name2)

        if a1 and getattr(a1, "in_conversation_with", None) == name2:

            a1.in_conversation_with = None

            a1._conversation_started_at = 0

        if a2 and getattr(a2, "in_conversation_with", None) == name1:

            a2.in_conversation_with = None

            a2._conversation_started_at = 0

        self._npc_chat_tokens.pop(self._npc_chat_key(name1, name2), None)

        self.chat_bubbles.pop(name1, None)

        self.chat_bubbles.pop(name2, None)





    def _clear_conversation_if_too_far(self, name1: str, name2: str) -> bool:

        a1 = self.agents.get(name1)

        a2 = self.agents.get(name2)

        if not a1 or not a2:

            return False

        # NPC-NPC: allow center distance up to 2 (one empty space between them)

        threshold = 1 if (name1 == self.detective_name or name2 == self.detective_name) else 2

        if self._agent_distance(a1, a2) <= threshold:

            return False

        self._clear_conversation_pair(name1, name2)

        return True





    def _interrupt_agent_conversation(self, name: str) -> None:

        agent = self.agents.get(name)

        partner_name = getattr(agent, "in_conversation_with", None) if agent else None

        if not partner_name:

            return

        # Also clear thought/action/runtime state for the interrupted NPC and its partner

        partner_agent = self.agents.get(partner_name)

        for a in (agent, partner_agent):

            if a:

                a.current_thought = ""

                a.current_thought_time = 0

                a.current_action = ""

                a.current_action_type = ""

                a._pending_action = None

                a._last_decision = {}

                a._last_raw_response = ""

                a._is_thinking = False

                a._is_reflecting = False

        self._clear_conversation_pair(name, partner_name)





    @staticmethod

    def _generate_agent_response(agent, partner_name: str, message: str, day: int,

                                 priority: bool = False, max_retries: int = None) -> str:

        """Call Agent.generate_response with priority when supported.



        Tests often monkeypatch generate_response with a 3-arg lambda; production

        Agent instances accept the extra priority controls.

        """

        try:

            sig = inspect.signature(agent.generate_response)

            supports_kwargs = any(

                p.kind == inspect.Parameter.VAR_KEYWORD

                for p in sig.parameters.values()

            )

            if supports_kwargs or "priority" in sig.parameters or "max_retries" in sig.parameters:

                return agent.generate_response(

                    partner_name,

                    message,

                    day,

                    priority=priority,

                    max_retries=max_retries,

                )

        except (TypeError, ValueError):

            pass

        return agent.generate_response(partner_name, message, day)


    def _detective_chat_target_reserved(self, target_name: str) -> bool:
        return target_name in {
            getattr(self, "_detective_chat_active_target", None),
            getattr(self, "_detective_chat_pending_target", None),
        }

    def _release_conversation_for_expired_bubble(self, name: str, bubble: dict | None = None) -> None:
        bubble = bubble or self.chat_bubbles.get(name)
        target_name = bubble.get("target") if isinstance(bubble, dict) else None
        if not target_name:
            return
        agent = self.agents.get(name)
        target = self.agents.get(target_name)
        if agent and getattr(agent, "in_conversation_with", None) == target_name:
            agent.in_conversation_with = None
            agent._conversation_started_at = 0
            agent.runtime_state = "idle"
            agent._action_completed = True
        if target and getattr(target, "in_conversation_with", None) == name:
            target.in_conversation_with = None
            target._conversation_started_at = 0
            target.runtime_state = "idle"
            target._action_completed = True
        if hasattr(self, "_npc_chat_key"):
            self._npc_chat_tokens.pop(self._npc_chat_key(name, target_name), None)
        if name == getattr(self, "detective_name", None):
            if getattr(self, "_detective_chat_active_target", None) == target_name:
                self._detective_chat_active_target = None
            if getattr(self, "_detective_chat_pending_target", None) == target_name:
                self._detective_chat_pending_target = None
        if target_name == self.detective_name:
            if getattr(self, "_detective_chat_active_target", None) == name:
                self._detective_chat_active_target = None
            if getattr(self, "_detective_chat_pending_target", None) == name:
                self._detective_chat_pending_target = None

    def _enqueue_speech_job(self, job_id: str, priority: int, func) -> None:
        with self._lock:
            self._speech_queue_seq += 1
            self._speech_queue.append((int(priority), self._speech_queue_seq, str(job_id), func))
            if self._speech_worker_active:
                return
            self._speech_worker_active = True

        def _worker():
            while True:
                with self._lock:
                    if not self._speech_queue:
                        self._speech_worker_active = False
                        return
                    self._speech_queue.sort(key=lambda item: (item[0], item[1]))
                    _, _, _, job = self._speech_queue.pop(0)
                try:
                    job()
                except Exception as exc:
                    print(f"[Speech Queue Error] {exc}", file=sys.stderr, flush=True)

        t = threading.Thread(target=_worker, daemon=True)
        self.llm_threads.append(t)
        t.start()




    def _trigger_npc_to_detective_chat(self, source_name: str, action: str = "",

                                       expected_result: str = "") -> bool:

        """NPC reached Crow by its own action; immediately speak instead of idling."""

        source = self.agents.get(source_name)

        detective = self.agents.get(self.detective_name)

        if not source or not detective or not source.is_alive:

            return False



        # Guard: do not interrupt Crow if already in conversation with another NPC

        if getattr(detective, "in_conversation_with", None) is not None:

            self._log(

                f"[NPC-Crow] {display_name_for_person(source_name)} 想找克罗说话，"

                f"但克罗正在与{display_name_for_person(detective.in_conversation_with)}交谈，暂缓",

                "think",

            )

            return False



        delivered_clues = self._deliver_pending_clues_to_crow(source_name)

        clue_text = "；".join(clue.summary for clue in delivered_clues)

        if clue_text:

            message = f"警长，我有新线索：{clue_text}"

        else:

            base = localize_visible_character_names(action or expected_result or "我有些想法想告诉你。")

            base = re.sub(r"^\s*(我会|我要|我想|准备)?\s*(去)?\s*(找|向)?\s*警长\s*(汇报|说明|报告)?", "", base).strip(" ，。:：")
            if not base:
                base = localize_visible_character_names(expected_result or "我有些情况想告诉你")

            if self._agent_distance(source, detective) <= 1:

                message = base if base.startswith("警长") else f"警长，{base}"

            else:

                message = f"警长，我有想法，但这里不方便细说：{base}"

        message = self._limit_gathering_speech(

            message,

            max_chars=90,

            fallback="警长，我有些情况想告诉你。",

        )



        now = time.time()

        source.in_conversation_with = self.detective_name
        detective.in_conversation_with = source_name

        source._conversation_started_at = now
        detective._conversation_started_at = now
        source.current_thought = ""
        source.current_thought_time = 0
        source.current_action = ""
        source.current_action_type = ""
        source.current_emoji = ""
        source._pending_action = None
        source._last_decision = {}
        source._last_raw_response = ""
        source._is_thinking = False
        source._is_reflecting = False
        self._bump_agent_action_generation(source)
        source.runtime_state = "acting"
        source._report_busy_until = now + float(CONFIG.get("game", {}).get("bubble_lifetime_seconds", 12))
        if not hasattr(source, "action_history") or not isinstance(source.action_history, list):
            source.action_history = []
        source.action_history.append({
            "action_type": "report_to_detective",
            "location": getattr(source, "current_location", ""),
            "action": action,
            "expected_result": expected_result,
            "message": message,
            "time": now,
        })
        if len(source.action_history) > 10:
            source.action_history = source.action_history[-10:]

        self.chat_bubbles[source_name] = {

            "text": message,

            "target": self.detective_name,

            "time": now,

        }

        self._log(f"💬 [主动汇报] {display_name_for_person(source_name)} 对克罗说：{message}", "chat")

        source.add_memory(f"我主动向警长克罗说明：{message}", self.day)
        self._record_observation_event(
            event_type="speech",
            subject=source_name,
            text=f"{display_name_for_person(source_name)}对{display_name_for_person(self.detective_name)}说：{message[:120]}",
            x=source.x,
            y=source.y,
            witnesses={source_name, self.detective_name},
        )
        self._enqueue_memory_task(
            source_name,
            {
                "kind": "conversation_completed",
                "speaker": source_name,
                "listener": self.detective_name,
                "transcript": [(source_name, message)],
                "day": self.day,
                "game_hour": self.game_hour,
            },
        )
        return True





    def detective_chat(self, target_name: str, message: str, is_deep_dive: bool = False) -> dict:

        """返回 {response, remaining_chats, deep_dive_remaining} 或 {error}





        Rules:

        - Normal chat: once per NPC per day, counts as daily interview.

        - Deep dive: only available after normal talk with that NPC AND global deep-dive quota > 0.

          Deep dives do NOT count as daily interview if the normal interview was not yet done.

        - Jailed NPCs cannot be chatted with.

        """

        should_broadcast_start = False

        with self._lock:

            detective = self.agents[self.detective_name]

            target = self.agents.get(target_name)



            if not target or not target.is_alive:

                return {"error": f"{target_name} 不存在或已死亡"}



            if target_name in self._jailed:

                return {"error": f"{display_name_for_person(target_name)} 已被拘留，无法交谈"}



            # Deep dive gating: must have had normal chat with this NPC today first

            if is_deep_dive:

                if target_name not in self._daily_interviewed:

                    return {"error": f"必须先进行正常采访才能对{display_name_for_person(target_name)}进行深度追问"}



            if not detective.can_chat_with(target_name, is_deep_dive):

                return {"error": f"与{target_name}的对话次数已用完"}



            active_target = getattr(self, "_detective_chat_active_target", None)

            if active_target and active_target != target_name:
                return {"error": f"警长正在与{display_name_for_person(active_target)}交谈，请稍后"}


            # 对话轮数上限检查

            if not hasattr(self, '_chat_round_count'):

                self._chat_round_count = {}

            key = (self.detective_name, target_name)

            self._chat_round_count[key] = self._chat_round_count.get(key, 0) + 1

            max_rounds = CONFIG["conversation"]["max_rounds_per_side"]

            if self._chat_round_count[key] > max_rounds:

                return {"error": f"与{target_name}的对话轮数已达上限({max_rounds}轮)"}



            # 警长问话优先：打断目标NPC当前的居民闲聊，防止迟到回复污染状态。

            self._interrupt_agent_conversation(target_name)

            target = self.agents[target_name]

            self._detective_chat_job_id += 1

            chat_job_id = self._detective_chat_job_id
            self._detective_chat_active_target = target_name
            self._detective_chat_pending_target = None


            # 锁定目标 NPC 的对话状态

            target.in_conversation_with = self.detective_name

            target._conversation_started_at = time.time()
            target.target_x = target.x
            target.target_y = target.y
            target.runtime_state = "acting"
            self._bump_agent_action_generation(target)
            target.current_thought = ""
            target.current_thought_time = 0
            target.current_action = ""
            target.current_action_type = ""
            target._pending_action = None
            target._last_decision = {}
            target._last_raw_response = ""
            target._is_thinking = False
            self.agent_paths.pop(target_name, None)
            self._clear_action_status_bubble(target_name)

            detective.in_conversation_with = None

            detective._conversation_started_at = 0



            incoming_message = str(message or "").strip()

            npc_opening_chat = not is_deep_dive

            fixed_detective_question = (

                "我得把昨晚的时间线核清楚。你说说，为什么你不可能是凶手？"

                "另外，现在你最不放心谁，为什么？"

            )

            if npc_opening_chat:

                incoming_message = fixed_detective_question

            prompt_message = incoming_message

            if npc_opening_chat:

                prompt_message = (

                    "警长已经来到你面前。请你主动向警长说明昨晚的行踪、"

                    "你知道的线索或当前怀疑。语气严肃，100字以内。"

                )



            if npc_opening_chat:

                prompt_message = (

                    f"警长克罗当面对你说：{fixed_detective_question}\n"

                    "请直接回答这两个问题：一是你为什么不可能是凶手，二是你目前怀疑谁以及原因。"

                    "语气要像真实小镇居民，紧张、克制，不要开心，不要聊无关人物。100字以内。"

                )



            # 玩家交互先落账，不能等模型返回；迟到/失败回复只影响NPC回答，不回滚玩家动作。

            detective.record_chat(target_name, is_deep_dive)

            if target_name != self.detective_name:

                if not is_deep_dive:

                    self._daily_interviewed.add(target_name)

                if self.detective_name not in self._daily_normal_chats:

                    self._daily_normal_chats[self.detective_name] = set()

                self._daily_normal_chats[self.detective_name].add(target_name)



            self.chat_bubbles[self.detective_name] = {

                "text": self._limit_gathering_speech(incoming_message, max_chars=84),

                "target": target_name,

                "time": time.time(),

            }

            self.chat_bubbles[target_name] = {
                "text": "...",
                "target": self.detective_name,
                "time": time.time(),
            }

            should_broadcast_start = True



        if should_broadcast_start:

            self._broadcast_state()



        # Call the LLM without holding the game engine lock

        response = self._generate_agent_response(

            target,

            self.detective_name,

            prompt_message,

            self.day,

            priority=True,

            max_retries=0,

        )



        with self._lock:

            if (

                getattr(self, "_detective_chat_job_id", 0) != chat_job_id

                or getattr(self, "_detective_chat_active_target", None) != target_name

            ):

                return {"error": "这次回复已经过期"}



            # Re-verify target status after releasing the lock
            if target_name not in self.agents or not self.agents[target_name].is_alive:
                if target_name in self.agents:
                    self.agents[target_name].in_conversation_with = None
                self._detective_chat_active_target = None
                self._detective_chat_pending_target = None
                detective.in_conversation_with = None
                return {"error": f"{target_name} 已死亡，无法继续对话"}


            if not response or not response.strip():
                self._log(
                    f"[模型超时/空结果，保持等待] {display_name_for_person(target_name)} 回复警长",
                    "system",
                )
                self.chat_bubbles[target_name] = {
                    "text": "...",
                    "target": self.detective_name,
                    "time": time.time(),
                }
                self.chat_bubbles[self.detective_name] = {
                    "text": self._limit_gathering_speech(incoming_message, max_chars=84),
                    "target": target_name,
                    "time": time.time(),
                }
                self._broadcast_state()
                return {
                    "pending_response": True,
                    "response": "...",
                    "remaining_chats": CONFIG["conversation"]["detective_normal_chat_limit"]
                    - detective.chat_count.get(target_name, 0),
                    "deep_dive_remaining": detective.deep_dive_quota - detective.deep_dive_used,
                    "delivered_clues": [],
                }
            delivered_clues = self._deliver_pending_clues_to_crow(target_name)

            if delivered_clues:

                clue_text = "\n".join(f"- {clue.summary}" for clue in delivered_clues)

                response = f"{response}\n\n[New factual clues]\n{clue_text}"

            if hasattr(target, "record_dialogue"):

                target.record_dialogue(self.detective_name, incoming_message, response, self.day)

            if hasattr(detective, "record_dialogue"):

                detective.record_dialogue(target_name, incoming_message, response, self.day)

            target.add_memory(

                f"与克罗对话 - 克罗问：{incoming_message[:100]} | 我回答：{response[:120]}",

                self.day,

            )

            if npc_opening_chat:

                detective.add_memory(

                    f"与{target_name}对话 - 对方主动说明：{response[:140]}", self.day

                )

            else:

                detective.add_memory(

                    f"与{target_name}对话 - 我问：{incoming_message[:100]} | 对方答：{response[:100]}", self.day

                )

            self._record_observation_event(
                event_type="speech",
                subject=self.detective_name,
                text=f"{display_name_for_person(self.detective_name)}问{display_name_for_person(target_name)}：{incoming_message[:120]}",
                x=detective.x,
                y=detective.y,
                witnesses={self.detective_name, target_name},
            )
            self._record_observation_event(
                event_type="speech",
                subject=target_name,
                text=f"{display_name_for_person(target_name)}回答{display_name_for_person(self.detective_name)}：{response[:120]}",
                x=target.x,
                y=target.y,
                witnesses={self.detective_name, target_name},
            )
            self._enqueue_conversation_memory(
                self.detective_name,
                target_name,
                [(self.detective_name, incoming_message), (target_name, response)],
            )



            # 清除NPC的思考/行动状态，避免回复后残留蓝泡泡状态；对话锁等白色气泡过期时释放。

            target.current_thought = ""

            target.current_thought_time = 0

            target.current_action = ""

            target.current_action_type = ""

            target._pending_action = None

            target._last_decision = {}

            target._last_raw_response = ""

            target._is_thinking = False

            target._is_reflecting = False

            # 同时也清除侦探的思考/行动状态

            detective.current_thought = ""

            detective.current_thought_time = 0

            detective._is_thinking = False

            detective._is_reflecting = False

            self.chat_bubbles[target_name] = {

                "text": self._limit_gathering_speech(response, max_chars=84),

                "target": self.detective_name,

                "time": time.time(),

            }

            self.chat_bubbles[self.detective_name] = {

                "text": self._limit_gathering_speech(incoming_message, max_chars=84),

                "target": target_name,

                "time": time.time(),

            }



            if npc_opening_chat:

                self._log(f"💬 {target_name} 主动向 {self.detective_name} 说明情况", "chat")

            else:

                self._log(f"💬 {self.detective_name} -> {target_name}: {incoming_message[:100]}", "chat")

            self._log(f"💬 {target_name}: {response[:100]}", "chat")



            return {

                "response": response,

                "remaining_chats": CONFIG["conversation"]["detective_normal_chat_limit"]

                - detective.chat_count.get(target_name, 0),

                "deep_dive_remaining": detective.deep_dive_quota - detective.deep_dive_used,

                "delivered_clues": [clue.summary for clue in delivered_clues],

            }



    def detective_announce(self, werewolf_guess: str) -> dict:

        """返回 {is_correct, werewolf_name, winner}"""

        with self._lock:

            is_correct = self.werewolf_name.lower() in werewolf_guess.lower()

            self.game_over = True

            self.winner = "villagers" if is_correct else "werewolf"

            self._log(f"警长宣布{werewolf_guess}是狼人！{'正确！' if is_correct else '错误！'}", "chat")

            return {

                "is_correct": is_correct,

                "werewolf_name": self.werewolf_name,

                "winner": self.winner,

            }





    # ==================== LLM行为 ====================





    def _llm_tick(self):

        """轮询选一个NPC → reflect → 更新agent → 检查附近NPC触发对话"""

        self.llm_threads = [t for t in self.llm_threads if t.is_alive()]





        alive_npcs = [n for n, a in self.agents.items()

                      if a.is_alive and n != self.detective_name

                      and n not in self._jailed

                      and getattr(a, "in_conversation_with", None) is None]

        if not alive_npcs:

            return





        idx = self.llm_reflect_idx % len(alive_npcs)

        npc_name = alive_npcs[idx]

        npc = self.agents[npc_name]

        if getattr(npc, "_is_reflecting", False):

            started_at = getattr(npc, "_reflect_started_at", time.time())

            stale_timeout = int(CONFIG.get("llm", {}).get("request_timeout_seconds", 60)) + 10

            if time.time() - started_at <= stale_timeout:

                return

            npc._is_reflecting = False





        # 用print直接输出思考开始，不用self._log（避免死锁：_day_tick已在锁内）

        print(f"[Think] {npc_name} 开始思考...", file=sys.stderr, flush=True)

        context = self._build_npc_context(npc_name)

        npc._is_reflecting = True

        npc._reflect_started_at = time.time()





        def _do_reflect():

            try:

                thought = npc.reflect(context)

                if thought:

                    self._log(f"💭 {npc_name}: {thought[:500]}", "think")

                    npc.update_agent(f"反思后更新：{thought[:300]}")

                    self._log(f"🧠 {npc_name} 更新了状态文件 agent.md", "memory")

            except Exception as e:

                print(f"[LLM Reflect Error] {npc_name}: {e}", file=sys.stderr, flush=True)

            finally:

                npc._is_reflecting = False

                npc._reflect_started_at = 0





        t = threading.Thread(target=_do_reflect, daemon=True)

        self.llm_threads.append(t)

        t.start()





        # NPC-NPC chat is now an explicit action decision, not a random proximity side-effect.





    def _build_npc_context(self, name: str) -> str:

        agent = self.agents[name]

        lines = [f"现在是第{self.day}天，游戏时间约{int(self.game_hour)}点。"]





        if agent.current_location:

            lines.append(f"你在{agent.current_location}。")

        if agent.current_action:

            lines.append(f"你正在{agent.current_action}。")





        # 场景物件信息

        scene = get_tile_scene(agent.x, agent.y,

                               self.sector_maze, self.arena_maze, self.go_maze,

                               self.sector_dict, self.arena_dict, self.go_dict)

        if scene["arena"]:

            arena_name = scene["arena"].split(",")[-1].strip()

            if arena_name != scene["sector"]:

                lines.append(f"具体位置：{arena_name}。")

        nearby_objs = get_nearby_objects(agent.x, agent.y, 3,

                                         self.sector_maze, self.arena_maze, self.go_maze,

                                         self.sector_dict, self.arena_dict, self.go_dict)

        if nearby_objs:

            lines.append(f"你看到：{'、'.join(nearby_objs)}。")





        nearby = []

        for other_name, other in self.agents.items():

            if other_name == name or not other.is_alive:

                continue

            if other_name in self._jailed:

                continue

            dist = abs(agent.x - other.x) + abs(agent.y - other.y)

            if dist <= 5:

                nearby.append(f"{other_name}（正在{other.current_action}）")

        if nearby:

            lines.append(f"附近的人：{', '.join(nearby)}。")





        if self.dead_list:

            lines.append(f"已死亡的人：{', '.join(self.dead_list)}。小镇上有狼人！")





        return " ".join(lines)





    def _check_llm_chats(self, npc_name: str):

        # Compatibility shim for older tests/callers. NPC-NPC chats are driven by

        # action_type=talk/socialize decisions and distance checks at execution.

        return

        if getattr(self, "_detective_chat_active_target", None):

            return

        agent = self.agents[npc_name]

        # Jailed NPCs cannot chat

        if npc_name in self._jailed:

            return

        for other_name, other in self.agents.items():

            if other_name == npc_name or not other.is_alive:

                continue

            if other_name == self.detective_name:

                continue

            if other_name in self._jailed:

                continue

            dist = abs(agent.x - other.x) + abs(agent.y - other.y)

            if dist <= 1 and random.random() < 0.8:

                self._trigger_npc_chat(npc_name, other_name)

                break





    def _trigger_npc_chat(self, name1: str, name2: str):

        if name1.lower() == self.detective_name.lower() or name1.lower() == "crow" or name2.lower() == self.detective_name.lower() or name2.lower() == "crow":

            return

        agent1 = self.agents[name1]

        agent2 = self.agents[name2]





        # Lifecycle guard: avoid starting if either participant already in conversation

        with self._lock:

            if getattr(self, "_detective_chat_active_target", None):
                return
            if self._detective_chat_target_reserved(name1) or self._detective_chat_target_reserved(name2):
                return
            if not agent1.is_alive or not agent2.is_alive:
                return
            if self._agent_distance(agent1, agent2) > 2:

                return

            if getattr(agent1, 'in_conversation_with', None) is not None:

                return

            if getattr(agent2, 'in_conversation_with', None) is not None:

                return

            # Clear stale thought/plan for both participants before chat

            agent1.current_thought = ""

            agent1.current_thought_time = 0

            agent1._pending_action = None

            agent1._last_decision = {}

            agent2.current_thought = ""

            agent2.current_thought_time = 0

            agent2._pending_action = None

            agent2._last_decision = {}

            agent1.in_conversation_with = name2

            agent2.in_conversation_with = name1
            self._bump_agent_action_generation(agent1)
            self._bump_agent_action_generation(agent2)
            agent1.runtime_state = "acting"
            agent2.runtime_state = "acting"

            started_at = time.time()

            agent1._conversation_started_at = started_at

            agent2._conversation_started_at = started_at

            chat_key = self._npc_chat_key(name1, name2)

            token = f"{started_at:.6f}:{name1}:{name2}"

            self._npc_chat_tokens[chat_key] = token
            agent1._pending_action = None
            self.chat_bubbles[name1] = {
                "text": "...",
                "target": name2,
                "time": started_at,
                "kind": "conversation_pending",
            }





        def _do_chat():

            try:

                soul1 = agent1.read_soul()

                memory1 = agent1.read_memory()

                cognition1 = agent1.read_cognition()





                role_hint1 = ""

                if agent1.role == "werewolf":

                    role_hint1 = "\n重要：你是狼人！白天伪装成普通居民，绝不暴露身份。"





                system_prompt1 = f"""你是{name1}，主动和{name2}搭话。

你的灵魂：{soul1}{role_hint1}

{active_town_people_rule()}

规则：1. 保持角色性格 2. 自然对话 3. 简短（1-2句话，60-72字左右，完整句可到约75字）"""





                user_prompt1 = f"你的记忆：\n{safe_truncate(memory1, 500)}\n\n你的思考：\n{safe_truncate(cognition1, 300)}\n\n你对{name2}说什么？只输出你的话："





                msg1 = chat_for_agent(name1, system_prompt1, user_prompt1, temperature=0.8)

                with self._lock:

                    if (

                        self._npc_chat_tokens.get(chat_key) != token

                        or getattr(self, "_detective_chat_active_target", None)

                        or getattr(agent1, "in_conversation_with", None) != name2

                        or getattr(agent2, "in_conversation_with", None) != name1

                        or self._agent_distance(agent1, agent2) > 2
                    ):

                        return

                if not msg1:

                    agent1._last_response_error = "empty_response"

                    msg1 = f"（{name1} 想和 {name2} 说话，但还没想好措辞）"

                    self._log(f"[NPC聊天] {name1} 的发言为空，使用可见回退", "system")

                else:

                    agent1._last_response_error = ""





                response2 = agent2.generate_response(name1, msg1, self.day)

                with self._lock:

                    if (

                        self._npc_chat_tokens.get(chat_key) != token

                        or getattr(self, "_detective_chat_active_target", None)

                        or getattr(agent1, "in_conversation_with", None) != name2

                        or getattr(agent2, "in_conversation_with", None) != name1

                        or self._agent_distance(agent1, agent2) > 2
                    ):

                        return

                if not response2:

                    response2 = "我现在还没有想清楚，稍后再和你说。"

                    agent2._last_response_error = "empty_response"





                agent1.add_memory(f"与{name2}闲聊 - 我说：{msg1[:80]} | 对方说：{response2[:80]}", self.day)





                # Sequential bubble pacing: publish initiator bubble first

                with self._lock:

                    if self._npc_chat_tokens.get(chat_key) != token or self._agent_distance(agent1, agent2) > 2:
                        return

                    self.chat_bubbles.pop(name1, None)

                    self.chat_bubbles.pop(name2, None)

                    self.chat_bubbles[name1] = {

                        "text": self._limit_gathering_speech(msg1, max_chars=72),

                        "target": name2,

                        "time": time.time(),

                    }

                self._log(f"💬 {name1}: {msg1[:100]}", "chat")





                # Configurable delay before responder bubble

                npc_chat_delay = float(CONFIG.get("game", {}).get("npc_chat_delay_seconds", 3.0))

                time.sleep(npc_chat_delay)





                with self._lock:

                    if self._npc_chat_tokens.get(chat_key) != token or self._agent_distance(agent1, agent2) > 2:
                        return

                    self.chat_bubbles[name2] = {

                        "text": self._limit_gathering_speech(response2, max_chars=72),

                        "target": name1,

                        "time": time.time(),

                    }

                self._log(f"💬 {name2}: {response2[:100]}", "chat")
                with self._lock:
                    self._record_observation_event(
                        event_type="speech",
                        subject=name1,
                        text=f"{display_name_for_person(name1)}对{display_name_for_person(name2)}说：{msg1[:120]}",
                        x=agent1.x,
                        y=agent1.y,
                        witnesses={name1, name2},
                    )
                    self._record_observation_event(
                        event_type="speech",
                        subject=name2,
                        text=f"{display_name_for_person(name2)}回应{display_name_for_person(name1)}：{response2[:120]}",
                        x=agent2.x,
                        y=agent2.y,
                        witnesses={name1, name2},
                    )
                    self._enqueue_conversation_memory(
                        name1,
                        name2,
                        [(name1, msg1), (name2, response2)],
                    )





            except Exception as e:

                print(f"[LLM Chat Error] {name1}<->{name2}: {e}", file=sys.stderr, flush=True)

            finally:

                with self._lock:

                    if self._npc_chat_tokens.get(chat_key) == token and not self.chat_bubbles.get(name1) and not self.chat_bubbles.get(name2):

                        self._release_conversation_for_expired_bubble(name1, {"target": name2})





        self._enqueue_speech_job(chat_key, 1, _do_chat)





    # ==================== 状态查询（线程安全）====================





    def _body_status(self, body: BodyRecord) -> dict:

        status = body.to_status()

        status["victim_display_name"] = display_name_for_person(body.victim_name)

        status["location_label"] = self._destination_label_zh(body.location)

        return status

    def _public_night_progress_status(self) -> dict:
        """Return only anonymous night-stage data safe for the frontend."""
        progress = dict(getattr(self, "_night_progress", {}) or {})
        stage = str(progress.get("stage") or "werewolf")
        now = time.time()
        if stage == "silver_knife":
            started_at = getattr(self, "_silver_knife_phase_started_at", 0.0) or now
            stage_elapsed = max(0, now - started_at)
            stage_duration = getattr(self, "_silver_knife_phase_duration", 60.0)
        elif stage == "complete" or progress.get("complete"):
            stage_elapsed = getattr(self, "_silver_knife_phase_duration", 60.0)
            stage_duration = getattr(self, "_silver_knife_phase_duration", 60.0)
            stage = "complete"
        else:
            night_started_at = getattr(self, "night_start_time", None) or now
            stage_elapsed = max(0, now - night_started_at)
            stage_duration = max(1.0, getattr(self, "night_duration", 300) - getattr(self, "_silver_knife_phase_duration", 60.0))
            stage = "werewolf"
        return {
            "active": bool(progress.get("active", self.phase == GamePhase.NIGHT)),
            "stage": stage,
            "stage_elapsed": round(stage_elapsed),
            "stage_duration": round(max(1.0, stage_duration)),
            "complete": bool(progress.get("complete")),
        }





    def get_status(self) -> dict:

        with self._lock:

            elapsed_day = 0

            elapsed_dusk = 0

            elapsed_night = 0

            if self.phase == GamePhase.DAY and self.day_start_time:

                elapsed_day = time.time() - self.day_start_time

            elif self.phase == GamePhase.DUSK_DISCUSSION and self.dusk_start_time:

                elapsed_dusk = time.time() - self.dusk_start_time

            elif self.phase == GamePhase.NIGHT and self.night_start_time:

                elapsed_night = time.time() - self.night_start_time





            detective = self.agents.get(self.detective_name) if self.detective_name else None

            detective_chat_limit = CONFIG["conversation"]["detective_normal_chat_limit"]

            deep_dive_quota_total = getattr(detective, "deep_dive_quota", 0) if detective else 0

            deep_dive_used = getattr(detective, "deep_dive_used", 0) if detective else 0





            # jailed status for public view

            jailed_list = list(self._jailed)





            persona_data = {}

            for name, agent in self.agents.items():

                display_name = CHARACTER_DISPLAY_NAMES.get(name, name)

                true_role = agent.role

                public_role = "villager" if true_role == "werewolf" else true_role

                is_jailed = name in self._jailed





                # 计算该 NPC 对侦探的对话可用性

                chat_available = False

                deep_dive_available = False

                if detective and name != self.detective_name and agent.is_alive and not is_jailed:

                    chat_count = detective.chat_count.get(name, 0) if hasattr(detective, "chat_count") else 0

                    chat_available = chat_count < detective_chat_limit

                    # Deep dive available only after normal chat done with that NPC AND quota remaining

                    deep_dive_available = (name in self._daily_interviewed) and (deep_dive_used < deep_dive_quota_total)





                pending_action = getattr(agent, '_pending_action', {})

                if not isinstance(pending_action, dict):

                    pending_action = {}

                last_decision = getattr(agent, '_last_decision', {})

                if not isinstance(last_decision, dict):

                    last_decision = {}

                public_last_decision = {

                    key: localize_visible_character_names(value)

                    for key, value in last_decision.items()

                    if key != "raw_response" and isinstance(value, (str, int, float, bool, type(None)))

                }

                scratch_current = ""

                if hasattr(agent, 'scratch') and isinstance(getattr(agent, 'scratch', None), dict):

                    scratch_current = getattr(agent, 'scratch', {}).get("currently", "")

                plan_text = (

                    pending_action.get("expected_result")

                    or last_decision.get("expected_result")

                    or scratch_current

                )

                target_location = pending_action.get("target_location") or last_decision.get("target_location") or agent.current_location

                target_object = pending_action.get("target_object") or last_decision.get("target_object") or ""

                target_person = pending_action.get("target_person") or last_decision.get("target_person") or ""



                is_detective = (name == self.detective_name)
                visual_moving = bool(self.agent_paths.get(name)) or (
                    agent.x != agent.target_x or agent.y != agent.target_y
                ) or getattr(agent, 'runtime_state', 'idle') == "moving"


                display_action = "" if is_detective else self._action_for_display(agent.current_action)

                persona_data[name] = {
                "x": agent.x,

                "y": agent.y,

                "target_x": agent.target_x,

                "target_y": agent.target_y,

                "action": display_action,
                "action_type": "" if is_detective else getattr(agent, 'current_action_type', ''),

                "action_plan": "" if is_detective else localize_visible_character_names(plan_text),

                "action_target_location": "" if is_detective else target_location,

                "action_target_location_label": "" if is_detective else self._destination_label_zh(target_location),

                "action_target_object": "" if is_detective else target_object,

                "action_target_person": "" if is_detective else target_person,

                "emoji": "" if is_detective else agent.current_emoji,

                "location": agent.current_location,

                "location_label": self._destination_label_zh(agent.current_location),

                "display_name": display_name,

                "alive": agent.is_alive,

                "model": getattr(self, "model_assignments", {}).get(name, getattr(agent, 'model', '')),

                "role": public_role,

                "public_role": public_role,

                "true_role": true_role,

                "has_new_clue": self._agent_has_visible_clue_hint(name, agent),
                "has_visible_clue_hint": self._agent_has_visible_clue_hint(name, agent),
                "has_detective_hint": self._agent_has_visible_clue_hint(name, agent),

                "thought": "" if is_detective else getattr(agent, 'current_thought', ''),

                "thought_time": 0 if is_detective else getattr(agent, 'current_thought_time', 0),

                "thought_summary": "" if is_detective else self._summarize_thought_for_display(

                    getattr(agent, 'current_thought', '')

                ),

                # Crow is player-controlled. The UI may still use path/runtime

                # state to infer a blue thought/action bubble, so public status

                # must expose him as idle even while the backend pathfinder moves

                # him. His visible feedback is handled only by white speech bubbles.

                "path_len": 0 if is_detective else len(self.agent_paths.get(name, [])),

                "runtime_state": "idle" if is_detective else getattr(agent, 'runtime_state', 'idle'),
                "visual_moving": visual_moving,
                "action_started_at": 0 if is_detective else getattr(agent, "_action_started_at", 0),
                "action_status_visible_at": 0 if is_detective else getattr(agent, "_action_status_visible_at", 0),
                "departure_delay_until": 0 if is_detective else getattr(agent, "_departure_delay_until", 0),
                "last_decision": {} if is_detective else public_last_decision,

                "last_error": "" if is_detective else localize_visible_character_names(last_decision.get("error", "")),

                "llm_error": "" if is_detective else get_last_error_for_agent(name),

                "response_error": "" if is_detective else getattr(agent, '_last_response_error', ''),

                "current_goal": "" if is_detective else scratch_current,

                "conversation_with": None if is_detective else getattr(agent, "in_conversation_with", None),

                "chat_available": chat_available,

                "deep_dive_available": deep_dive_available,

                "jailed": is_jailed,

                "prison_cell": self._get_prison_cell(name) if is_jailed else None,

            }

                if is_detective:

                    persona_data[name].update({

                        "action": "",

                        "action_type": "",

                        "action_plan": "",

                        "action_target_location": "",

                        "action_target_location_label": "",

                        "action_target_object": "",

                        "action_target_person": "",

                        "emoji": "",

                        "thought": "",

                        "thought_time": 0,

                        "thought_summary": "",

                        "path_len": 0,

                        "runtime_state": "idle",

                        "last_decision": {},

                        "last_error": "",

                        "response_error": "",

                        "current_goal": "",

                        "conversation_with": None,

                    })





            now = time.time()

            bubble_lifetime = float(CONFIG.get("game", {}).get("bubble_lifetime_seconds", 12))

            expired = [k for k, v in self.chat_bubbles.items() if now - v["time"] > bubble_lifetime]

            for k in expired:

                bubble = self.chat_bubbles.pop(k, None)
                if bubble is not None:
                    self._release_conversation_for_expired_bubble(k, bubble)





            gather_site = {

                "x": INITIAL_BODY_SITE["x"],

                "y": INITIAL_BODY_SITE["y"],

                "location": INITIAL_BODY_SITE["location"],

            }

            if hasattr(self, "bodies") and self.bodies:

                discovered_bodies = [b for b in self.bodies if getattr(b, "discovered", False)]

                if discovered_bodies:

                    latest_body = max(discovered_bodies, key=lambda b: getattr(b, "created_day", 0))

                    gather_site = {

                        "x": latest_body.x,

                        "y": latest_body.y,

                        "location": latest_body.location,

                    }

            hunt = getattr(self, "night_hunt", None)

            hunt_status = {}

            if hunt:

                hunt_status = {

                    "stage": hunt.stage,

                    "target_name": hunt.target_name,

                    "target_changes": list(hunt.target_changes),

                    "witnessed_by": sorted(hunt.witnessed_by),

                    "killed_name": hunt.killed_name,

                    "withdrawal_complete": hunt.withdrawal_complete,

                    "forced_completion": hunt.forced_completion,

                }





            # 每日 NPC 采访总数（排除 Crow 自己，排除 jailed）

            daily_interview_total = len([n for n, a in self.agents.items()

                                         if n != self.detective_name and a.is_alive and n not in self._jailed])

            daily_interview_count = len(self._daily_interviewed & set(self.agents.keys()))





            # Build daily tasks list

            daily_tasks = self._build_daily_tasks()





            # Check if dusk can start

            can_dusk, dusk_block_reason = self.can_start_dusk_discussion()





            # Build vote summary for dusk

            vote_summary = self._build_vote_summary() if self.phase == GamePhase.DUSK_DISCUSSION else None





            # 主 CTA 提示

            primary_cta = None

            if self.phase == GamePhase.DAY:

                if getattr(self, '_gathering_active', False):

                    primary_cta = "gathering"  # 聚集讨论进行中

                elif not can_dusk:

                    primary_cta = "interviews"  # 还需要采访才能开始黄昏

                else:

                    primary_cta = "dusk_discussion"  # 默认：开始黄昏讨论

            elif self.phase == GamePhase.DUSK_DISCUSSION:

                if getattr(self, "_dusk_stage", "") == "escorting":

                    primary_cta = None

                elif self._dusk_vote_active and self._dusk_jail_target is None:

                    primary_cta = "jail_choice"  # 等待玩家选择拘留目标

                else:

                    primary_cta = "vote_accuse"  # 投票/指控

            elif self.phase == GamePhase.PENDING_SILVER_SHOT:

                primary_cta = "silver_shot"





            recent_log = []
            for entry in list(self.game_log[-100:]):
                if not self._is_player_visible_log_entry(entry):
                    continue
                item = dict(entry)
                item["message"] = localize_visible_character_names(item.get("message", ""))
                recent_log.append(item)

            return {
                "director_view": True,
                "observation_mode": True,

                "day": self.day,

                "phase": self.phase.value,

                "game_hour": round(self.game_hour, 1),

                "day_elapsed": round(elapsed_day),

                "day_duration": getattr(self, "day_duration", 1800),

                "dusk_elapsed": round(elapsed_dusk),

                "dusk_duration": getattr(self, "dusk_duration", 600),

                "night_elapsed": round(elapsed_night),

                "night_duration": getattr(self, "night_duration", 300),

                "day_time_expired": getattr(self, "day_time_expired", False),

                "personas": persona_data,

                "dead": self.dead_list,

                "jailed": jailed_list,

                "chat_bubbles": dict(self.chat_bubbles),

                "detective_chats": dict(self.agents[self.detective_name].chat_count) if self.detective_name in self.agents and hasattr(self.agents[self.detective_name], "chat_count") else {},

                "deep_dive_quota": getattr(self.agents[self.detective_name], "deep_dive_quota", {}) if self.detective_name in self.agents else {},

                "deep_dive_remaining": deep_dive_quota_total - deep_dive_used,

                "daily_interview_total": daily_interview_total,

                "daily_interview_count": daily_interview_count,

                "daily_tasks": daily_tasks,

                "can_start_dusk_discussion": can_dusk,

                "dusk_block_reason": dusk_block_reason,

                "vote_summary": vote_summary,
                "vote_history": list(getattr(self, "_vote_history", [])),
                "dusk_votes": vote_summary["votes"] if vote_summary else {},
                "dusk_discussion_active": getattr(self, "_dusk_discussion_active", False),
                "dusk_discussion_statements": list(getattr(self, "_dusk_discussion_statements", [])),
                "dusk_crow_statement": getattr(self, "_dusk_crow_statement", ""),
                "silver_bullet_acquired": self._silver_bullet_acquired,
                "silver_jewelry_acquired": self._silver_jewelry_acquired,

                "silver_bullet_crafted": self._silver_bullet_crafted,

                "silver_bullet_used": self._silver_bullet_used,

                "night_progress": self._public_night_progress_status(),
                "pending_silver_shot": self.phase == GamePhase.PENDING_SILVER_SHOT,
                "silver_shot_available": (
                    self.phase == GamePhase.PENDING_SILVER_SHOT
                    and self._silver_bullet_crafted
                    and not self._silver_bullet_used
                ),
                "day4_no_free_activity": getattr(self, "_day4_no_free_activity", False),
                "primary_cta": primary_cta,

                "bodies": [self._body_status(b) for b in getattr(self, "bodies", []) if not getattr(b, "buried", False)],

                "werewolf_name": getattr(self, "werewolf_name", ""),

                "werewolf_names": list(getattr(self, "werewolf_names", [])),

                "model_assignments": getattr(self, "model_assignments", {}),

                "llm_provider": getattr(self, "llm_provider", {"provider": "chat2api"}),

                "gathering_site": gather_site,

                "night_hunt": hunt_status,

                "recent_log": recent_log,
            }
