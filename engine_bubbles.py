"""Engine-side bubble timing and compact display helpers."""

import time

from config_loader import load_config


CONFIG = load_config()


class EngineBubbleMixin:
    def _show_gathering_bubble(self, name: str, text: str) -> None:
        """Keep the active meeting speaker readable without covering the crowd."""
        for participant in getattr(self, "_gathering_queue", []):
            self.chat_bubbles.pop(participant, None)
        now = time.time()
        bubble_lifetime = float(CONFIG.get("game", {}).get("bubble_lifetime_seconds", 12))
        expired = [k for k, v in self.chat_bubbles.items() if now - v["time"] > bubble_lifetime]
        for k in expired:
            del self.chat_bubbles[k]
        self.chat_bubbles[name] = {"text": text, "time": time.time()}

    @staticmethod
    def _gathering_speech_visible_seconds() -> float:
        return float(CONFIG.get("game", {}).get("gathering_speech_visible_seconds", 2.5))

    @staticmethod
    def _crow_intro_line_delay(text: str) -> float:
        """Deterministic delay after each sheriff intro line is shown."""
        return float(CONFIG.get("game", {}).get("crow_intro_line_delay_seconds", 2.0))

    @staticmethod
    def _gathering_departure_gap_seconds() -> float:
        return float(CONFIG.get("game", {}).get("gathering_departure_gap_seconds", 1.0))

    @staticmethod
    def _departure_delay_seconds() -> float:
        return float(CONFIG.get("game", {}).get("npc_chat_delay_seconds", 1.0))

    def _expire_chat_bubbles(self) -> None:
        now = time.time()
        bubble_lifetime = float(CONFIG.get("game", {}).get("bubble_lifetime_seconds", 12))
        expired = [k for k, v in self.chat_bubbles.items() if now - v["time"] > bubble_lifetime]
        for k in expired:
            del self.chat_bubbles[k]

    @staticmethod
    def _summarize_thought_for_display(
        text: str,
        max_chars: int = 100,
        fallback: str = "正在整理当前情况。",
    ) -> str:
        """Keep private reasoning intact while exposing a compact complete-sentence summary."""
        thought = " ".join(str(text or "").strip().split())
        if len(thought) <= max_chars:
            return thought

        clauses = []
        current = ""
        for char in thought:
            current += char
            if char in "。.!！?？;；":
                clauses.append(current.strip())
                current = ""
        if current.strip():
            clauses.append(current.strip())

        shortened = ""
        for clause in clauses:
            candidate = shortened + clause
            if len(candidate) > max_chars:
                break
            shortened = candidate
        return shortened or fallback
