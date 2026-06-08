"""Dusk discussion, voting, and prison helpers for WerewolfGameEngine."""

import threading
import time
import sys

from llm import chat_for_agent
from world_config import (
    ACTIVE_CHARACTERS,
    CHARACTER_DISPLAY_NAMES,
    INITIAL_BODY_SITE,
    SHERIFF_AREA,
    display_name_for_person,
)

# Day 1 fixed knowledge revelation text (spec section 3)
_DAY1_KNOWLEDGE_TEXT = (
    "我查过尸体咬痕、抓痕和旧资料，可以确定这不是野兽，是狼人。"
    "狼人白天像普通人，也能被制服；夜里会变成狼首怪物，力量和攻击性都很强。"
    "伤口显示凶手可能不止一个，大家今晚尽量待在室内，黄昏投票一定要认真判断、互相核对。"
)

# Voting countdown in seconds
_VOTE_COUNTDOWN_SECONDS = 30

_CROW_GATHERING_TEXT = "黄昏到了，大家一起到广场集合。"
_CROW_DISCUSSION_TEXT = (
    "既然这样，大家就按顺序说说今天的观察，各自证明一下自己为什么不是狼人。"
    "你怀疑谁、看见了什么异常，也都可以说出来。等一圈发言结束后我们进行投票；"
    "怀疑谁就投谁，不确定也可以弃票，得票最高的人我会先暂时关进牢房。"
)
_CROW_START_VOTE_TEXT = "现在开始投票。"
_DUSK_FINAL_WORDS_HOLD_SECONDS = 6.0
_DUSK_SPEAKER_HOLD_SECONDS = 3.0

_DUSK_FILLER_PATTERNS = (
    "我没意见",
    "没有意见",
    "先听警长",
    "先听克罗",
    "听听警长",
    "听听克罗",
    "等大家说完",
    "等别人说",
    "暂时没有线索",
    "没有线索",
    "不好说",
    "不确定",
)

_DUSK_VOTE_OPENING_HOLD_SECONDS = 3.0


def active_town_people_rule() -> str:
    people = "、".join(display_name_for_person(name) for name in ACTIVE_CHARACTERS.keys())
    return (
        "人物边界：这个小镇当前只有以下8个可行动人物："
        f"{people}。所有对外发言只能使用这些中文名字，不要说英文名、全名或内部代号。"
        "不得编造、提及或引用名单外的人名；如果需要说“其他人”，"
        "只能说“其他镇民/路人”，不要给他们起名字。"
    )


def _chat_for_agent(*args, **kwargs):
    """Honor the legacy game_engine.chat_for_agent patch point."""
    game_engine_module = sys.modules.get("game_engine")
    runtime_chat = getattr(game_engine_module, "chat_for_agent", chat_for_agent)
    return runtime_chat(*args, **kwargs)


def _is_dusk_filler_statement(text: str) -> bool:
    """Return True for low-information dusk speeches that dodge discussion."""
    compact = "".join(str(text or "").split())
    if not compact:
        return True
    return any(pattern in compact for pattern in _DUSK_FILLER_PATTERNS)


