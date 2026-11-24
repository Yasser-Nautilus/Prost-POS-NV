# ruff: noqa: F811
"""Every action the React frontend sends must be routed by the real bridge.

The frontend mock (frontend/src/bridge.ts) hides a missing backend route, as
happened with get_driver_stats. This scans the frontend source for every
literal action name passed to call(...) and dispatches it through the real
POSBridge as admin: a routed action may fail validation, but must never come
back as an "unknown action" error.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_e2e_user_flows import (  # noqa: F401
    POSUserClient,
    _build_test_bridge,
    qapp,
    reset_db_singleton,
)

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
CALL = re.compile(r"""\bcall(?:<[^>()]*>)?\(\s*['"]([A-Za-z_][A-Za-z0-9_.]*)['"]""")
# call(cond ? "a" : "b", ...) passes one of two literal actions
TERNARY = re.compile(r"""\bcall(?:<[^>()]*>)?\([^'"\n,]*\?\s*['"]([A-Za-z_][A-Za-z0-9_.]*)['"]\s*:\s*['"]([A-Za-z_][A-Za-z0-9_.]*)['"]""")
# Calling these with an empty payload would end the test session itself.
SKIP = {"login", "logout"}


def frontend_actions() -> set[str]:
    found: set[str] = set()
    for path in list(SRC.rglob("*.ts")) + list(SRC.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        found.update(CALL.findall(text))
        for pair in TERNARY.findall(text):
            found.update(pair)
    return found - SKIP


def test_scanner_finds_known_actions():
    actions = frontend_actions()
    assert len(actions) > 60
    assert {"get_driver_stats", "complete_payment_split", "session.open",
            "check_in_driver", "check_out_driver"} <= actions


@pytest.mark.parametrize("action", sorted(frontend_actions()))
def test_frontend_action_is_routed_by_real_bridge(qapp, action):
    bridge, _db = _build_test_bridge(qapp)
    client = POSUserClient(bridge)
    assert client.call("login", {"pin": "1234"})["success"]
    raw = bridge.dispatch(action, json.dumps({}))
    result = json.loads(raw)
    assert "غير معروف" not in str(result.get("error", "")), (
        f"{action} is called by the frontend but not routed by the backend bridge: {result}"
    )
