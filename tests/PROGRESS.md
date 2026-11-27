# Tests — Progress

> **Last Updated:** 2026-11-26
> **Source of Truth:** File listing of `tests/` directory

---

## Overview

The test suite contains **23 test files** with a combined **6,369 lines** of test code. Tests cover services, controllers, integration scenarios, and the v2 feature phases.

> [!CAUTION]
> **Tests have NOT been executed.** Pass/fail status is unknown. The information below describes what the test files contain based on file names and structure, not verified test results.

---

## Test Files

| # | File | Description |
|---|---|---|
| 1 | `test_b01_order_service.py` | Order service unit tests |
| 2 | `test_b02_financial_service.py` | Financial service unit tests |
| 3 | `test_b03_delivery_service.py` | Delivery service unit tests |
| 4 | `test_b04_customer_service.py` | Customer service unit tests |
| 5 | `test_b05_auth_service.py` | Authentication service unit tests |
| 6 | `test_b06_product_service.py` | Product service unit tests |
| 7 | `test_b07_integration.py` | Cross-service integration tests |
| 8 | `test_b08_order_completion.py` | Order completion flow tests |
| 9 | `test_b09_report_service.py` | Report service unit tests |
| 10 | `test_b10_shift_reports.py` | Shift-based reporting tests (B-10 pattern) |
| 11 | `test_b11_cashier_session.py` | Cashier session service tests |
| 12 | `test_b12_cash_ledger.py` | Cash ledger repository and integration tests |
| 13 | `test_b13_business_day.py` | Business day service tests (X/Z reports, close) |
| 14 | `test_b14_driver_settlement.py` | Driver settlement service tests |
| 15 | `test_b15_audit.py` | Audit service tests |
| 16 | `test_b16_session_controller.py` | Session controller bridge tests |
| 17 | `test_b17_reports_controller.py` | Reports controller bridge tests |
| 18 | `test_b18_order_lifecycle.py` | End-to-end order lifecycle tests |
| 19 | `test_b19_permissions.py` | Permission and authorization tests |
| 20 | `test_v2_phase1.py` | V2 phase 1 feature tests |
| 21 | `test_v2_phase2.py` | V2 phase 2 feature tests |
| 22 | `test_v2_phase3.py` | V2 phase 3 feature tests |
| 23 | `test_v2_phase4.py` | V2 phase 4 feature tests |
|    | `test_v2_phase5.py` | V2 phase 5 feature tests |

---

## Coverage Areas

Based on file names, the test suite covers:

- **Core services:** Order, financial, delivery, customer, auth, product, report, audit.
- **New services:** Cashier session, cash ledger, business day, driver settlement.
- **Controllers:** Session controller, reports controller.
- **Integration:** Cross-service workflows, order lifecycle end-to-end.
- **Permissions:** Authorization and role-based access.
- **V2 phases:** Incremental feature development tests (phases 1–5).

---

## Statistics

| Metric | Value |
|---|---|
| Total test files | 23 |
| Total lines | 6,369 |
| Execution status | **Not executed** |
| Pass/fail | **Unknown** |

---

## Recommendations

1. Execute the full test suite and record results.
2. Measure code coverage.
3. Identify and fix any failing tests.
4. Add frontend tests (currently no React/TypeScript tests exist).
5. Add printing infrastructure tests (mocked, since hardware is unavailable).

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26.

- Suite grew past 800 tests (814 test functions on 2026-11-26). New files include regression tests for the driver picker, duplicate names, QA findings, and combined audit fixes [#67, #92, #97, #108].
- `tests/test_frontend_bridge_actions.py` checks every frontend action is routed in the real `POSBridge`; `tests/test_visible_flows_extended.py` runs rendered UI flows (split payment, repeat customer, park/resume) through the real React app, QWebChannel bridge and SQLite [#102].
- CI installs a headless Qt runtime so the Qt bridge tests run in GitHub Actions [#93, #110].
