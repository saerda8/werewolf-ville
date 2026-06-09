"""Sheriff task/status helpers for WerewolfGameEngine."""


SILVER_JEWELRY_TASK_TEXT = "通过深挖女性角色获得银质项链"
SILVER_BULLET_TOOL_TASK_TEXT = "去五金店找到制造子弹的工具"
SILVER_CHOICE_TASK_TEXT = f"{SILVER_JEWELRY_TASK_TEXT}/{SILVER_BULLET_TOOL_TASK_TEXT}(二选一)"


class EngineTasksMixin:
    def _silver_task_text_for_status(self) -> tuple[str, bool]:
        """Return the task text and completion state for the current day."""
        bullet_done = bool(getattr(self, "_silver_bullet_acquired", False))
        jewelry_done = bool(getattr(self, "_silver_jewelry_acquired", False))
        done_today = bool(self._silver_task_done_for_today())

        if bullet_done and jewelry_done:
            return "银质项链和制造子弹的工具已收集齐", True
        if self.day >= 3:
            if bullet_done and not jewelry_done:
                return SILVER_JEWELRY_TASK_TEXT, False
            if jewelry_done and not bullet_done:
                return SILVER_BULLET_TOOL_TASK_TEXT, False
        return SILVER_CHOICE_TASK_TEXT, done_today

    def _build_daily_tasks(self) -> list[dict]:
        """Build structured daily tasks list for get_status()."""
        tasks = []

        required_interviews = {
            n for n, a in self.agents.items()
            if n != self.detective_name and a.is_alive and n not in self._jailed
        }
        done_interviews = self._daily_interviewed & required_interviews
        tasks.append({
            "id": "daily_interviews",
            "label": "每日采访所有居民",
            "description": f"采访所有存活、未被关押的居民（{len(required_interviews)}人）",
            "done": len(done_interviews),
            "total": len(required_interviews),
            "complete": len(done_interviews) >= len(required_interviews),
            "daily": True,
        })

        if self.day >= 2:
            bullet_done = bool(getattr(self, "_silver_bullet_acquired", False))
            jewelry_done = bool(getattr(self, "_silver_jewelry_acquired", False))
            silver_done_today = bool(self._silver_task_done_for_today())
            label, complete = self._silver_task_text_for_status()
            tasks.append({
                "id": "silver_resource_choice",
                "label": label,
                "description": label,
                "done": 1 if complete else 0,
                "total": 1,
                "complete": complete,
                "daily": False,
                "silver_bullet_acquired": bullet_done,
                "silver_jewelry_acquired": jewelry_done,
                "silver_task_done_today": self._silver_task_done_for_today(),
                "available_today": not silver_done_today and not (bullet_done and jewelry_done),
            })

            if self.day >= 4 and bullet_done and jewelry_done and not self._silver_bullet_crafted:
                tasks.append({
                    "id": "craft_silver_bullet",
                    "label": "制作银子弹",
                    "description": "使用制造子弹的工具和银质项链制作真正的银子弹",
                    "done": 0,
                    "total": 1,
                    "complete": False,
                    "daily": False,
                })

        return tasks
