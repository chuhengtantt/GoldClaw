"""
GoldClaw 状态机 — IDLE / WATCH / TRIGGER 转换逻辑。

设计思想：惯性确认。通过双重阈值过滤瞬时噪音，只在真正趋势形成时介入。

三态：
- IDLE（常态巡航，15 分钟）：监控累积斜率 + 斜率突变
- WATCH（高频盯盘，3 分钟）：确认波动持续性
- TRIGGER（即时执行）：触发操作 + 冷却期
"""

import logging
from datetime import datetime, timezone

from internal.state_machine.states import SystemState

logger = logging.getLogger(__name__)


class StateMachine:
    """状态机：管理 IDLE → WATCH → TRIGGER → IDLE 的转换。"""

    def __init__(
        self,
        threshold_a: float = 0.003,
        threshold_b: float = 0.005,
        watch_duration: int = 5,
        trigger_slope: float = 0.002,
        silence_period: int = 30,
    ) -> None:
        """
        Args:
            threshold_a: 累积斜率阈值（IDLE → WATCH）。
            threshold_b: 斜率突变阈值（IDLE → WATCH）。
            watch_duration: WATCH 最长观察期（tick 数）。
            trigger_slope: WATCH → TRIGGER 的斜率阈值。
            silence_period: 冷却期（分钟）。
        """
        self.threshold_a = threshold_a
        self.threshold_b = threshold_b
        self.watch_duration = watch_duration
        self.trigger_slope = trigger_slope
        self.silence_period = silence_period

        # WATCH 阶段追踪
        self._watch_ticks: int = 0
        self._watch_start_price: float | None = None
        self._watch_start_time: str | None = None

        # 冷却期
        self._silence_until: str | None = None

        # 上一周期斜率（用于 Slope_Delta 计算）
        self._prev_slope: float = 0.0

    def transition(
        self,
        current: SystemState,
        current_price: float,
        total_slope: float,
        current_slope: float,
        has_tp_sl_trigger: bool = False,
        has_margin_call: bool = False,
    ) -> SystemState:
        """
        根据输入参数决定状态转换。

        Args:
            current: 当前状态。
            current_price: 当前金价。
            total_slope: CYCLE_X 窗口内累积斜率。
            current_slope: 最近短周期斜率。
            has_tp_sl_trigger: 是否触及 TP/SL。
            has_margin_call: 是否爆仓。

        Returns:
            转换后的新状态。
        """
        if current == SystemState.IDLE:
            return self._from_idle(current_price, total_slope, current_slope)
        elif current == SystemState.WATCH:
            return self._from_watch(current_price, has_tp_sl_trigger, has_margin_call)
        elif current == SystemState.TRIGGER:
            return self._from_trigger()
        return current

    def _from_idle(
        self, current_price: float, total_slope: float, current_slope: float
    ) -> SystemState:
        """IDLE → WATCH 判定。"""
        slope_delta = abs(current_slope - self._prev_slope)
        self._prev_slope = current_slope

        if total_slope > self.threshold_a:
            logger.info(
                "IDLE→WATCH: total_slope=%.6f > threshold_a=%.6f",
                total_slope, self.threshold_a,
            )
            self._enter_watch(current_price)
            return SystemState.WATCH

        if slope_delta > self.threshold_b:
            logger.info(
                "IDLE→WATCH: slope_delta=%.6f > threshold_b=%.6f",
                slope_delta, self.threshold_b,
            )
            self._enter_watch(current_price)
            return SystemState.WATCH

        return SystemState.IDLE

    def _from_watch(
        self,
        current_price: float,
        has_tp_sl_trigger: bool,
        has_margin_call: bool,
    ) -> SystemState:
        """WATCH → TRIGGER 或 WATCH → IDLE 判定。"""
        self._watch_ticks += 1

        # 紧急事件：TP/SL 或爆仓 → 直接 TRIGGER
        if has_tp_sl_trigger or has_margin_call:
            reason = "margin_call" if has_margin_call else "tp_sl"
            logger.warning("WATCH→TRIGGER: emergency (%s)", reason)
            self._enter_silence()
            return SystemState.TRIGGER

        # 计算从 WATCH 开始到现在的斜率
        if self._watch_start_price and self._watch_start_price > 0:
            slope_since_watch = (
                (current_price - self._watch_start_price) / self._watch_start_price
            )
            if slope_since_watch > self.trigger_slope:
                logger.info(
                    "WATCH→TRIGGER: slope_since_watch=%.6f > trigger_slope=%.6f",
                    slope_since_watch, self.trigger_slope,
                )
                self._enter_silence()
                return SystemState.TRIGGER

        # 超时退回 IDLE
        if self._watch_ticks >= self.watch_duration:
            logger.info("WATCH→IDLE: timeout after %d ticks", self._watch_ticks)
            self._reset_watch()
            return SystemState.IDLE

        return SystemState.WATCH

    def _from_trigger(self) -> SystemState:
        """TRIGGER → IDLE（冷却期结束后）。"""
        if self._silence_until and not self._is_silenced():
            logger.info("TRIGGER→IDLE: silence period over")
            self._silence_until = None
            return SystemState.IDLE
        return SystemState.TRIGGER

    def _enter_watch(self, price: float) -> None:
        """进入 WATCH 状态，重置追踪变量。"""
        self._watch_ticks = 0
        self._watch_start_price = price
        self._watch_start_time = datetime.now(timezone.utc).isoformat()

    def _reset_watch(self) -> None:
        """重置 WATCH 追踪变量。"""
        self._watch_ticks = 0
        self._watch_start_price = None
        self._watch_start_time = None

    def _enter_silence(self) -> None:
        """进入冷却期。"""
        from datetime import timedelta
        end = datetime.now(timezone.utc) + timedelta(minutes=self.silence_period)
        self._silence_until = end.isoformat()
        self._reset_watch()

    def _is_silenced(self) -> bool:
        """当前是否在冷却期内。"""
        if not self._silence_until:
            return False
        return datetime.now(timezone.utc).isoformat() < self._silence_until

    @property
    def is_silenced(self) -> bool:
        """当前是否在冷却期内（公开接口）。"""
        return self._is_silenced()

    @property
    def watch_start_price(self) -> float | None:
        return self._watch_start_price

    @property
    def watch_start_time(self) -> str | None:
        return self._watch_start_time

    @property
    def silence_until(self) -> str | None:
        return self._silence_until

    @property
    def prev_slope(self) -> float:
        return self._prev_slope
