# Reports — Progress

> **Last Updated:** 2026-11-20
> **Source of Truth:** `report_service.py`, `report_repository.py`, `reports_controller.py`

---

## Overview

The reporting system generates financial and operational reports at daily, shift-based, monthly, and yearly granularity. Reports are accessible through the React frontend and can be printed via the printing infrastructure.

---

## Report Types

### Daily Report

**Status:** Implemented

- Sales summary for a specific calendar date.
- Order counts by type (dine-in, takeaway, delivery, pickup).
- Payment method breakdown (cash, card, mobile).
- Total revenue, discounts, and tax.

### Shift-Based Report (B-10 Pattern)

**Status:** Implemented

- Revenue and order counts grouped by cashier shift boundaries (open/close timestamps).
- Queries use shift start and end times rather than calendar dates.
- Ensures reports align with actual cashier sessions even when shifts cross midnight.

> [!NOTE]
> The B-10 shift-based reporting pattern is a key distinction from simple date-based reports. `OrderRepository.get_orders_for_shift()` queries by shift timestamp range, not by calendar date.

### Monthly Report

**Status:** Implemented

- Aggregated monthly statistics across all days.
- Order counts, revenue totals, and payment breakdowns.

### Yearly Report

**Status:** Implemented

- Aggregated yearly statistics across all months.
- Order counts, revenue totals, and payment breakdowns.

---

## Bridge Integration

### ReportsController (`reports_controller.py` — 473 lines)

**Status:** Implemented

**Key actions:**
- Generate daily/shift/monthly/yearly reports.
- Print reports via `PrinterManager`.
- Validate date ranges and report parameters.
- Format report data for frontend display.

---

## Frontend Integration

### ReportsView

**Status:** Implemented

- Report type selection (daily, shift, monthly, yearly).
- Date/period picker.
- Report display with formatted tables.
- Print button integration.
- Access restricted to Manager+ roles.

---

## Summary

| Feature | Status |
|---|---|
| Daily reports | Implemented |
| Shift-based reports (B-10) | Implemented |
| Monthly reports | Implemented |
| Yearly reports | Implemented |
| Report printing | Implemented |
| Frontend (ReportsView) | Implemented |
| Bridge controller | Implemented |
