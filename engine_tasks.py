"""Sheriff task/status helpers for WerewolfGameEngine."""


class EngineTasksMixin:
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
            "description": f"采访所有存活、未被拘留的居民（{len(required_interviews)}人）",
            "done": len(done_interviews),
            "total": len(required_interviews),
            "complete": len(done_interviews) >= len(required_interviews),
            "daily": True,
        })

        if self.day >= 2:
            bullet_done = self._silver_bullet_acquired
            jewelry_done = self._silver_jewelry_acquired
            silver_done_today = bool(getattr(self, "_silver_task_done_today", None))
            tasks.append({
                "id": "silver_resource_choice",
                "label": "银器资源",
                "description": "通过深挖向 NPC 获取银制首饰，或前往五金店取得制造子弹的工具（二选一）。完成任意一项即完成。",
                "done": 1 if (silver_done_today or bullet_done or jewelry_done) else 0,
                "total": 1,
                "complete": silver_done_today or bullet_done or jewelry_done,
                "daily": False,
                "silver_bullet_acquired": bullet_done,
                "silver_jewelry_acquired": jewelry_done,
                "silver_task_done_today": getattr(self, "_silver_task_done_today", None),
                "available_today": not silver_done_today,
            })

            if self.day >= 4 and bullet_done and jewelry_done and not self._silver_bullet_crafted:
                tasks.append({
                    "id": "craft_silver_bullet",
                    "label": "制作银子弹",
                    "description": "使用银子弹工具和银饰物制作真正的银子弹",
                    "done": 0,
                    "total": 1,
                    "complete": False,
                    "daily": False,
                })

        return tasks
