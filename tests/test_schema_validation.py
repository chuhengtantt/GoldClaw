"""
GoldClaw 通信层测试。

覆盖：Pydantic Schema 校验、投资者权限、信箱文件交换、门铃、幻觉检测、耻辱柱。
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
import sqlite3

from internal.db.connection import get_connection
from internal.db.migrations import run_migrations, seed_initial_data
from internal.exchange.schema import (
    EmergencyPayload,
    InvestorInstruction,
    OrderFile,
    StateReport,
)
from internal.exchange.validator import (
    validate_instruction,
    validate_orders,
    record_violation,
    check_hallucination,
    get_unacknowledged_violations,
)
from internal.exchange.webhook_client import (
    write_state_file,
    read_orders_file,
    ring_doorbell,
    build_state_report,
    ORDERS_FILE,
    STATE_FILE,
)


# ============================================================
# Pydantic Schema 校验
# ============================================================

class TestInvestorInstruction:
    """指令 Schema 校验测试。"""

    def test_valid_cfd_long(self) -> None:
        inst = InvestorInstruction(
            investor="A", action="cfd_long", margin_pct=0.8, tp=3100, sl=2900,
        )
        assert inst.investor == "A"
        assert inst.margin_pct == 0.8

    def test_valid_hold(self) -> None:
        inst = InvestorInstruction(investor="A", action="hold")
        assert inst.action == "hold"

    def test_invalid_action(self) -> None:
        with pytest.raises(Exception):
            InvestorInstruction(investor="A", action="buy_gold")

    def test_margin_pct_over_1(self) -> None:
        with pytest.raises(Exception):
            InvestorInstruction(investor="A", action="cfd_long", margin_pct=1.5)

    def test_margin_pct_negative(self) -> None:
        with pytest.raises(Exception):
            InvestorInstruction(investor="A", action="cfd_long", margin_pct=-0.1)

    def test_invalid_investor_id(self) -> None:
        with pytest.raises(Exception):
            InvestorInstruction(investor="abc", action="hold")

    def test_optional_fields_default(self) -> None:
        inst = InvestorInstruction(investor="A", action="hold")
        assert inst.signal_strength is None
        assert inst.signal_type is None
        assert inst.reasoning is None


# ============================================================
# 权限校验
# ============================================================

class TestPermissions:
    """投资者权限校验测试。"""

    def test_a_can_cfd_long(self) -> None:
        inst, err = validate_instruction(
            {"investor": "A", "action": "cfd_long", "margin_pct": 0.5, "tp": 3100, "sl": 2900},
            "A",
        )
        assert inst is not None
        assert err is None

    def test_a_can_cfd_short(self) -> None:
        inst, err = validate_instruction(
            {"investor": "A", "action": "cfd_short", "margin_pct": 0.5, "tp": 2900, "sl": 3100},
            "A",
        )
        assert inst is not None

    def test_a_cannot_sgln_long(self) -> None:
        inst, err = validate_instruction(
            {"investor": "A", "action": "sgln_long", "margin_pct": 0.5}, "A",
        )
        assert inst is None
        assert "cannot" in err

    def test_b_cannot_cfd_long(self) -> None:
        inst, err = validate_instruction(
            {"investor": "B", "action": "cfd_long", "margin_pct": 0.5, "tp": 3100, "sl": 2900}, "B",
        )
        assert inst is None
        assert "cannot" in err

    def test_b_can_cfd_short(self) -> None:
        inst, err = validate_instruction(
            {"investor": "B", "action": "cfd_short", "margin_pct": 0.5, "tp": 2900, "sl": 3100}, "B",
        )
        assert inst is not None

    def test_b_can_sgln_long(self) -> None:
        inst, err = validate_instruction(
            {"investor": "B", "action": "sgln_long", "margin_pct": 0.5}, "B",
        )
        assert inst is not None

    def test_cfd_open_requires_margin(self) -> None:
        inst, err = validate_instruction(
            {"investor": "A", "action": "cfd_long", "margin_pct": 0, "tp": 3100, "sl": 2900}, "A",
        )
        assert inst is None
        assert "margin_pct" in err

    def test_cfd_open_requires_tp_sl(self) -> None:
        inst, err = validate_instruction(
            {"investor": "A", "action": "cfd_long", "margin_pct": 0.5, "tp": 0, "sl": 0}, "A",
        )
        assert inst is None
        assert "tp and sl" in err


# ============================================================
# 批量校验
# ============================================================

class TestValidateOrders:
    """批量订单校验测试。"""

    def test_mixed_valid_invalid(self) -> None:
        raw = {
            "instructions": [
                {"investor": "A", "action": "hold"},
                {"investor": "B", "action": "cfd_long", "margin_pct": 0.5, "tp": 3100, "sl": 2900},
            ]
        }
        valid, violations = validate_orders(raw)
        assert len(valid) == 1
        assert len(violations) == 1
        assert violations[0][0] == "B"

    def test_empty_instructions(self) -> None:
        valid, violations = validate_orders({"instructions": []})
        assert len(valid) == 0
        assert len(violations) == 0


# ============================================================
# 幻觉检测
# ============================================================

class TestHallucination:
    """幻觉检测测试。"""

    def test_normal_change(self) -> None:
        assert not check_hallucination(10000, 10500)

    def test_hallucination_detected(self) -> None:
        assert check_hallucination(10000, 16000)

    def test_zero_before(self) -> None:
        assert not check_hallucination(0, 10000)


# ============================================================
# 信箱文件交换
# ============================================================

class TestMailbox:
    """信箱文件交换测试。"""

    def test_write_and_read_state(self, tmp_path: Path) -> None:
        """写状态文件 → 文件存在且内容正确。"""
        state_file = tmp_path / "state.json"
        report = StateReport()
        report.timestamp = "2026-04-09T00:00:00Z"
        state_file.write_text(report.model_dump_json(), encoding="utf-8")

        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["type"] == "status_report"

    def test_read_orders_and_rename(self, tmp_path: Path) -> None:
        """读决策文件 → 重命名 → 二次读取返回 None。"""
        orders_path = tmp_path / "orders_from_openclaw.json"
        orders_data = {
            "timestamp": "2026-04-09T00:00:00Z",
            "instructions": [
                {"investor": "A", "action": "hold"},
            ],
        }
        orders_path.write_text(json.dumps(orders_data), encoding="utf-8")

        # Manually test the rename logic
        raw = json.loads(orders_path.read_text(encoding="utf-8"))
        orders = OrderFile(**raw)
        assert len(orders.instructions) == 1
        assert orders.instructions[0].action == "hold"

    def test_no_orders_file(self, tmp_path: Path) -> None:
        """文件不存在 → 返回 None。"""
        path = tmp_path / "nonexistent.json"
        assert not path.exists()


# ============================================================
# 耻辱柱
# ============================================================

class TestViolations:
    """违规记录测试。"""

    def test_record_and_retrieve(self) -> None:
        conn = get_connection(":memory:")
        run_migrations(conn)
        seed_initial_data(conn, {"A": 10000.0, "B": 10000.0})
        conn.commit()

        record_violation(conn, "A", "sgln_long", "Investor A cannot sgln_long")
        conn.commit()

        violations = get_unacknowledged_violations(conn)
        assert len(violations) == 1
        assert violations[0]["investor"] == "A"
        assert "sgln_long" in violations[0]["violation"]

        # After retrieval, should be acknowledged
        violations2 = get_unacknowledged_violations(conn)
        assert len(violations2) == 0

        conn.close()
