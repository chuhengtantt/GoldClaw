"""
GoldClaw 调度器 — APScheduler 双频率调度。

IDLE 状态：每 15 分钟
WATCH 状态：每 3 分钟
状态切换时动态调整频率。
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from internal.state_machine.states import SystemState

logger = logging.getLogger(__name__)


class GoldClawScheduler:
    """调度器：管理双频率 tick。"""

    def __init__(self, engine: "Engine") -> None:  # noqa: F821
        self._engine = engine
        self._scheduler = BackgroundScheduler()
        self._current_interval = settings.schedule_interval_idle
        self._idle_interval = settings.schedule_interval_idle
        self._watch_interval = settings.schedule_interval_watch
        self._job_id = "goldclaw_tick"

    def start(self) -> None:
        """启动调度器，使用 IDLE 频率。"""
        self._scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(minutes=self._current_interval),
            id=self._job_id,
            name="GoldClaw tick",
            max_instances=1,
        )
        self._scheduler.start()
        logger.info(
            "Scheduler started: interval=%d min, state=%s",
            self._current_interval,
            self._engine.system_state.value,
        )

    def _tick(self) -> None:
        """调度器触发的 tick。执行后检查是否需要切换频率。"""
        self._engine.run_tick()
        self._adjust_interval()

    def _adjust_interval(self) -> None:
        """根据当前状态调整调度频率。"""
        state = self._engine.system_state

        if state == SystemState.WATCH:
            target = self._watch_interval
        else:
            target = self._idle_interval

        if target != self._current_interval:
            self._reschedule(target)

    def _reschedule(self, minutes: int) -> None:
        """重新设定调度间隔。"""
        self._current_interval = minutes
        self._scheduler.reschedule_job(
            self._job_id,
            trigger=IntervalTrigger(minutes=minutes),
        )
        logger.info("Scheduler rescheduled: interval=%d min", minutes)

    def update_intervals(self, idle_min: int, watch_min: int) -> None:
        """外部调用：更新调度频率并立即生效。"""
        self._idle_interval = idle_min
        self._watch_interval = watch_min
        state = self._engine.system_state
        target = watch_min if state == SystemState.WATCH else idle_min
        if target != self._current_interval:
            self._reschedule(target)

    def shutdown(self) -> None:
        """关闭调度器。"""
        self._scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
