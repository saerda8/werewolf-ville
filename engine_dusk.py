"""Dusk discussion, voting, and prison helpers for WerewolfGameEngine."""

import time
import sys

from llm import chat_for_agent
from world_config import ACTIVE_CHARACTERS, CHARACTER_DISPLAY_NAMES, SHERIFF_AREA, display_name_for_person


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
        """黄昏讨论阶段：移动 NPC 但检查阶段超时（可配置时长），超时后自动进入夜晚"""
        self._move_agents()
        elapsed = time.time() - (self.dusk_start_time or time.time())
        if elapsed >= self.dusk_duration:
            self._log("⏰ 黄昏讨论时间到，自动进入夜晚...", "system")
            self._transition_to_night()


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
        """进入黄昏讨论阶段：居民聚集，生成 NPC 投票，等待玩家最终拘留决定。"""
        self.phase = type(self.phase).DUSK_DISCUSSION
        self.dusk_start_time = time.time()
        self._dusk_votes = {}
        self._dusk_vote_reasons = {}
        self._dusk_vote_active = False
        self._dusk_jail_target = None
        self._log("🌅 黄昏降临，居民们聚集讨论今天的发现...", "action")
        # Generate NPC votes (deterministic fallback; LLM-enriched when available)
        self._generate_dusk_votes()
        self._dusk_vote_active = True
        self._log("🗳️ NPC 投票已生成，等待玩家选择拘留目标", "system")
        self._broadcast_state()


    def _generate_dusk_votes(self):
        """Generate NPC votes/reasons for dusk discussion.
        Uses LLM if available, deterministic fallback otherwise.
        Each living non-jailed non-Crow NPC votes for one person.
        """
        eligible_voters = [n for n, a in self.agents.items()
                          if n != self.detective_name and a.is_alive and n not in self._jailed]
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
        Tries LLM; falls back to deterministic behavior."""
        agent = self.agents[voter_name]
        try:
            # Build prompt
            dead_str = "、".join(display_name_for_person(d) for d in recent_dead) if recent_dead else "无"
            clue_str = "；".join(clue_summaries[:3]) if clue_summaries else "暂无明确线索"


            # Get all living non-jailed residents (excluding self) as possible vote targets
            possible_targets = [n for n, a in self.agents.items()
                               if n != voter_name and n != self.detective_name
                               and a.is_alive and n not in self._jailed]
            if not possible_targets:
                return ("没有可指控的人", "")


            target_list = "、".join(display_name_for_person(t) for t in possible_targets)


            system_prompt = f"""你是 {display_name_for_person(voter_name)}，小镇居民。
当前是第{self.day}天黄昏讨论。请大家投票发表看法。
{active_town_people_rule()}
最近死者：{dead_str}
已知线索：{clue_str}
可选指控对象：{target_list}


