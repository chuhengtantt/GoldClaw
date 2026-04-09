"""
GoldClaw 状态机测试。

覆盖 PRD 第 6 节所有状态转换逻辑：
- IDLE → WATCH（累积斜率阈值 / 斜率突变阈值）
- WATCH → TRIGGER（斜率突破 / TP/SL / 爆仓）
- WATCH → IDLE（超时退回）
- TRIGGER → IDLE（冷却期结束）
- 冷却机制
"""

import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from internal.state_machine.states import SystemState
from internal.state_machine.machine import StateMachine


@pytest.fixture
def sm() -> StateMachine:
    """默认参数的状态机。"""
    return StateMachine(
        threshold_a=0.003,
        threshold_b=0.005,
        watch_duration=5,
        trigger_slope=0.002,
        silence_period=30,
    )


# ============================================================
# IDLE → WATCH
# ============================================================

class TestIdleToWatch:
    """IDLE → WATCH 转换测试。"""

    def test_total_slope_exceeds_threshold_a(self, sm: StateMachine) -> None:
        """累积斜率超过 THRESHOLD_A → 进入 WATCH。"""
        new_state = sm.transition(
            current=SystemState.IDLE,
            current_price=3000,
            total_slope=0.004,  # > 0.003
            current_slope=0.001,
        )
        assert new_state == SystemState.WATCH
        assert sm.watch_start_price == 3000

    def test_slope_delta_exceeds_threshold_b(self, sm: StateMachine) -> None:
        """斜率突变超过 THRESHOLD_B → 进入 WATCH。"""
        # 第一次 tick 设置 prev_slope
        sm.transition(SystemState.IDLE, 3000, total_slope=0.001, current_slope=0.001)
        # 第二次 tick：current_slope - prev_slope = 0.008 - 0.001 = 0.007 > 0.005
        new_state = sm.transition(
            SystemState.IDLE, 3000, total_slope=0.001, current_slope=0.008,
        )
        assert new_state == SystemState.WATCH

    def test_no_trigger_when_below_thresholds(self, sm: StateMachine) -> None:
        """两个阈值都未突破 → 保持 IDLE。"""
        new_state = sm.transition(
            SystemState.IDLE, 3000, total_slope=0.001, current_slope=0.001,
        )
        assert new_state == SystemState.IDLE

    def test_total_slope_takes_priority(self, sm: StateMachine) -> None:
        """累积斜率和突变都满足时，累积斜率优先判断。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.001, current_slope=0.001)
        new_state = sm.transition(
            SystemState.IDLE, 3020, total_slope=0.005, current_slope=0.010,
        )
        assert new_state == SystemState.WATCH

    def test_watch_state_records_start_price(self, sm: StateMachine) -> None:
        """进入 WATCH 时记录起始金价和时间。"""
        sm.transition(SystemState.IDLE, 3050, total_slope=0.004, current_slope=0.001)
        assert sm.watch_start_price == 3050
        assert sm.watch_start_time is not None


# ============================================================
# WATCH → TRIGGER
# ============================================================

class TestWatchToTrigger:
    """WATCH → TRIGGER 转换测试。"""

    def test_slope_since_watch_exceeds_trigger(self, sm: StateMachine) -> None:
        """WATCH 期间斜率突破 → TRIGGER。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        # 价格上涨 0.3%: 3000 → 3009
        new_state = sm.transition(
            SystemState.WATCH, 3009, total_slope=0.005, current_slope=0.003,
            has_tp_sl_trigger=False, has_margin_call=False,
        )
        # 3009/3000 - 1 = 0.003 > trigger_slope 0.002
        assert new_state == SystemState.TRIGGER

    def test_tp_sl_triggers_immediately(self, sm: StateMachine) -> None:
        """TP/SL 触发 → 直接 TRIGGER，无视斜率。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        new_state = sm.transition(
            SystemState.WATCH, 3001, total_slope=0.004, current_slope=0.001,
            has_tp_sl_trigger=True, has_margin_call=False,
        )
        assert new_state == SystemState.TRIGGER

    def test_margin_call_triggers_immediately(self, sm: StateMachine) -> None:
        """爆仓 → 直接 TRIGGER。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        new_state = sm.transition(
            SystemState.WATCH, 3001, total_slope=0.004, current_slope=0.001,
            has_tp_sl_trigger=False, has_margin_call=True,
        )
        assert new_state == SystemState.TRIGGER

    def test_slope_not_enough_stays_watch(self, sm: StateMachine) -> None:
        """斜率不够 → 保持 WATCH。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        new_state = sm.transition(
            SystemState.WATCH, 3001, total_slope=0.004, current_slope=0.001,
            has_tp_sl_trigger=False, has_margin_call=False,
        )
        # 3001/3000 - 1 = 0.00033 < 0.002
        assert new_state == SystemState.WATCH


# ============================================================
# WATCH → IDLE (timeout)
# ============================================================

class TestWatchToIdle:
    """WATCH → IDLE 超时退回测试。"""

    def test_watch_timeout_returns_to_idle(self, sm: StateMachine) -> None:
        """超过 WATCH_DURATION 个 tick → 退回 IDLE。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        # 连续 watch_duration 个 tick，斜率不够
        for _ in range(sm.watch_duration):
            state = sm.transition(
                SystemState.WATCH, 3001, total_slope=0.004, current_slope=0.001,
                has_tp_sl_trigger=False, has_margin_call=False,
            )
        assert state == SystemState.IDLE
        assert sm.watch_start_price is None

    def test_watch_resets_on_reentry(self, sm: StateMachine) -> None:
        """重新进入 WATCH 时重置计时器。"""
        # 第一次进入 WATCH
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        # 超时退回
        for _ in range(sm.watch_duration):
            sm.transition(
                SystemState.WATCH, 3001, total_slope=0.004, current_slope=0.001,
                has_tp_sl_trigger=False, has_margin_call=False,
            )
        # 重新进入 WATCH
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        assert sm.watch_start_price == 3000
        assert sm._watch_ticks == 0


