"""Dusk discussion, voting, and prison helpers for WerewolfGameEngine."""

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
    "我今天在大学里查了不少旧资料，也专门对照了第一天死者身上的伤痕。"
    "现在我基本可以确定，那种咬痕和抓痕不是普通野兽留下的，而是狼人造成的。"
    "从伤口的形状来看，凶手很可能不止一个，甚至可能有两个。"
    "狼人是一种古老又危险的生物，白天看起来和正常人一样，也没有可怕的攻击力，"
    "是最容易被制服的时候；可一到晚上，它就会变成狼首怪物，力量和攻击性都非常强，"
    "手无寸铁的人很容易被它咬死或者抓死。所以今晚大家一定要小心，尽量待在室内。"
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


class EngineDuskMixin:
    def _dusk_tick(self):
        """黄昏讨论阶段：移动 NPC，检查投票倒计时，超时自动解决投票并进入夜晚"""
        self._move_agents()
        elapsed = time.time() - (self.dusk_start_time or time.time())

        if getattr(self, "_dusk_stage", "") == "gathering":
            participants = self._eligible_dusk_participants()
            if all(
                (self.agents[name].x, self.agents[name].y)
                == (self.agents[name].target_x, self.agents[name].target_y)
                for name in participants
            ):
                self._begin_dusk_discussion_after_gathering()
            return

        if getattr(self, "_dusk_stage", "") == "escorting":
            crow = self.agents.get(self.detective_name)
            if crow and (crow.x, crow.y) == (crow.target_x, crow.target_y):
                self._transition_to_night()
            return

        # Phase-level timeout: if dusk exceeds dusk_duration, force transition
        if elapsed >= self.dusk_duration:
            self._log("⏰ 黄昏讨论时间到，自动进入夜晚...", "system")
            if not getattr(self, "_dusk_vote_resolved", False) and self._dusk_vote_active:
                self._resolve_dusk_votes()
            elif getattr(self, "_dusk_stage", "") == "results":
                self.confirm_vote_result()
            else:
                self._transition_to_night()
            return

        # Voting countdown: if vote is active and deadline passed, auto-resolve
        if (self._dusk_vote_active
                and not getattr(self, "_dusk_vote_resolved", False)
                and self._dusk_jail_target is None
                and self._dusk_vote_deadline is not None
                and time.time() >= self._dusk_vote_deadline):
            self._log("⏰ 投票时间到！自动解决投票...", "system")
            # If Crow hasn't voted, record abstain
            if not getattr(self, "_dusk_crow_voted", False):
                self._dusk_votes[self.detective_name] = ""
                self._dusk_vote_reasons[self.detective_name] = "克罗未投票（弃票）"
                self._dusk_crow_voted = True
                self._log("🗳️ 克罗未在时限内投票，视为弃票。", "system")
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
        self._log("🌅 黄昏降临，居民们聚集讨论今天的发现...", "action")
        self.chat_bubbles[self.detective_name] = {
            "text": _CROW_GATHERING_TEXT,
            "target": "",
            "time": time.time(),
        }
        self._send_dusk_participants_to_plaza()
        self._broadcast_state()

    def _eligible_dusk_participants(self) -> list[str]:
        return [
            name for name, agent in self.agents.items()
            if agent.is_alive and name not in self._jailed
        ]

    def _send_dusk_participants_to_plaza(self) -> None:
        """Reuse the morning plaza ring and make all eligible participants walk there."""
        import math

        participants = self._eligible_dusk_participants()
        center_x = INITIAL_BODY_SITE["x"]
        center_y = INITIAL_BODY_SITE["y"]
        radius = 7
        for idx, name in enumerate(self.agents):
            if name not in participants:
                continue
            desired = (
                round(center_x + radius * math.cos(idx * 2 * math.pi / len(self.agents))),
                round(center_y + radius * math.sin(idx * 2 * math.pi / len(self.agents))),
            )
            target = self._nearest_walkable_tile(
                desired,
                radius=6,
                blocked=self._occupied_tiles({name}),
            ) or desired
            agent = self.agents[name]
            agent.target_x, agent.target_y = target
            agent.current_location = INITIAL_BODY_SITE["location"]
            agent.current_action = "前往广场参加黄昏讨论"
            agent.current_emoji = "🚶"
            self.agent_paths.pop(name, None)

    def _begin_dusk_discussion_after_gathering(self) -> None:
        if getattr(self, "_dusk_stage", "") != "gathering":
            return
        self._dusk_stage = "knowledge_reveal"
        if self.day == 1:
            self._reveal_day1_werewolf_knowledge()
            self._pause_for_dusk_bubble()
        self.chat_bubbles[self.detective_name] = {
            "text": _CROW_DISCUSSION_TEXT,
            "target": "",
            "time": time.time(),
        }
        self._broadcast_state()
        self._pause_for_dusk_bubble()
        self._generate_dusk_discussion_statements()
        self._dusk_stage = "crow_statement"
        self._log("请克罗总结发言。克罗发言后，居民再进入投票。", "system")
        self._broadcast_state()

    def _pause_for_dusk_bubble(self) -> None:
        """Keep fixed sequence bubbles readable in the live game without slowing unit tests."""
        if getattr(self, "_running", False):
            time.sleep(max(3.0, float(self._gathering_speech_visible_seconds())))

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
        # Calculate angle from plaza center for each agent
        def angle_from_center(name):
            agent = self.agents[name]
            dx = agent.x - center_x
            dy = agent.y - center_y
            # atan2 returns angle where 0 is east, positive is CCW
            # Convert to clockwise starting from left (west = π)
            import math
            a = math.atan2(dy, dx)
            # Shift so 0 is west (left of center), clockwise increasing
            a = math.pi - a
            if a < 0:
                a += 2 * math.pi
            return a
        return sorted(eligible, key=angle_from_center)

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
        self._log(f"💬 {disp}（第1天知识揭露）: {_DAY1_KNOWLEDGE_TEXT[:80]}...", "chat")
        self._broadcast_state()

    # ==================== Dusk discussion ====================

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

        speaker_gap = float(self._gathering_departure_gap_seconds())
        for idx, speaker_name in enumerate(eligible_speakers):
            text = ""
            try:
                agent = self.agents[speaker_name]
                memory_text = str(agent.read_memory() or "")[-900:]
                cognition_text = str(agent.read_cognition() or "")[-500:]
                text = _chat_for_agent(
                    speaker_name,
                    (
                        f"你是{display_name_for_person(speaker_name)}，现在是第{self.day}天黄昏讨论。"
                        f"最近死者：{recent_dead}。已知线索：{clue_text}。"
                        f"你对白天经历的记忆：{memory_text}。你的当前判断：{cognition_text}。"
                        "结合自己的经历、怀疑和阵营目标发表意见，可以辩护、怀疑、说真话或撒谎；"
                        "不要投票，不要要求马上拘留。80字以内。"
                    ),
                    "请发表黄昏讨论发言，不要投票。",
                    max_retries=0,
                )
            except Exception:
                text = ""
            text = str(text or "").strip()
            if not text:
                text = "我会根据今天的线索谨慎判断，先听完大家和克罗的意见。"
            text = self._limit_gathering_speech(text, max_chars=90)
            statements.append({"speaker": speaker_name, "text": text})
            self.chat_bubbles[speaker_name] = {
                "text": text,
                "target": self.detective_name,
                "time": time.time(),
            }
            self._log(f"💬 黄昏讨论 {display_name_for_person(speaker_name)}: {text}", "chat")
            self._dusk_discussion_statements = list(statements)
            self._broadcast_state()
            if idx < len(eligible_speakers) - 1 and speaker_gap > 0:
                time.sleep(speaker_gap)

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
            self._broadcast_state()
            self._pause_for_dusk_bubble()
            self._generate_dusk_votes()
            self._dusk_vote_active = True
            self._dusk_stage = "voting"
            self._dusk_vote_deadline = time.time() + _VOTE_COUNTDOWN_SECONDS
            self._dusk_crow_voted = False
            self._log("🗳️ 黄昏发言结束，投票开始（30秒）。请克罗投票。", "system")
            self.chat_bubbles[self.detective_name] = {
                "text": _CROW_START_VOTE_TEXT,
                "target": "",
                "time": time.time(),
            }
            self._broadcast_state()
            return {
                "success": True,
                "statement": text,
                "vote_summary": self._build_vote_summary(),
            }


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


        # For each voter, try LLM or fallback
        for voter_name in eligible_voters:
            reason, voted = self._generate_single_dusk_vote(voter_name, recent_dead, clue_summaries)
            self._dusk_votes[voter_name] = voted
            self._dusk_vote_reasons[voter_name] = reason
        self._record_vote_history_snapshot()


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
                               if a.is_alive and n not in self._jailed]
            if not possible_targets:
                return ("没有可指控的人", "")


            target_list = "、".join(display_name_for_person(t) for t in possible_targets)


            system_prompt = f"""你是 {display_name_for_person(voter_name)}，小镇居民。
当前是第{self.day}天黄昏讨论。请大家投票发表看法。
{active_town_people_rule()}
最近死者：{dead_str}
已知线索：{clue_str}
可选指控对象：{target_list}


⚠️ 你有完全独立的判断权：你可以根据自己的推理投票指控任何人（包括自己），也可以选择弃票（证据不足时）。不受他人影响，不需要迎合任何人的意见。
请分析并投票。输出JSON格式：
{{"reason": "你的推理（简短）", "vote": "指控对象名（可选对象之一，包括自己，或空置票）"}}"""


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
                        return (reason or "我现在证据不足，先弃票。", "")
                    # Map display name back to internal name
                    vote_internal = self._resolve_display_name_to_internal(vote_name)
                    if vote_internal in possible_targets:
                        return (reason, vote_internal)
            except Exception:
                pass  # Fall through to deterministic


        except Exception:
            pass  # Fall through to deterministic


        # Deterministic fallback: vote for someone based on simple heuristics
        return self._deterministic_dusk_vote(voter_name)


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
                           if a.is_alive and n not in self._jailed]
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


        # Villager voters: if clues point to someone, vote them; otherwise random/self/abstain
        clues_about = set()
        for clue in getattr(self, 'clues', []):
            if clue.related_person and clue.related_person in possible_targets:
                clues_about.add(clue.related_person)


        if clues_about:
            target = self._rng.choice(list(clues_about))
            return (f"根据线索，{display_name_for_person(target)}很可疑", target)


        if self._rng.random() < 0.55:
            return ("我现在还没有足够把握，先弃票。", "")


        # 20% chance of self-vote for villagers as a defensive strategy
        if self._rng.random() < 0.20 and voter_name in possible_targets:
            return ("我确信自己不是狼人，投自己一票。", voter_name)

        # Random vote
        target = self._rng.choice(possible_targets)
        return (f"我感觉{display_name_for_person(target)}最近有些不对劲", target)


    def submit_crow_vote(self, target_name: str) -> dict:
        """Player submits Crow's vote. Crow can vote for any living non-jailed participant
        including self, or pass empty string to abstain. After voting, auto-resolve if all
        NPC votes are in; otherwise wait for countdown (spec section 5.6-5.7)."""
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                return {"error": "Not in dusk discussion phase"}
            if not self._dusk_vote_active:
                return {"error": "Dusk votes not yet generated"}
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

            # Auto-resolve immediately since all NPC votes are pre-generated
            result = self._resolve_dusk_votes()
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
            if winner:
                self._dusk_jail_target = winner
                self._jailed.add(winner)
                self._place_in_prison(winner)
                final_words = self._jailed_final_words(winner)
                warning = (
                    f"{display_name_for_person(winner)}得票最高，我先把他带到牢房。"
                    "马上天黑了，请大家尽量待在室内，不要外出。"
                )
                self.chat_bubbles[self.detective_name] = {
                    "text": warning,
                    "target": winner,
                    "time": time.time(),
                }
                self._log(f"💬 {display_name_for_person(winner)}（被拘留）: {final_words}", "chat")
            crow = self.agents.get(self.detective_name)
            office = SHERIFF_AREA["sheriff_office"]["anchor_points"][0]
            target = self._nearest_walkable_tile(
                office,
                blocked=self._occupied_tiles({self.detective_name}),
            ) or office
            crow.target_x, crow.target_y = target
            crow.current_action = "押送结束，返回警长办公室"
            crow.current_emoji = "🔒"
            self.agent_paths.pop(self.detective_name, None)
            self._dusk_stage = "escorting"
            # Day4: resolve game outcome after vote
            if self.day == 4:
                outcome = self._resolve_day4_after_vote()
                if outcome == "pending_silver_shot":
                    self._log("⚠️ 请克罗做出最终决定：使用银子弹射击存疑目标。", "system")
                self._broadcast_state()
                return {"success": True, "jailed": winner, "day4_outcome": outcome}
            if winner == self.detective_name:
                self._transition_to_night()
            self._broadcast_state()
            return {"success": True, "jailed": winner}


    def _place_in_prison(self, target_name: str):
        """Move a jailed target to a prison cell anchor point."""
        target = self.agents[target_name]
        # Pick the emptier prison cell
        cell_1_occupants = sum(1 for n in self._jailed
                              if n != target_name and self._get_prison_cell(n) == "prison_cell_1")
        cell_2_occupants = sum(1 for n in self._jailed
                              if n != target_name and self._get_prison_cell(n) == "prison_cell_2")


        chosen_cell = "prison_cell_1" if cell_1_occupants <= cell_2_occupants else "prison_cell_2"
        setattr(target, '_prison_cell', chosen_cell)


        anchor_points = SHERIFF_AREA[chosen_cell]["anchor_points"]
        # Pick anchor point not occupied
        occupied = self._occupied_tiles({target_name})
        best_pt = anchor_points[0]
        for pt in anchor_points:
            if pt not in occupied:
                best_pt = pt
                break


        target.x, target.y = best_pt
        target.target_x, target.target_y = best_pt
        target.current_location = SHERIFF_AREA[chosen_cell]["name"]
        target.current_action = "被拘留中"
        target.current_emoji = "🔒"
        target.runtime_state = "jailed"
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
            fallback = "我没有杀人！这是误会！"
        else:
            fallback = "我是无辜的，请务必查清真相！"
        try:
            raw = _chat_for_agent(target_name,
                f"你被Crow拘留了。这是你最后对外说的话。请用{display_name_for_person(target_name)}的身份说一句简短的话。",
                "请说最后一句话", max_retries=0)
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
            "crow_voted": getattr(self, "_dusk_crow_voted", False),
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


