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
            tasks.append({
                "id": "silver_bullet",
                "label": "获取银子弹工具",
                "description": "前往哈维橡树五金店，向亚瑟·伯顿获取银子弹工具",
                "done": 1 if bullet_done else 0,
                "total": 1,
                "complete": bullet_done,
                "daily": False,
            })

            jewelry_done = self._silver_jewelry_acquired
            tasks.append({
                "id": "silver_jewelry",
                "label": "获取银饰物",
                "description": "找到银饰物持有者并获取银饰物",
                "done": 1 if jewelry_done else 0,
                "total": 1,
                "complete": jewelry_done,
                "daily": False,
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

        if self.day == 2:
            tasks.append({
                "id": "day2_objective",
                "label": "第二天目标",
                "description": "前往哈维橡树五金店获取银子弹工具，或找到银饰物持有者",
                "done": 1 if (bullet_done or jewelry_done) else 0,
                "total": 1,
                "complete": (bullet_done or jewelry_done),
                "daily": False,
            })
        elif self.day == 3:
            missing = []
            if not self._silver_bullet_acquired:
                missing.append("银子弹工具")
            if not self._silver_jewelry_acquired:
                missing.append("银饰物")
            tasks.append({
                "id": "day3_objective",
                "label": "第三天目标",
                "description": f"获取缺失的银器: {'、'.join(missing)}" if missing else "银器已齐全",
                "done": 0 if missing else 1,
                "total": 1,
                "complete": not bool(missing),
                "daily": False,
            })

        return tasks