# ============================================================
# TRIGGER → IDLE (silence)
# ============================================================

class TestTriggerToIdle:
    """TRIGGER → IDLE 冷却期测试。"""

    def test_trigger_enters_silence(self, sm: StateMachine) -> None:
        """TRIGGER 后进入冷却期。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        sm.transition(
            SystemState.WATCH, 3010, total_slope=0.005, current_slope=0.003,
        )
        assert sm.silence_until is not None
        assert sm.is_silenced

    def test_trigger_stays_until_silence_over(self, sm: StateMachine) -> None:
        """冷却期未结束 → 保持 TRIGGER。"""
        sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        sm.transition(SystemState.WATCH, 3010, total_slope=0.005, current_slope=0.003)

        # 冷却期内 → 保持 TRIGGER
        new_state = sm.transition(SystemState.TRIGGER, 3010, total_slope=0.005, current_slope=0.003)
        assert new_state == SystemState.TRIGGER

    def test_returns_to_idle_after_silence(self, sm: StateMachine) -> None:
        """冷却期结束 → 回到 IDLE。"""
        sm._silence_until = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        new_state = sm.transition(SystemState.TRIGGER, 3010, total_slope=0.005, current_slope=0.003)
        assert new_state == SystemState.IDLE
        assert sm.silence_until is None


# ============================================================
# 完整循环
# ============================================================

class TestFullCycle:
    """IDLE → WATCH → TRIGGER → IDLE 完整循环。"""

    def test_full_cycle(self, sm: StateMachine) -> None:
        """完整三态循环。"""
        # IDLE → WATCH
        state = sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        assert state == SystemState.WATCH

        # WATCH → TRIGGER (价格涨到 3010, 0.33% > 0.2%)
        state = sm.transition(SystemState.WATCH, 3010, total_slope=0.006, current_slope=0.003)
        assert state == SystemState.TRIGGER

        # 冷却结束 → IDLE
        sm._silence_until = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        state = sm.transition(SystemState.TRIGGER, 3010, total_slope=0.006, current_slope=0.003)
        assert state == SystemState.IDLE

    def test_idle_watch_idle_timeout_cycle(self, sm: StateMachine) -> None:
        """IDLE → WATCH → IDLE（超时退回）。"""
        state = sm.transition(SystemState.IDLE, 3000, total_slope=0.004, current_slope=0.001)
        assert state == SystemState.WATCH

        for _ in range(sm.watch_duration):
            state = sm.transition(
                SystemState.WATCH, 3001, total_slope=0.004, current_slope=0.001,
                has_tp_sl_trigger=False, has_margin_call=False,
            )
        assert state == SystemState.IDLE
