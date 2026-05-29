# 💵 feature/financial — PROGRESS

## 🎯 Goal
Implement the **Financial View** (`financial_view.py`) to manage the shift lifecycle (open, transfer, close), log immutable cash expenses, and view historical shift summaries.

---

## Task List

### 1. Open Shift View State
- **What**: Interface to open a shift when none is active.
- **Details**:
  - Show message explaining that opening resets invoice counter to #1.
  - Large button "Open Shift / فتح الوردية".
  - Triggers `financial_service.open_shift(user_id)`.
- **Status**: `Done`

### 2. Active Shift Dashboard Metrics
- **What**: Live metrics panel for active shift.
- **Details**:
  - Metric summary cards: Total Sales, Total Expenses, Pending Orders (Delivery, Dine-In, Kitchen), Expected Cash.
  - Periodic auto-refresh to update the values.
- **Status**: `Done`

### 3. Expense Entry Form & Table
- **What**: Form to log cash-out expenses and display daily log.
- **Details**:
  - Fields: Amount (double validator), Category dropdown (delivery_fees, supplies, other), Description.
  - Save button: calls `financial_service.add_expense()`.
  - Display table below showing time, category, description, and amount. Immutable (no edit/delete).
- **Status**: `Done`

### 4. Shift Transfer (Mid-Day Handover)
- **What**: Transfer shift cash accountability to another cashier.
- **Details**:
  - Manager PIN override validation.
  - Dropdown to select next cashier.
  - Prints shift transfer report (تقرير تسليم وردية).
  - Snapshot recorded in DB.
- **Status**: `Done`

### 5. Close Shift (End-of-Day Reconciliation)
- **What**: Close active shift and print final report.
- **Details**:
  - Manager PIN override validation.
  - Enforce prerequisites: all driver trips settled, daily summary printed.
  - Displays Expected Cash verification summary.
  - Prints shift close summary, closes shift in DB (resets invoice numbers to #1 for next shift).
- **Status**: `Done`

### 6. Shift History Tab
- **What**: View past shifts.
- **Details**:
  - Table listing completed shifts: ID, Cashier, Opened At, Closed At, Closed By, Expected Cash.
- **Status**: `Done`