⚠️ 你有完全独立的判断权：你可以根据自己的推理投票指控任何人，也可以选择弃票（证据不足时）。不受他人影响，不需要迎合任何人的意见。
请分析并投票。输出JSON格式：
{{"reason": "你的推理（简短）", "vote": "指控对象名（可选对象之一，或空置票）"}}"""


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
        """Deterministic fallback: vote based on simple clues and heuristics."""
        possible_targets = [n for n, a in self.agents.items()
                           if n != voter_name and n != self.detective_name
                           and a.is_alive and n not in self._jailed]
        if not possible_targets:
            return ("没有可指控的人", "")


        # Werewolf voters try to throw suspicion on villagers
        agent = self.agents[voter_name]
        if agent.role == "werewolf":
            # Vote for a non-wolf villager
            villager_targets = [t for t in possible_targets if t not in self.werewolf_names]
            if villager_targets:
                target = self._rng.choice(villager_targets)
                return (f"我觉得{display_name_for_person(target)}的行为有些可疑", target)
            target = self._rng.choice(possible_targets)
            return (f"我怀疑{display_name_for_person(target)}", target)


        # Villager voters: if clues point to someone, vote them; otherwise random
        clues_about = set()
        for clue in getattr(self, 'clues', []):
            if clue.related_person and clue.related_person in possible_targets:
                clues_about.add(clue.related_person)


        if clues_about:
            target = self._rng.choice(list(clues_about))
            return (f"根据线索，{display_name_for_person(target)}很可疑", target)


        if self._rng.random() < 0.55:
            return ("我现在还没有足够把握，先弃票。", "")


        # Random vote
        target = self._rng.choice(possible_targets)
        # Avoid voting for same-wolf if villager accidentally picks one (they don't know)
        return (f"我感觉{display_name_for_person(target)}最近有些不对劲", target)


    def jail_vote_target(self, target_name: str) -> dict:
        """Player (Crow) chooses who to jail after dusk votes. Returns result dict."""
        with self._lock:
            if self.phase != type(self.phase).DUSK_DISCUSSION:
                return {"error": "Not in dusk discussion phase"}
            if not self._dusk_vote_active:
                return {"error": "Dusk votes not yet generated"}
            if self._dusk_jail_target is not None:
                return {"error": f"Already chose to jail: {display_name_for_person(self._dusk_jail_target)}"}


            target = self.agents.get(target_name)
            if not target:
                return {"error": f"Unknown target: {target_name}"}
            if not target.is_alive:
                return {"error": f"{display_name_for_person(target_name)} is dead"}
            if target_name == self.detective_name:
                return {"error": "Cannot jail the detective"}
            if target_name in self._jailed:
                return {"error": f"{display_name_for_person(target_name)} is already jailed"}


            self._dusk_jail_target = target_name
            self._jailed.add(target_name)


            # Move jailed target to a prison cell
            self._place_in_prison(target_name)


            # Log the jail event
            self._log(f"🔒 Crow 决定拘留 {display_name_for_person(target_name)}！押送至监狱。", "action")


            # Emit final words from the jailed target (fallback)
            final_words = self._jailed_final_words(target_name)
            self._log(f"💬 {display_name_for_person(target_name)}（被拘留）: {final_words}", "chat")


            # Transition to night after a short delay (handled by tick)
            # The jail target has been chosen; dusk is effectively complete
            self._dusk_vote_active = False
            vote_summary = self._build_vote_summary()
            self._record_vote_history_snapshot(jail_target=target_name)
            self._log("Crow 押送嫌疑人回警长办公室。天马上黑了，大家回家锁好门。", "chat")
            self._transition_to_night()

            return {
                "success": True,
                "jailed": target_name,
                "jailed_display": display_name_for_person(target_name),
                "final_words": final_words,
                "vote_summary": vote_summary,
            }


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
        """Build a structured vote summary for get_status."""
        vote_counts = {}
        abstain_count = 0
        for voter, target in self._dusk_votes.items():
            if target:
                vote_counts[target] = vote_counts.get(target, 0) + 1
            else:
                abstain_count += 1


        # Sort by count descending
        sorted_votes = sorted(vote_counts.items(), key=lambda x: -x[1])


        return {
            "votes": dict(self._dusk_votes),
            "reasons": dict(self._dusk_vote_reasons),
            "counts": [{"target": t, "display": display_name_for_person(t), "count": c} for t, c in sorted_votes],
            "abstain_count": abstain_count,
            "active": self._dusk_vote_active,
            "jail_target": self._dusk_jail_target,
            "jail_target_display": display_name_for_person(self._dusk_jail_target) if self._dusk_jail_target else None,
        }


    def _record_vote_history_snapshot(self, jail_target: str | None = None) -> None:
        summary = self._build_vote_summary()
        entry = {
            "day": self.day,
            "votes": summary["votes"],
            "reasons": summary["reasons"],
            "counts": summary["counts"],
            "abstain_count": summary.get("abstain_count", 0),
            "jail_target": jail_target or self._dusk_jail_target,
            "jail_target_display": display_name_for_person(jail_target or self._dusk_jail_target) if (jail_target or self._dusk_jail_target) else None,
        }
        self._vote_history = [e for e in getattr(self, "_vote_history", []) if e.get("day") != self.day]
        self._vote_history.append(entry)


    # ==================== 每日任务 & 银器进展 ====================