class EngineDuskMixin:
    def _dusk_tick(self):
        """黄昏讨论阶段：移动 NPC，检查投票倒计时，超时自动解决投票并进入夜晚"""
        self._move_agents()
        elapsed = time.time() - (self.dusk_start_time or time.time())

        if getattr(self, "_dusk_stage", "") == "gathering":
            participants = self._eligible_dusk_participants()
            if self._all_dusk_participants_arrived(participants):
                self._begin_dusk_discussion_after_gathering()
            return

        if getattr(self, "_dusk_stage", "") == "escorting":
            crow = self.agents.get(self.detective_name)
            target_name = getattr(self, "_dusk_jail_target", None)
            target = self.agents.get(target_name) if target_name else None
            target_arrived = (
                not target
                or (target.x, target.y) == (target.target_x, target.target_y)
            )
            if crow and target_arrived and (crow.x, crow.y) == (crow.target_x, crow.target_y):
                self._transition_to_night()
            return

        # Phase-level timeout: if dusk exceeds dusk_duration, force transition
        if elapsed >= self.dusk_duration:
            self._log("⏰ 黄昏讨论时间到，自动进入夜晚...", "system")
            if not getattr(self, "_dusk_vote_resolved", False) and self._dusk_vote_active:
                self._finalize_missing_dusk_votes_as_abstain()
                self._resolve_dusk_votes()
            elif getattr(self, "_dusk_stage", "") == "results":
                self.confirm_vote_result()
            else:
                self._transition_to_night()
            return

        # Voting countdown: if vote is active and deadline passed, auto-resolve.
        # If everyone has voted earlier, resolve immediately.
        if (self._dusk_vote_active
                and not getattr(self, "_dusk_vote_resolved", False)
                and self._dusk_jail_target is None
                and self._dusk_vote_deadline is not None):
            if self._all_dusk_votes_collected():
                self._log("🗳️ 全员投票完成，立即结算。", "system")
                self._resolve_dusk_votes()
            elif time.time() >= self._dusk_vote_deadline:
                self._log("⏰ 投票时间到！未投票者按弃票处理。", "system")
                self._finalize_missing_dusk_votes_as_abstain()
                self._resolve_dusk_votes()


    # ==================== 昼夜转换（线程安全，都加锁）====================


    def can_start_dusk_discussion(self) -> tuple[bool, str]:
        """Check if dusk discussion can start. Returns (ok, reason).
        Gates:
        - Day 1: all living non-jailed non-Crow residents must be interviewed (normal chat) at least once.
        - Every day: same interview requirement.
        - Also checks that phase is DAY and gathering is not active.
        """
        if self.phase != type(self.phase).DAY:
            return False, "Not in DAY phase"
        if getattr(self, '_gathering_active', False):
            return False, "Morning gathering still in progress"
        # Compute required interviews: all living, non-jailed, non-Crow residents
        required = {n for n, a in self.agents.items()
                    if n != self.detective_name and a.is_alive and n not in self._jailed}
        missing = required - self._daily_interviewed
        if missing:
            missing_names = "、".join(display_name_for_person(n) for n in sorted(missing))
            return False, f"还需要采访: {missing_names}"
        return True, "OK"

    def mark_all_daily_interviews_for_test(self) -> dict:
        """Development-only shortcut: mark today's required interviews complete."""
        required = {
            name for name, agent in self.agents.items()
            if name != self.detective_name and agent.is_alive and name not in self._jailed
        }
        self._daily_interviewed.update(required)
        self._daily_normal_chats.setdefault(self.detective_name, set()).update(required)
        self._log("🧪 测试按钮：已将今日所有居民标记为已交谈。", "system")
        return {
            "success": True,
            "count": len(required),
            "total": len(required),
        }


    def start_dusk_discussion(self):
        """玩家触发黄昏讨论阶段：投票/指控环节，不立即进入夜晚。
        黄昏讨论中 NPC 会投票指控，然后玩家选择谁被 Crow 拘留。"""
        with self._lock:
            ok, reason = self.can_start_dusk_discussion()
            if not ok:
                self._log(f"⚠️ 无法开始黄昏讨论: {reason}", "system")
                return False
            self._transition_to_dusk()
            return True


    def _transition_to_dusk(self):
        """Enter dusk and gather everyone before any discussion starts."""
        self.phase = type(self.phase).DUSK_DISCUSSION
        self.dusk_start_time = time.time()
        self._dusk_votes = {}
        self._dusk_vote_reasons = {}
        self._dusk_vote_active = False
        self._dusk_discussion_active = True
        self._dusk_discussion_statements = []
        self._dusk_crow_statement = ""
        self._dusk_jail_target = None
        self._dusk_crow_voted = False
        self._dusk_vote_deadline = None
        self._dusk_vote_resolved = False
        self._dusk_stage = "gathering"
        self._dusk_winner = None
        self._dusk_result_note = ""
        self._dusk_discussion_thread = None
        participants = self._eligible_dusk_participants()
        self._clear_daytime_state_for_dusk(participants)
        self._log("🌅 黄昏降临，居民们聚集讨论今天的发现...", "action")
        self.chat_bubbles[self.detective_name] = {
            "text": _CROW_GATHERING_TEXT,
            "target": "",
            "time": time.time(),
        }
        self._send_dusk_participants_to_plaza(participants)
        self._broadcast_state()

    def _eligible_dusk_participants(self) -> list[str]:
        return [
            name for name, agent in self.agents.items()
            if agent.is_alive and name not in self._jailed
        ]

    def _clear_daytime_state_for_dusk(self, participants: list[str]) -> None:
        """Clear stale daytime NPC runtime state before assigning dusk gathering."""
        participant_set = set(participants)
        self.chat_bubbles.clear()
        self._detective_chat_active_target = None
        self._detective_chat_pending_target = None
        for name, agent in self.agents.items():
            agent.in_conversation_with = None
            agent._conversation_started_at = 0
            if name == self.detective_name or name not in participant_set:
                continue
            agent.current_thought = ""
            agent.current_thought_time = 0
            agent.current_action = ""
            agent.current_action_type = ""
            agent.current_emoji = ""
            agent.runtime_state = "idle"
            agent._pending_action = None
            agent._is_thinking = False
            agent._is_reflecting = False
            agent._action_status_visible_at = 0
            agent._action_start_visible_until = 0
            agent._action_move_ready_at = 0
            # Bump generation to cancel any stale daytime LLM decisions still in-flight
            self._bump_agent_action_generation(agent)
            self.agent_paths.pop(name, None)

    def _send_dusk_participants_to_plaza(self, participants: list[str] | None = None) -> None:
        """Reuse the morning plaza ring and make all eligible participants walk there."""
        import math

        participants = participants or self._eligible_dusk_participants()
        if not participants:
            return
        center_x = INITIAL_BODY_SITE["x"]
        center_y = INITIAL_BODY_SITE["y"]
        radius = 7
        participant_set = set(participants)
        blocked_base = self._occupied_tiles(participant_set)
        reserved_targets = set()
        for idx, name in enumerate(participants):
            desired = (
                round(center_x + radius * math.cos(idx * 2 * math.pi / len(participants))),
                round(center_y + radius * math.sin(idx * 2 * math.pi / len(participants))),
            )
            target = self._nearest_walkable_tile(
                desired,
                radius=6,
                blocked=blocked_base | reserved_targets,
            ) or desired
            reserved_targets.add(target)
            agent = self.agents[name]
            blocked_tiles = (blocked_base | reserved_targets) - {target}
            path_result = self._nearest_reachable_path(
                (agent.x, agent.y),
                target,
                radius=10,
                blocked=blocked_tiles,
            )
            if path_result:
                target_x, target_y, path = path_result
                agent.target_x, agent.target_y = target_x, target_y
                if path:
                    self.agent_paths[name] = path
                else:
                    self.agent_paths.pop(name, None)
                reserved_targets.discard(target)
                reserved_targets.add((target_x, target_y))
            else:
                agent.target_x, agent.target_y = target
                self.agent_paths.pop(name, None)
            agent.current_location = INITIAL_BODY_SITE["location"]
            agent.current_action = "前往广场参加黄昏讨论"
            agent.current_emoji = "🚶"
            agent.runtime_state = "moving" if (agent.x, agent.y) != (agent.target_x, agent.target_y) else "idle"
            if self.agent_paths.get(name):
                agent.runtime_state = "moving"

    def _all_dusk_participants_arrived(self, participants: list[str] | None = None) -> bool:
        participants = participants or self._eligible_dusk_participants()
        for name in participants:
            agent = self.agents.get(name)
            if not agent or not agent.is_alive:
                continue
            if self.agent_paths.get(name):
                return False
            if (agent.x, agent.y) != (agent.target_x, agent.target_y):
                return False
        return True

    def _freeze_dusk_participants(self, participants: list[str] | None = None) -> None:
        participants = participants or self._eligible_dusk_participants()
        for name in participants:
            agent = self.agents.get(name)
            if not agent:
                continue
            self.agent_paths.pop(name, None)
            agent.target_x, agent.target_y = agent.x, agent.y
            agent.current_action = "参加黄昏讨论"
            agent.current_emoji = "💬"
            agent.runtime_state = "idle"
            agent._pending_action = None
            agent.current_thought = ""
            agent.current_thought_time = 0
            agent._is_thinking = False
            agent._is_reflecting = False
            # Bump generation so any still-in-flight daytime LLM decision is rejected
            self._bump_agent_action_generation(agent)

    def _begin_dusk_discussion_after_gathering(self) -> None:
        if getattr(self, "_dusk_stage", "") != "gathering":
            return
        participants = self._eligible_dusk_participants()
        if not self._all_dusk_participants_arrived(participants):
            return
        self._freeze_dusk_participants(participants)
        self._dusk_stage = "knowledge_reveal"
        if self.day == 1:
            self._reveal_day1_werewolf_knowledge()
            self._pause_for_dusk_bubble()
        self.chat_bubbles[self.detective_name] = {
            "text": _CROW_DISCUSSION_TEXT,
            "target": "",
            "time": time.time(),
        }
        self._log(f"💬 克罗（黄昏主持）: {_CROW_DISCUSSION_TEXT}", "chat")
        self._broadcast_state()
        self._pause_for_dusk_bubble()
        self._dusk_stage = "npc_discussion"
        if getattr(self, "_running", False):
            worker = getattr(self, "_dusk_discussion_thread", None)
            if worker and worker.is_alive():
                return
            self._dusk_discussion_thread = threading.Thread(
                target=self._finish_dusk_discussion_sequence,
                daemon=True,
            )
            self._dusk_discussion_thread.start()
            self._broadcast_state()
            return
        self._finish_dusk_discussion_sequence()

    def _finish_dusk_discussion_sequence(self) -> None:
        self._generate_dusk_discussion_statements()
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                return
            if getattr(self, "_dusk_stage", "") not in {"npc_discussion", "discussion"}:
                return
            for name in list(self.chat_bubbles.keys()):
                if name != self.detective_name:
                    self.chat_bubbles.pop(name, None)
            self._dusk_stage = "crow_statement"
            self._log("请克罗总结发言。克罗发言后，居民再进入投票。", "system")
            self._broadcast_state()

    def _pause_for_dusk_bubble(self) -> None:
        """Keep fixed sequence bubbles readable in the live game without slowing unit tests."""
        if getattr(self, "_running", False):
            time.sleep(6.0)

    def _pause_for_dusk_final_words(self) -> None:
        """Keep the jailed target's final words readable before escorting."""
        if getattr(self, "_running", False):
            time.sleep(_DUSK_FINAL_WORDS_HOLD_SECONDS)

    # ==================== Day 1 knowledge revelation ====================

    def _get_plaza_clockwise_order(self) -> list[str]:
        """Return eligible speakers sorted clockwise from Crow's left, around plaza center."""
        eligible = [
            n for n, a in self.agents.items()
            if n != self.detective_name and a.is_alive and n not in self._jailed
        ]
        if not eligible:
            return []
        center_x = INITIAL_BODY_SITE["x"]
        center_y = INITIAL_BODY_SITE["y"]
        import math

        crow = self.agents.get(self.detective_name)
        if not crow:
            return eligible
        crow_angle = math.atan2(crow.y - center_y, crow.x - center_x)

        def clockwise_delta_from_crow_left(name):
            agent = self.agents[name]
            angle = math.atan2(agent.y - center_y, agent.x - center_x)
            return (angle - crow_angle + 2 * math.pi) % (2 * math.pi)

        return sorted(eligible, key=clockwise_delta_from_crow_left)

    def _resolve_speaker_for_day1_knowledge(self) -> str:
        """Select speaker for day 1 knowledge: prefer Mei Lin, then Klaus, then any other."""
        preference_order = ["Mei Lin", "Klaus Mueller"]
        for name in preference_order:
            if name in self.agents and self.agents[name].is_alive and name not in self._jailed:
                return name
        # Fall back to any other living non-jailed NPC
        for name, agent in self.agents.items():
            if name != self.detective_name and agent.is_alive and name not in self._jailed:
                return name
        return ""

    def _reveal_day1_werewolf_knowledge(self):
        """Reveal fixed werewolf knowledge on day 1. Speaker identity does not depend on werewolf status."""
        if self.day != 1:
            return
        speaker = self._resolve_speaker_for_day1_knowledge()
        if not speaker:
            return
        disp = display_name_for_person(speaker)
        self.chat_bubbles[speaker] = {
            "text": _DAY1_KNOWLEDGE_TEXT,
            "target": "",
            "time": time.time(),
        }
        self._log(f"💬 {disp}（第1天知识揭露）: {_DAY1_KNOWLEDGE_TEXT}", "chat")
        self._broadcast_state()

    # ==================== Dusk discussion ====================

    def _dusk_discussion_speech_timeout_seconds(self) -> float:
        return 10.0

    def _generate_single_dusk_discussion_statement(
        self,
        speaker_name: str,
        recent_dead: str,
        clue_text: str,
    ) -> str:
        if not getattr(self, "_running", False):
            return ""
        agent = self.agents[speaker_name]
        memory_text = str(agent.read_memory() or "")[-900:]
        cognition_text = str(agent.read_cognition() or "")[-500:]
        possible_suspects = [
            display_name_for_person(name)
            for name, suspect in self.agents.items()
            if name != speaker_name and suspect.is_alive and name not in self._jailed
        ]
        suspect_text = "、".join(possible_suspects) or "暂无其他存活对象"
        role_instruction = (
            "你实际是狼人。发言时必须伪装成好人，自证清白，把怀疑甩给一个具体非狼人对象；"
            "不要承认狼人身份，不要显得在保护同伴。"
            if agent.role == "werewolf"
            else "你是好人。发言时必须自证清白，指出一个具体怀疑对象，并提醒大家下一步该查什么。"
        )
        system_prompt = (
            f"你是{display_name_for_person(speaker_name)}，现在是第{self.day}天黄昏讨论。"
            f"最近死者：{recent_dead}。已知线索：{clue_text}。"
            f"你对白天经历的记忆：{memory_text}。你的当前判断：{cognition_text}。"
            f"可怀疑对象：{suspect_text}。{role_instruction}"
            "发言要像狼人杀讨论：先用自己的行踪/观察/记忆自证，再点名一个具体怀疑对象，"
            "再基于尸体、讨论或公开线索给出推理理由。"
            "禁止说“我没意见”“先听警长/克罗”“等大家说完”“暂时没有线索”等划水句；"
            "不要使用固定格式开头；每个人都要根据自己的职业、记忆和怀疑对象说出不同重点。"
            "不要投票，不要要求马上拘留。80字以内，必须只说角色本人会说的话。"
        )
        result = {"text": ""}

        def _call_model() -> None:
            try:
                result["text"] = _chat_for_agent(
                    speaker_name,
                    system_prompt,
                    "请发表黄昏讨论发言，不要投票。",
                    max_retries=1,
                )
            except Exception:
                result["text"] = ""

        worker = threading.Thread(target=_call_model, daemon=True)
        worker.start()
        worker.join(timeout=self._dusk_discussion_speech_timeout_seconds())
        return str(result.get("text") or "")

    def _generate_dusk_discussion_statements(self):
        """Collect short NPC discussion statements in clockwise plaza order."""
        statements = []
        # Use clockwise order from Crow's left around plaza (spec section 4.3)
        eligible_speakers = self._get_plaza_clockwise_order()
        if not eligible_speakers:
            self._dusk_discussion_statements = statements
            return

        recent_dead = "、".join(display_name_for_person(d) for d in self.dead_list[-3:]) if self.dead_list else "暂无"
        clue_summaries = [c.summary for c in getattr(self, "clues", [])[-5:]]
        clue_text = "；".join(clue_summaries[:3]) if clue_summaries else "暂无明确线索"

        for idx, speaker_name in enumerate(eligible_speakers):
            text = ""
            try:
                text = self._generate_single_dusk_discussion_statement(
                    speaker_name,
                    recent_dead,
                    clue_text,
                )
            except Exception:
                text = ""
            text = str(text or "").strip()
            if _is_dusk_filler_statement(text):
                speaker = self.agents.get(speaker_name)
                location = getattr(speaker, "current_location", "") or "白天所在区域"
                suspect_pool = [
                    name for name, agent in self.agents.items()
                    if name != speaker_name and agent.is_alive and name not in self._jailed
                ]
                if getattr(speaker, "role", "") == "werewolf":
                    suspect_pool = [name for name in suspect_pool if name not in self.werewolf_names] or suspect_pool
                suspect_name = self._rng.choice(suspect_pool) if suspect_pool else ""
                suspect_text = display_name_for_person(suspect_name) if suspect_name else "行踪解释不清的人"
                if getattr(speaker, "role", "") == "werewolf":
                    templates = [
                        f"我白天一直在{location}附近，没机会靠近死者。{suspect_text}一直避开关键问题，我怀疑他在把线索往别人身上推。",
                        f"我能解释自己的去向，反倒是{suspect_text}说话绕来绕去。现在不能再等，他的行踪必须被重点追问。",
                        f"尸体出现后{suspect_text}最急着撇清自己，这不像普通紧张。我建议先盯住他，别被表面的安静骗了。",
                    ]
                else:
                    templates = [
                        f"我白天在{location}，能说明自己见过什么。{suspect_text}的时间线最薄弱，我希望他把去向说完整。",
                        f"我不想空猜，但{suspect_text}和尸体线索对不上。现在要查的是谁能解释行动，谁只是在躲问题。",
                        f"我能说清自己的位置；{suspect_text}还没解释关键空档。大家别只听态度，要看他说法有没有矛盾。",
                    ]
                text = self._rng.choice(templates)
            text = self._limit_gathering_speech(text, max_chars=90)
            statements.append({"speaker": speaker_name, "text": text})
            self.chat_bubbles[speaker_name] = {
                "text": text,
                "target": "",
                "time": time.time(),
            }
            self._log(f"💬 黄昏讨论 {display_name_for_person(speaker_name)}: {text}", "chat")
            self._dusk_discussion_statements = list(statements)
            self._broadcast_state()
            if getattr(self, "_running", False):
                time.sleep(_DUSK_SPEAKER_HOLD_SECONDS)

        self._dusk_discussion_statements = statements


    def submit_dusk_statement(self, statement: str) -> dict:
        """Crow speaks after NPC discussion; only then do residents vote.
        Starts a 30-second countdown for voting (spec section 5.1)."""
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                return {"success": False, "error": "Not in dusk discussion phase"}
            if getattr(self, "_dusk_stage", "") == "gathering":
                participants = self._eligible_dusk_participants()
                if all(
                    (self.agents[name].x, self.agents[name].y)
                    == (self.agents[name].target_x, self.agents[name].target_y)
                    for name in participants
                ):
                    self._begin_dusk_discussion_after_gathering()
            if not getattr(self, "_dusk_discussion_active", False):
                return {"success": False, "error": "Dusk discussion statement already submitted"}
            if getattr(self, "_dusk_stage", "") != "crow_statement":
                return {"success": False, "error": "It is not Crow's turn to speak"}
            text = str(statement or "").strip()
            if not text:
                return {"success": False, "error": "Crow statement is required before voting"}

            text = self._limit_gathering_speech(text, max_chars=120)
            self._dusk_crow_statement = text
            self._dusk_discussion_active = False
            self.chat_bubbles[self.detective_name] = {
                "text": text,
                "target": "",
                "time": time.time(),
            }
            self._log(f"💬 克罗黄昏发言: {text}", "chat")
            self._dusk_stage = "crow_speaking"
            self._dusk_vote_active = False
            self._dusk_vote_deadline = None
            self._dusk_crow_voted = False
            self._broadcast_state()
            if getattr(self, "_running", False):
                threading.Thread(target=self._open_dusk_vote_after_crow_bubble, daemon=True).start()
            else:
                self._open_dusk_vote_after_crow_bubble()
            return {
                "success": True,
                "statement": text,
                "vote_summary": self._build_vote_summary(),
            }


    def _open_dusk_vote_after_crow_bubble(self):
        if getattr(self, "_running", False):
            time.sleep(_DUSK_SPEAKER_HOLD_SECONDS)
        with self._lock:
            if (
                self.phase != type(self.phase).DUSK_DISCUSSION
                or getattr(self, "_dusk_stage", "") != "crow_speaking"
                or self._dusk_jail_target is not None
            ):
                return
            self._dusk_stage = "vote_opening"
            self.chat_bubbles[self.detective_name] = {
                "text": _CROW_START_VOTE_TEXT,
                "target": "",
                "time": time.time(),
            }
            self._log(f"💬 克罗（投票开始）: {_CROW_START_VOTE_TEXT}", "chat")
            self._broadcast_state()
        if getattr(self, "_running", False):
            time.sleep(_DUSK_VOTE_OPENING_HOLD_SECONDS)
        with self._lock:
            if (
                self.phase != type(self.phase).DUSK_DISCUSSION
                or getattr(self, "_dusk_stage", "") != "vote_opening"
                or self._dusk_jail_target is not None
            ):
                return
            self._dusk_stage = "voting"
            self._dusk_vote_active = True
            self._dusk_vote_deadline = time.time() + _VOTE_COUNTDOWN_SECONDS
            self._log("🗳️ 投票开始（30秒）。克罗可立即投票，居民投票会实时更新。", "system")
            self._broadcast_state()
        if getattr(self, "_running", False):
            threading.Thread(target=self._generate_dusk_votes_async, daemon=True).start()
        else:
            self._generate_dusk_votes_async()


    def _generate_dusk_votes_async(self):
        try:
            self._generate_dusk_votes()
        except Exception as exc:
            self._log(f"⚠️ 黄昏投票生成失败：{exc}", "error")
        finally:
            with self._lock:
                if self._dusk_vote_active and not getattr(self, "_dusk_vote_resolved", False):
                    if self._all_dusk_votes_collected():
                        self._log("🗳️ 全员投票完成，立即结算。", "system")
                        self._resolve_dusk_votes()
                    else:
                        self._broadcast_state()


    def _generate_dusk_votes(self):
        """Generate NPC votes/reasons for dusk discussion.
        Uses LLM if available, deterministic fallback otherwise.
        Each living non-jailed NPC (including self-voting) votes for one person or abstains.
        """
        eligible_voters = [n for n, a in self.agents.items()
                          if a.is_alive and n not in self._jailed]
        # Remove Crow from NPC vote generation; Crow votes separately via submit_crow_vote
        eligible_voters = [n for n in eligible_voters if n != self.detective_name]
        if not eligible_voters:
            return


        # Collect recent dead and clues for context
        recent_dead = list(self.dead_list[-3:]) if self.dead_list else []
        clue_summaries = [c.summary for c in getattr(self, 'clues', [])[-5:]]


        # For each voter, try LLM or fallback. Broadcast after each vote so the
        # vote board fills in live instead of waiting for all NPCs.
        for voter_name in eligible_voters:
            with self._lock:
                if (
                    self.phase != type(self.phase).DUSK_DISCUSSION
                    or not self._dusk_vote_active
                    or getattr(self, "_dusk_vote_resolved", False)
                    or self._dusk_jail_target is not None
                ):
                    return
                if voter_name in self._dusk_votes:
                    continue
            reason, voted = self._generate_single_dusk_vote(voter_name, recent_dead, clue_summaries)
            with self._lock:
                if (
                    self.phase != type(self.phase).DUSK_DISCUSSION
                    or not self._dusk_vote_active
                    or getattr(self, "_dusk_vote_resolved", False)
                    or self._dusk_jail_target is not None
                ):
                    return
                if voter_name in self._dusk_votes:
                    continue
                self._dusk_votes[voter_name] = voted
                self._dusk_vote_reasons[voter_name] = reason
                self._record_vote_history_snapshot()
                self._broadcast_state()
                if self._all_dusk_votes_collected():
                    self._resolve_dusk_votes()
                    return


    def _generate_single_dusk_vote(self, voter_name: str, recent_dead: list, clue_summaries: list) -> tuple[str, str]:
        """Generate a single NPC's dusk vote. Returns (reason, voted_target_name).
        Tries LLM; falls back to deterministic behavior. Self-voting is allowed."""
        agent = self.agents[voter_name]
        try:
            # Build prompt
            dead_str = "、".join(display_name_for_person(d) for d in recent_dead) if recent_dead else "无"
            clue_str = "；".join(clue_summaries[:3]) if clue_summaries else "暂无明确线索"


            # Get all living non-jailed residents (including self) as possible vote targets
            possible_targets = [n for n, a in self.agents.items()
                               if a.is_alive and n not in self._jailed and n != self.detective_name]
            if not possible_targets:
                return ("没有可指控的人", "")


            target_list = "、".join(display_name_for_person(t) for t in possible_targets)


            system_prompt = f"""你是 {display_name_for_person(voter_name)}，小镇居民。
当前是第{self.day}天黄昏讨论。请大家投票发表看法。
{active_town_people_rule()}
最近死者：{dead_str}
已知线索：{clue_str}
可选指控对象：{target_list}


⚠️ 你有完全独立的判断权：你必须投给一个具体嫌疑人（包括自己也可以），不要弃票，不要空票，不要说“无法判断”。
如果你是狼人，你更应该主动把票投给一个具体非狼人对象，制造压力和怀疑。不要划水，不要保守。
请分析并投票。输出JSON格式：
{{"reason": "你的推理（简短）", "vote": "指控对象名（必须是可选对象之一）"}}"""


            raw = ""
            try:
                raw = _chat_for_agent(voter_name, system_prompt, "请投票指控一个嫌疑人", max_retries=0)
                # Try to parse JSON from response
                import json as _json
                # Find JSON block
                if "{" in raw and "}" in raw:
                    start = raw.index("{")
                    end = raw.rindex("}") + 1
                    parsed = _json.loads(raw[start:end])
                    reason = str(parsed.get("reason", "可疑"))
                    vote_name = str(parsed.get("vote", ""))
                    if self._is_abstain_vote(vote_name):
                        return self._deterministic_dusk_vote(voter_name)
                    # Map display name back to internal name
                    vote_internal = self._resolve_display_name_to_internal(vote_name)
                    if vote_internal in possible_targets:
                        return (reason, vote_internal)
            except Exception:
                pass  # Fall through to deterministic


        except Exception:
            pass  # Fall through to deterministic


        # Deterministic fallback: vote for someone based on simple heuristics
        reason, target = self._deterministic_dusk_vote(voter_name)
        if not target and possible_targets:
            fallback_targets = [t for t in possible_targets if t != voter_name] or possible_targets
            target = self._rng.choice(fallback_targets)
            reason = f"我怀疑{display_name_for_person(target)}，他的行踪最需要解释。"
        return reason, target


    def _resolve_display_name_to_internal(self, display_or_name: str) -> str:
        """Resolve a display name back to internal name, if needed."""
        # Direct match
        if display_or_name in self.agents:
            return display_or_name
        # Reverse lookup display name
        for internal, disp in CHARACTER_DISPLAY_NAMES.items():
            if disp == display_or_name or display_or_name in disp:
                return internal
        return display_or_name


    @staticmethod
    def _is_abstain_vote(value: str) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized in {"", "abstain", "none", "null", "skip", "弃票", "不投", "未投", "无法判断"}


    def _deterministic_dusk_vote(self, voter_name: str) -> tuple[str, str]:
        """Deterministic fallback: vote based on simple clues and heuristics.
        Self-voting is allowed per spec section 5.3."""
        possible_targets = [n for n, a in self.agents.items()
                           if a.is_alive and n not in self._jailed and n != self.detective_name]
        if not possible_targets:
            return ("没有可指控的人", "")


        # Werewolf voters try to throw suspicion on villagers, or vote for self as cover
        agent = self.agents[voter_name]
        if agent.role == "werewolf":
            # Vote for a non-wolf villager (preferred), or self as fallback
            villager_targets = [t for t in possible_targets if t not in self.werewolf_names]
            if villager_targets:
                target = self._rng.choice(villager_targets)
                return (f"我觉得{display_name_for_person(target)}的行为有些可疑", target)
            # Only wolves or self available; wolves vote for self rather than other wolf
            if voter_name in possible_targets and self._rng.random() < 0.5:
                return ("我觉得自己是清白的，投自己表明立场。", voter_name)
            target = self._rng.choice(possible_targets)
            return (f"我怀疑{display_name_for_person(target)}", target)


        # Villager voters: if clues point to someone, vote them; otherwise push
        # the most suspicious available person instead of defaulting to abstain.
        clues_about = set()
        for clue in getattr(self, 'clues', []):
            if clue.related_person and clue.related_person in possible_targets:
                clues_about.add(clue.related_person)


        if clues_about:
            target = self._rng.choice(list(clues_about))
            return (f"根据线索，{display_name_for_person(target)}很可疑", target)


        suspicion_targets = [t for t in possible_targets if t != voter_name] or possible_targets
        target = self._rng.choice(suspicion_targets)
        return (f"我感觉{display_name_for_person(target)}最近有些不对劲", target)


    def _eligible_dusk_voters(self) -> list[str]:
        return [
            n for n, a in self.agents.items()
            if a.is_alive and n not in self._jailed
        ]


    def _all_dusk_votes_collected(self) -> bool:
        voters = set(self._eligible_dusk_voters())
        if not voters:
            return True
        return voters.issubset(set(self._dusk_votes.keys()))


    def _finalize_missing_dusk_votes_as_abstain(self) -> None:
        for name in self._eligible_dusk_voters():
            if name not in self._dusk_votes:
                self._dusk_votes[name] = ""
                reason = "克罗未投票（弃票）" if name == self.detective_name else "投票倒计时结束，视为弃票"
                self._dusk_vote_reasons[name] = reason
                if name == self.detective_name:
                    self._dusk_crow_voted = True
        self._record_vote_history_snapshot()


    def submit_crow_vote(self, target_name: str) -> dict:
        """Player submits Crow's vote. Crow can vote for any living non-jailed participant
        including self, or pass empty string to abstain. After voting, auto-resolve if all
        NPC votes are in; otherwise wait for countdown (spec section 5.6-5.7)."""
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                return {"error": "Not in dusk discussion phase"}
            if not self._dusk_vote_active:
                return {"error": "Dusk voting is not active"}
            if self._dusk_jail_target is not None:
                return {"error": "Voting already resolved"}
            if getattr(self, "_dusk_crow_voted", False):
                return {"error": "Crow has already voted"}

            # Validate if target provided (non-empty = vote, empty = abstain)
            if target_name:
                target = self.agents.get(target_name)
                if not target:
                    return {"error": f"Unknown target: {target_name}"}
                if not target.is_alive:
                    return {"error": f"{display_name_for_person(target_name)} is dead"}
                if target_name in self._jailed:
                    return {"error": f"{display_name_for_person(target_name)} is already jailed"}

            # Record Crow's vote (target_name may be empty for abstain)
            self._dusk_votes[self.detective_name] = target_name
            self._dusk_vote_reasons[self.detective_name] = "克罗的投票"
            self._dusk_crow_voted = True

            voted_disp = display_name_for_person(target_name) if target_name else "弃票"
            self._log(f"🗳️ 克罗投票: {voted_disp}", "action")

            if self._all_dusk_votes_collected():
                result = self._resolve_dusk_votes()
            else:
                self._record_vote_history_snapshot()
                result = {"success": True, "pending": True, "vote_summary": self._build_vote_summary()}
            self._broadcast_state()
            return result

    def jail_vote_target(self, target_name: str) -> dict:
        """Legacy API: acts as Crow's vote. Calls submit_crow_vote internally."""
        return self.submit_crow_vote(target_name)

    def _resolve_dusk_votes(self) -> dict:
        """Compute vote winner using highest-vote + Crow tie-break (spec section 6).
        Returns the result dict with winner info."""
        if self._dusk_jail_target is not None:
            return {"error": "Voting already resolved"}
        if getattr(self, "_dusk_vote_resolved", False):
            return {"error": "Voting already resolved"}

        # Crow's normal vote counts once; if the resulting top count is tied,
        # Crow's choice among the tied candidates is the extra sheriff half-vote.
        vote_counts = {}
        abstain_count = 0
        for voter, target in self._dusk_votes.items():
            if target:
                vote_counts[target] = vote_counts.get(target, 0) + 1
            else:
                abstain_count += 1

        if not vote_counts:
            # Everyone abstained: keep a result screen so the player still confirms the flow.
            self._dusk_vote_active = False
            self._dusk_vote_resolved = True
            self._dusk_stage = "results"
            self._record_vote_history_snapshot(jail_target=None)
            self._log("🗳️ 所有人弃票，无人被拘留。", "action")
            if hasattr(self, "_record_observation_event"):
                self._record_observation_event(
                    event_type="vote_result",
                    subject="town",
                    text="所有人弃票，无人被拘留。",
                    x=0,
                    y=0,
                    public=True,
                    source="dusk_vote",
                )
            return {
                "success": True,
                "jailed": None,
                "jailed_display": None,
                "vote_summary": self._build_vote_summary(),
                "result_note": "所有人弃票，无人被拘留",
            }

        # Find max vote count
        max_count = max(vote_counts.values())
        top_candidates = [t for t, c in vote_counts.items() if c == max_count]

        winner = None
        result_note = ""

        if len(top_candidates) == 1:
            # Clear winner
            winner = top_candidates[0]
            result_note = f"{display_name_for_person(winner)} 得票最高（{max_count}票）"
        else:
            # Tie-break: Crow's vote among tied candidates wins (spec section 6.3)
            crow_vote = self._dusk_votes.get(self.detective_name, "")
            if crow_vote and crow_vote in top_candidates:
                winner = crow_vote
                result_note = (
                    f"最高票平票（{max_count}票），按警长裁决权，"
                    f"由警长所投对象 {display_name_for_person(winner)} 胜出"
                )
            else:
                # Crow didn't vote for any tied candidate → stable order (spec section 6.4)
                winner = sorted(top_candidates)[0]
                result_note = (
                    f"最高票平票（{max_count}票），警长未投给平票者，"
                    f"按稳定顺序 {display_name_for_person(winner)} 胜出"
                )

        self._dusk_vote_active = False
        self._dusk_vote_resolved = True
        self._dusk_stage = "results"
        self._dusk_winner = winner
        self._dusk_result_note = result_note
        self._record_vote_history_snapshot(jail_target=winner)
        vote_summary = self._build_vote_summary()
        self._log(f"🗳️ {result_note}。等待确认投票结果。", "action")
        if hasattr(self, "_record_observation_event"):
            self._record_observation_event(
                event_type="vote_result",
                subject=winner or "town",
                text=result_note,
                x=0,
                y=0,
                public=True,
                source="dusk_vote",
            )

        return {
            "success": True,
            "winner": winner,
            "winner_display": display_name_for_person(winner) if winner else None,
            "vote_summary": vote_summary,
            "result_note": result_note,
        }

    def confirm_vote_result(self) -> dict:
        """Confirm the immutable vote result, then escort the winner and enter night.

        On Day4, instead of entering night, resolves the game using Day4 win rules.
        """
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                return {"error": "Not in dusk discussion phase"}
            if getattr(self, "_dusk_stage", "") != "results":
                return {"error": "Vote result is not ready"}
            winner = getattr(self, "_dusk_winner", None)
            if getattr(self, "_dusk_result_sequence_running", False):
                return {"success": True, "jailed": winner, "pending": True}
            self._dusk_result_sequence_running = True
            self._dusk_jail_target = winner
            self._dusk_stage = "result_announcement_pending"
            self._broadcast_state()

        if getattr(self, "_running", False):
            threading.Thread(target=self._run_vote_result_sequence, args=(winner,), daemon=True).start()
        else:
            self._run_vote_result_sequence(winner)
        return {"success": True, "jailed": winner, "pending": True}

    def _run_vote_result_sequence(self, winner: str | None) -> None:
        if winner:
            warning = (
                f"{display_name_for_person(winner)}得票最高，我会先把你关押进牢房。"
                "你还有什么话要说？"
            )
            with self._lock:
                if self.phase != type(self.phase).DUSK_DISCUSSION:
                    self._dusk_result_sequence_running = False
                    return
                self._dusk_stage = "result_announcement"
                self.chat_bubbles[self.detective_name] = {
                    "text": warning,
                    "target": winner,
                    "time": time.time(),
                }
                self._log(f"💬 克罗（宣布投票结果）: {warning}", "chat")
                self._broadcast_state()
            self._pause_for_dusk_bubble()

            final_words = self._jailed_final_words(winner)
            with self._lock:
                if self.phase != type(self.phase).DUSK_DISCUSSION:
                    self._dusk_result_sequence_running = False
                    return
                self._dusk_stage = "final_words"
                self.chat_bubbles[winner] = {
                    "text": final_words,
                    "target": self.detective_name,
                    "time": time.time(),
                }
                self._log(f"💬 {display_name_for_person(winner)}（被拘留）: {final_words}", "chat")
                self._broadcast_state()
            self._pause_for_dusk_final_words()

            with self._lock:
                if self.phase != type(self.phase).DUSK_DISCUSSION:
                    self._dusk_result_sequence_running = False
                    return
                self._jailed.add(winner)
                self._start_prison_escort(winner)
                self._dusk_stage = "escorting"
                self._dusk_result_sequence_running = False
                if self.day == 4:
                    outcome = self._resolve_day4_after_vote()
                    if outcome == "pending_silver_shot":
                        self._log("⚠️ 请克罗做出最终决定：使用银子弹射击存疑目标。", "system")
                self._broadcast_state()
            return

        dismissal = "今晚无人被关押。大家先回去吧，晚上注意小心，尽量不要出去。"
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                self._dusk_result_sequence_running = False
                return
            self._dusk_stage = "result_announcement"
            self.chat_bubbles[self.detective_name] = {
                "text": dismissal,
                "target": "",
                "time": time.time(),
            }
            self._log(f"💬 克罗（投票结束）: {dismissal}", "chat")
            self._broadcast_state()
        self._pause_for_dusk_bubble()
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                self._dusk_result_sequence_running = False
                return
            self._send_crow_to_sheriff_office()
            self._dusk_stage = "escorting"
            self._dusk_result_sequence_running = False
            self._broadcast_state()

    def _send_crow_to_sheriff_office(self) -> None:
        crow = self.agents.get(self.detective_name)
        if not crow:
            return
        office = SHERIFF_AREA["sheriff_office"]["anchor_points"][0]
        path_result = self._nearest_reachable_path(
            (crow.x, crow.y),
            office,
            radius=8,
            blocked=self._occupied_tiles({self.detective_name}),
        )
        if path_result:
            target_x, target_y, path = path_result
            target = (target_x, target_y)
        else:
            target = (crow.x, crow.y)
            path = []
        crow.target_x, crow.target_y = target
        crow.current_action = "押送结束，返回警长办公室"
        crow.current_emoji = "🔒"
        self.agent_paths[self.detective_name] = path
        crow.runtime_state = "moving" if path else "idle"

    def _start_prison_escort(self, target_name: str) -> None:
        try:
            self._place_in_prison(target_name, walk=True)
        except TypeError:
            self._place_in_prison(target_name)
        self._send_crow_to_prison_escort_target(target_name)


    def _send_crow_to_prison_escort_target(self, target_name: str) -> None:
        crow = self.agents.get(self.detective_name)
        target = self.agents.get(target_name)
        if not crow or not target:
            self._send_crow_to_sheriff_office()
            return
        target_point = (
            getattr(target, "target_x", target.x),
            getattr(target, "target_y", target.y),
        )
        path_result = self._path_adjacent_to(
            (crow.x, crow.y),
            target_point,
            blocked=self._occupied_tiles({self.detective_name, target_name}),
            prefer_horizontal=True,
        )
        if path_result:
            target_x, target_y, path = path_result
            crow.target_x, crow.target_y = target_x, target_y
            self.agent_paths[self.detective_name] = path
            crow.runtime_state = "moving" if path else "idle"
        else:
            self._send_crow_to_sheriff_office()
        crow.current_action = f"押送{display_name_for_person(target_name)}前往牢房"
        crow.current_emoji = "🔒"


    def _place_in_prison(self, target_name: str, walk: bool = False):
        """Move a jailed target to a prison cell anchor point."""
        target = self.agents[target_name]
        # Pick the emptier prison cell
        cell_1_occupants = sum(1 for n in self._jailed
                              if n != target_name and self._get_prison_cell(n) == "prison_cell_1")
        cell_2_occupants = sum(1 for n in self._jailed
                              if n != target_name and self._get_prison_cell(n) == "prison_cell_2")


        preferred_cells = (
            ["prison_cell_2", "prison_cell_1"]
            if cell_2_occupants <= cell_1_occupants
            else ["prison_cell_1", "prison_cell_2"]
        )
        occupied = self._occupied_tiles({target_name})
        best = None
        for cell_key in preferred_cells:
            for anchor in SHERIFF_AREA[cell_key]["anchor_points"]:
                path_result = self._nearest_reachable_path(
                    (target.x, target.y),
                    anchor,
                    radius=10,
                    blocked=occupied,
                )
                if not path_result:
                    continue
                target_x, target_y, path = path_result
                score = (0 if cell_key == "prison_cell_2" else 1, len(path))
                if best is None or score < best[0]:
                    best = (score, cell_key, (target_x, target_y), path)

        if best:
            _, chosen_cell, best_pt, path = best
        else:
            chosen_cell = preferred_cells[0]
            best_pt = (target.x, target.y)
            path = []

        setattr(target, '_prison_cell', chosen_cell)
        target.target_x, target.target_y = best_pt
        target.current_location = SHERIFF_AREA[chosen_cell]["name"]
        target.current_action = "被拘留中"
        target.current_emoji = "🔒"
        target.runtime_state = "jailed"
        if walk:
            self.agent_paths[target_name] = path
            target.runtime_state = "moving" if path else "jailed"
            return
        target.x, target.y = best_pt
        self.agent_paths.pop(target_name, None)


    def _get_prison_cell(self, name: str) -> str:
        """Get which prison cell a jailed NPC is in."""
        agent = self.agents.get(name)
        if agent:
            return getattr(agent, '_prison_cell', 'prison_cell_1')
        return 'prison_cell_1'


    def _jailed_final_words(self, target_name: str) -> str:
        """Generate final words for a jailed target."""
        agent = self.agents[target_name]
        if agent.role == "werewolf":
            fallback = "我不是狼人，这次判断太急了；请继续查行踪含糊的人，别让真凶躲过去。"
        else:
            fallback = "我是好人，我的行踪经得起查；请继续盯住可疑对象，别让狼人带偏投票。"
        try:
            recent_dead = "、".join(display_name_for_person(d) for d in self.dead_list[-3:]) if self.dead_list else "暂无"
            clue_summaries = [c.summary for c in getattr(self, "clues", [])[-5:]]
            clue_text = "；".join(clue_summaries[:3]) if clue_summaries else "暂无明确线索"
            suspect_pool = [
                display_name_for_person(name)
                for name, suspect in self.agents.items()
                if name != target_name and suspect.is_alive and name not in self._jailed
            ]
            suspect_text = "、".join(suspect_pool) or "暂无其他存活对象"
            if agent.role == "werewolf":
                role_instruction = (
                    "你实际是狼人，但遗言必须伪装成好人：自证清白，点名一个具体对象甩锅，"
                    "提醒大家继续查他。禁止承认狼人身份，禁止狠话，禁止嘲讽或挑衅克罗。"
                )
            else:
                role_instruction = (
                    "你是好人。遗言必须自证清白，点名一个具体怀疑对象，提醒大家下一步查证。"
                    "禁止狠话，禁止嘲讽或挑衅克罗。"
                )
            raw = _chat_for_agent(target_name,
                (
                    f"你是{display_name_for_person(target_name)}，被克罗按黄昏投票结果关押。"
                    f"最近死者：{recent_dead}。公开线索：{clue_text}。"
                    f"可怀疑对象：{suspect_text}。{role_instruction}"
                    "请说一段80字以内的遗言，只说角色本人会说的话。"
                ),
                "请说黄昏投票后的遗言", max_retries=0)
            if raw and len(raw.strip()) >= 4:
                return raw.strip()[:120]
        except Exception:
            pass
        return fallback


    def _build_vote_summary(self) -> dict:
        """Build a structured vote summary for get_status.
        Includes voter lists per target, deadline, Crow vote status (spec section 6)."""
        vote_counts = {}
        voters_by_target = {}
        abstain_count = 0
        for voter, target in self._dusk_votes.items():
            if target:
                vote_counts[target] = vote_counts.get(target, 0) + 1
                voters_by_target.setdefault(target, []).append(voter)
            else:
                abstain_count += 1

        # Sort by count descending
        sorted_votes = sorted(vote_counts.items(), key=lambda x: -x[1])

        # Build count entries with voter lists
        count_entries = []
        for t, c in sorted_votes:
            voter_list = voters_by_target.get(t, [])
            count_entries.append({
                "target": t,
                "display": display_name_for_person(t),
                "count": c,
                "voters": voter_list,
                "voter_displays": [display_name_for_person(v) for v in voter_list],
            })

        return {
            "votes": dict(self._dusk_votes),
            "reasons": dict(self._dusk_vote_reasons),
            "counts": count_entries,
            "voters_by_target": {t: list(vs) for t, vs in voters_by_target.items()},
            "abstain_count": abstain_count,
            "active": self._dusk_vote_active,
            "deadline": getattr(self, "_dusk_vote_deadline", None),
            "seconds_remaining": max(0, int((getattr(self, "_dusk_vote_deadline", 0) or 0) - time.time())),
            "crow_voted": getattr(self, "_dusk_crow_voted", False),
            "crow_vote": self._dusk_votes.get(self.detective_name) if getattr(self, "_dusk_crow_voted", False) else None,
            "discussion_active": getattr(self, "_dusk_discussion_active", False),
            "discussion_statements": list(getattr(self, "_dusk_discussion_statements", [])),
            "crow_statement": getattr(self, "_dusk_crow_statement", ""),
            "jail_target": self._dusk_jail_target,
            "jail_target_display": display_name_for_person(self._dusk_jail_target) if self._dusk_jail_target else None,
            "eligible_participants": self._eligible_dusk_participants(),
            "stage": getattr(self, "_dusk_stage", ""),
            "winner": getattr(self, "_dusk_winner", None),
            "winner_display": display_name_for_person(self._dusk_winner) if getattr(self, "_dusk_winner", None) else None,
            "result_note": getattr(self, "_dusk_result_note", ""),
            "tie_broken_by_crow": "警长裁决权" in getattr(self, "_dusk_result_note", ""),
        }


    def _record_vote_history_snapshot(self, jail_target: str | None = None) -> None:
        summary = self._build_vote_summary()
        entry = {
            "day": self.day,
            "votes": summary["votes"],
            "reasons": summary["reasons"],
            "counts": summary["counts"],
            "voters_by_target": summary.get("voters_by_target", {}),
            "abstain_count": summary.get("abstain_count", 0),
            "crow_voted": summary.get("crow_voted", False),
            "jail_target": jail_target or self._dusk_jail_target,
            "jail_target_display": display_name_for_person(jail_target or self._dusk_jail_target) if (jail_target or self._dusk_jail_target) else None,
        }
        self._vote_history = [e for e in getattr(self, "_vote_history", []) if e.get("day") != self.day]
        self._vote_history.append(entry)


    # ==================== 每日任务 & 银器进展 ====================


