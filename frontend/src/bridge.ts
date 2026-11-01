// TypeScript wrapper for the QWebChannel bridge.
// Automatically falls back to high-fidelity mock data when running outside QWebEngineView.

export interface BridgeResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// ── v2 Session Types ──────────────────────────────────────────────────────

export type SessionStation = 'ALL' | 'COUNTER' | 'DELIVERY';

export interface CashierSession {
  id: number;
  day_id: number;
  user_id: number;
  station: SessionStation;
  is_open: boolean;
  opened_at: string;
  closed_at: string | null;
  opening_float_pt: number;
  opening_float_egp: number;
  counted_cash_pt: number | null;
  counted_cash_egp: number | null;
  expected_cash_pt: number | null;
  expected_cash_egp: number | null;
  variance_pt: number | null;
  variance_egp: number | null;
}

export interface LedgerBreakdownEntry {
  pt: number;
  egp: number;
}

export interface SessionSnapshot {
  session_id: number;
  user_id: number;
  station: SessionStation;
  is_open: boolean;
  opened_at: string;
  closed_at: string | null;
  opening_float_pt: number;
  opening_float_egp: number;
  expected_cash_pt: number;
  expected_cash_egp: number;
  counted_cash_pt: number | null;
  counted_cash_egp: number | null;
  variance_pt: number | null;
  variance_egp: number | null;
  breakdown: Record<string, LedgerBreakdownEntry>;
}

export interface XReportTotals {
  expected_cash_pt: number;
  expected_cash_egp: number;
  cash_sales_pt: number;
  cash_sales_egp: number;
  driver_remittance_pt: number;
  driver_remittance_egp: number;
  expenses_pt: number;
  expenses_egp: number;
}

export interface XReport {
  type: 'X' | 'Z';
  day_id: number;
  generated_at: string;
  sessions: SessionSnapshot[];
  totals: XReportTotals;
}

export interface ZReport extends XReport {
  type: 'Z';
  day_closed_at: string;
  total_variance_pt: number;
  total_variance_egp: number;
}

// ─────────────────────────────────────────────────────────────────────────

type SignalCallback = (data: any) => void;

class POSBridgeClient {
  private backend: any = null;
  private channelReady: Promise<any>;
  private signalListeners: { [key: string]: Set<SignalCallback> } = {
    orderChanged: new Set(),
    parkedChanged: new Set(),
    tableStateChanged: new Set(),
    shiftStatusChanged: new Set(),
  };

  // Mock database state for local browser development
  private mockState = {
    currentUser: null as any,
    currentOrder: null as any,
    parkedOrders: [] as any[],
    activeOrders: [] as any[],
    activeShift: null as any,
    closedShifts: [] as any[],
    expenses: [] as any[],
    users: [
      { id: 1, username: "admin", display_name: "ياسر (مدير النظام)", role: "admin", cashier_slot: 1, is_active: true, pin: "1234" },
      { id: 2, username: "manager", display_name: "مدير المطعم", role: "manager", cashier_slot: 1, is_active: true, pin: "5555" },
      { id: 3, username: "cashier1", display_name: "كاشير الوردية", role: "cashier", cashier_slot: 1, is_active: true, pin: "1111" }
    ] as any[],
    drivers: [
      { id: 10, username: "driver1", display_name: "أحمد (طيار)", role: "cashier", cashier_slot: null, is_active: true, is_checked_in: true },
      { id: 11, username: "driver2", display_name: "محمد (طيار)", role: "cashier", cashier_slot: null, is_active: true, is_checked_in: true },
      { id: 12, username: "driver3", display_name: "علي (طيار)", role: "cashier", cashier_slot: null, is_active: true, is_checked_in: true }
    ] as any[],
    trips: [] as any[],
    zones: [
      { id: 1, name: "مدينة فاقوس", delivery_fee: 15.0, is_active: true },
      { id: 2, name: "شارع الانتاج", delivery_fee: 10.0, is_active: true },
      { id: 3, name: "الغابة", delivery_fee: 25.0, is_active: true },
      { id: 4, name: "كفر البلاسي", delivery_fee: 12.0, is_active: true }
    ],
    customers: [
      {
        id: 1,
        name: "ياسر المصري",
        phone: "01012345678",
        notes: "بدون كاتشب",
        addresses: [
          { id: 1, customer_id: 1, street_name: "شارع المشالي", zone_id: 1, zone_name: "مدينة فاقوس", delivery_fee: 15.0 }
        ]
      }
    ],
    categories: [
      { id: 1, name: "عروض البروست", sort_order: 1, is_active: true },
      { id: 2, name: "وجبات فردية", sort_order: 2, is_active: true },
      { id: 3, name: "عائلي", sort_order: 3, is_active: true },
      { id: 4, name: "سندوتشات", sort_order: 4, is_active: true },
      { id: 5, name: "مشروبات ومقبلات", sort_order: 5, is_active: true }
    ],
    products: [
      { id: 101, category_id: 1, name: "عرض سوبر بروست 4 قطع", price: 160.0, is_active: true, sort_order: 1 },
      { id: 102, category_id: 1, name: "عرض بروست حار 8 قطع", price: 290.0, is_active: true, sort_order: 2 },
      { id: 103, category_id: 2, name: "وجبة بروست 3 قطع عادي", price: 130.0, is_active: true, sort_order: 1 },
      { id: 104, category_id: 2, name: "وجبة دينر 4 قطع حار", price: 170.0, is_active: true, sort_order: 2 },
      { id: 105, category_id: 3, name: "وجبة التوفير 12 قطعة", price: 420.0, is_active: true, sort_order: 1 },
      { id: 106, category_id: 3, name: "وجبة العيلة 16 قطعة", price: 540.0, is_active: true, sort_order: 2 },
      { id: 107, category_id: 4, name: "سندوتش زنجر سوبريم", price: 95.0, is_active: true, sort_order: 1 },
      { id: 108, category_id: 4, name: "سندوتش تويستر بروست", price: 75.0, is_active: true, sort_order: 2 },
      { id: 109, category_id: 5, name: "بطاطس وسط", price: 30.0, is_active: true, sort_order: 1 },
      { id: 110, category_id: 5, name: "كول سلو", price: 25.0, is_active: true, sort_order: 2 },
      { id: 111, category_id: 5, name: "بيبسي كانز", price: 20.0, is_active: true, sort_order: 3 },
    ]
  };

  constructor() {
    this.channelReady = this._initChannel();
  }

  private _initChannel(): Promise<boolean> {
    return new Promise((resolve) => {
      const w = window as any;

      // If no Qt WebChannel transport is present → browser / mock mode
      if (!w.qt || !w.qt.webChannelTransport) {
        console.warn("[Bridge] No qt.webChannelTransport found. Using MOCK backend.");
        resolve(false);
        return;
      }

      // Poll for QWebChannel class (injected by QWebEngineScript at DocumentCreation)
      let attempts = 0;
      const maxAttempts = 100; // 10 seconds total

      const tryInit = () => {
        attempts++;
        if (w.QWebChannel) {
          new w.QWebChannel(w.qt.webChannelTransport, (channel: any) => {
            this.backend = channel.objects.backend;
            console.log("[Bridge] QWebChannel connected to Python backend ✓");

            // Wire signals
            if (this.backend.orderChanged)
              this.backend.orderChanged.connect((d: string) => this.notifyListeners("orderChanged", JSON.parse(d)));
            if (this.backend.parkedChanged)
              this.backend.parkedChanged.connect((d: string) => this.notifyListeners("parkedChanged", JSON.parse(d)));
            if (this.backend.tableStateChanged)
              this.backend.tableStateChanged.connect((d: string) => this.notifyListeners("tableStateChanged", JSON.parse(d)));
            if (this.backend.shiftStatusChanged)
              this.backend.shiftStatusChanged.connect((d: string) => this.notifyListeners("shiftStatusChanged", JSON.parse(d)));

            resolve(true);
          });
        } else if (attempts < maxAttempts) {
          setTimeout(tryInit, 100);
        } else {
          console.error("[Bridge] QWebChannel class never appeared. Falling back to MOCK.");
          resolve(false);
        }
      };

      tryInit();
    });
  }


  public async call<T = any>(action: string, payload: any = {}): Promise<T> {
    const isNative = await this.channelReady;
    if (isNative && this.backend) {
      return new Promise((resolve, reject) => {
        this.backend.dispatch(action, JSON.stringify(payload), (responseJson: string) => {
          try {
            const res: BridgeResponse<T> = JSON.parse(responseJson);
            if (res.success) {
              resolve(res.data as T);
            } else {
              reject(new Error(res.error || "خطأ غير معروف في الخادم"));
            }
          } catch (e) {
            reject(new Error("فشل في معالجة رد الخادم: " + e));
          }
        });
      });
    } else {
      // Mock Implementation
      return this.dispatchMock<T>(action, payload);
    }
  }

  public subscribe(signal: string, callback: SignalCallback) {
    if (this.signalListeners[signal]) {
      this.signalListeners[signal].add(callback);
    }
  }

  public unsubscribe(signal: string, callback: SignalCallback) {
    if (this.signalListeners[signal]) {
      this.signalListeners[signal].delete(callback);
    }
  }

  // ── v2 Session API helpers ─────────────────────────────────────────────

  /** Open a new cashier session for the current business day. */
  public sessionOpen(params: {
    day_id?: number;
    user_id?: number;
    station?: SessionStation;
    opening_float_egp?: number;
  }): Promise<CashierSession> {
    return this.call<CashierSession>('session.open', params);
  }

  /** Close a cashier session with a blind cash count. */
  public sessionClose(params: {
    session_id: number;
    counted_cash_egp: number;
    variance_reason?: string;
    manager_pin?: string;
  }): Promise<CashierSession> {
    return this.call<CashierSession>('session.close', params);
  }

  /** Handover: atomically close outgoing and open new session. */
  public sessionHandover(params: {
    from_session_id: number;
    to_user_id: number;
    station?: SessionStation;
    counted_cash_egp: number;
    cash_drop_egp?: number;
    variance_reason?: string;
    manager_pin?: string;
  }): Promise<{ closed: CashierSession; new: CashierSession }> {
    return this.call('session.handover', params);
  }

  /** Get all open sessions for the current business day. */
  public sessionGetActive(day_id?: number): Promise<CashierSession[]> {
    return this.call<CashierSession[]>('session.get_active', { day_id });
  }

  /** Get all sessions (open + closed) for the current business day. */
  public sessionGetAll(day_id?: number): Promise<CashierSession[]> {
    return this.call<CashierSession[]>('session.get_all', { day_id });
  }

  /** Get live expected cash balance for a session (from ledger). */
  public sessionGetBalance(session_id: number): Promise<{
    session_id: number;
    balance_pt: number;
    balance_egp: number;
    is_open: boolean | null;
  }> {
    return this.call('session.get_balance', { session_id });
  }

  /** X-Report: live ledger snapshot for the business day. */
  public sessionXReport(day_id?: number): Promise<XReport> {
    return this.call<XReport>('session.x_report', { day_id });
  }

  /** Z-Report: close business day and get final ledger snapshot. */
  public sessionCloseDay(params: {
    day_id?: number;
    manager_pin?: string;
  }): Promise<ZReport> {
    return this.call<ZReport>('session.close_day', params);
  }

  private notifyListeners(signal: string, data: any) {
    if (this.signalListeners[signal]) {
      // The mock mutates its state in place; a fresh copy lets React see the change
      this.signalListeners[signal].forEach((cb) => cb(structuredClone(data)));
    }
  }

  // High-fidelity Mock Dispatcher
  private async dispatchMock<T = any>(action: string, payload: any): Promise<T> {
    console.log(`[MOCK] Dispatching action "${action}":`, payload);
    await new Promise((resolve) => setTimeout(resolve, 150)); // Artificial network latency

    switch (action) {
      case "login": {
        const found = this.mockState.users.find((u: any) => u.pin === payload.pin && u.is_active);
        if (!found) throw new Error("رمز PIN غير صحيح. جرب 1234 (مدير النظام) أو 5555 (مدير المطعم) أو 1111 (كاشير)");
        const { pin: _pin, ...user } = found;
        this.mockState.currentUser = user;
        // Auto create active shift if none
        if (!this.mockState.activeShift) {
          this.mockState.activeShift = { id: 101 + this.mockState.closedShifts.length, opened_by: user.display_name, opened_at: new Date().toISOString(), next_invoice_no: 1, is_active: true, summary_printed_at: null };
        }
        return user as any;
      }

      case "logout":
        this.mockState.currentUser = null;
        this.mockState.currentOrder = null;
        return true as any;

      case "get_current_user":
        return this.mockState.currentUser;

      case "get_all_users":
        return this.mockState.users.filter((u: any) => u.is_active).map(({ pin: _pin, ...u }: any) => u) as any;

      case "get_users_management":
        return [...this.mockState.users, ...this.mockState.drivers].map(({ pin: _pin, ...u }: any) => u) as any;

      case "create_user": {
        this.requireMockAdmin();
        const all = [...this.mockState.users, ...this.mockState.drivers];
        if (all.some((u: any) => u.username === payload.username)) throw new Error("اسم المستخدم موجود بالفعل");
        if (all.some((u: any) => u.pin === payload.pin)) throw new Error("رمز PIN مستخدم بالفعل");
        const newUser = { id: Date.now(), username: payload.username, display_name: payload.display_name, role: payload.role, cashier_slot: payload.cashier_slot, is_active: true, pin: payload.pin };
        if (payload.role === "cashier" && payload.cashier_slot == null) {
          this.mockState.drivers.push({ ...newUser, is_checked_in: false });
        } else {
          this.mockState.users.push(newUser);
        }
        return newUser as any;
      }

      case "update_user": {
        this.requireMockAdmin();
        const target = [...this.mockState.users, ...this.mockState.drivers].find((u: any) => u.id === payload.user_id);
        if (!target) throw new Error("المستخدم غير موجود");
        if (payload.username) target.username = payload.username;
        if (payload.display_name) target.display_name = payload.display_name;
        if (payload.role) target.role = payload.role;
        if (payload.pin) target.pin = payload.pin;
        if (payload.cashier_slot !== undefined && payload.cashier_slot !== -1) target.cashier_slot = payload.cashier_slot;
        return target as any;
      }

      case "deactivate_user": {
        this.requireMockAdmin();
        const target = [...this.mockState.users, ...this.mockState.drivers].find((u: any) => u.id === payload.user_id);
        if (target) target.is_active = false;
        return true as any;
      }

      case "verify_manager_pin": {
        const manager = this.mockState.users.find((u: any) => u.pin === payload.pin && u.is_active && (u.role === "admin" || u.role === "manager"));
        if (!manager) throw new Error("ليست لديك صلاحيات مدير");
        return { id: manager.id, display_name: manager.display_name, role: manager.role } as any;
      }

      case "get_active_categories":
        return this.mockState.categories.filter((c: any) => c.is_active) as any;

      case "get_all_categories":
        return this.mockState.categories as any;

      case "create_category": {
        const cat = { id: Date.now(), name: payload.name, sort_order: payload.sort_order || 0, is_active: true };
        this.mockState.categories.push(cat);
        return cat as any;
      }

      case "update_category": {
        const cat = this.mockState.categories.find((c: any) => c.id === payload.category_id);
        if (!cat) throw new Error("الفئة غير موجودة");
        if (payload.name) cat.name = payload.name;
        if (payload.sort_order !== undefined) cat.sort_order = payload.sort_order;
        return cat as any;
      }

      case "create_product": {
        const prod = { id: Date.now(), name: payload.name, price: payload.price, category_id: payload.category_id, is_active: true, sort_order: payload.sort_order || 0 };
        this.mockState.products.push(prod);
        return prod as any;
      }

      case "update_product": {
        const prod = this.mockState.products.find((x: any) => x.id === payload.product_id);
        if (!prod) throw new Error("المنتج غير موجود");
        Object.assign(prod, { name: payload.name, price: payload.price, category_id: payload.category_id, sort_order: payload.sort_order });
        return prod as any;
      }

      case "deactivate_product": {
        const prod = this.mockState.products.find((x: any) => x.id === payload.product_id);
        if (prod) prod.is_active = false;
        return true as any;
      }

      case "get_products_by_category":
        return this.mockState.products.filter(p => p.category_id === payload.category_id && p.is_active) as any;

      case "search_products": {
        const q = payload.query.toLowerCase();
        return this.mockState.products.filter(p => p.is_active && p.name.includes(q)) as any;
      }

      case "find_customer_by_phone":
        return this.mockState.customers.find(c => c.phone === payload.phone) as any;

      case "create_customer": {
        const newCust = {
          id: this.mockState.customers.length + 1,
          name: payload.name,
          phone: payload.phone,
          notes: payload.notes || "",
          addresses: []
        };
        this.mockState.customers.push(newCust);
        return newCust as any;
      }

      case "add_customer_address": {
        const cust = this.mockState.customers.find(c => c.id === payload.customer_id);
        const zone = this.mockState.zones.find(z => z.id === payload.zone_id);
        if (!cust || !zone) throw new Error("العميل أو المنطقة غير موجودة");
        const newAddr = {
          id: Math.floor(Math.random() * 1000),
          customer_id: cust.id,
          street_name: payload.street_name,
          zone_id: zone.id,
          zone_name: zone.name,
          delivery_fee: zone.delivery_fee
        };
        cust.addresses.push(newAddr as any);
        return newAddr as any;
      }

      case "get_active_zones":
        return this.mockState.zones as any;

      case "new_order": {
        const order = {
          id: null,
          invoice_no: null,
          order_type: payload.order_type || "dine_in",
          status: "new",
          table_no: null,
          items: [],
          subtotal: 0.0,
          discount_amount: 0.0,
          discount_type: null,
          service_amount: 0.0,
          delivery_fee: 0.0,
          total: 0.0,
          payment_method: null,
          is_paid: false
        };
        this.mockState.currentOrder = order;
        this.notifyListeners("orderChanged", order);
        return order as any;
      }

      case "get_current_order":
        return this.mockState.currentOrder;

      case "add_item": {
        const order = this.mockState.currentOrder;
        if (!order) throw new Error("لا يوجد طلب نشط");
        const item = {
          product_id: payload.product_id,
          product_name: payload.product_name,
          quantity: payload.quantity || 1,
          unit_price: payload.unit_price,
          total_price: (payload.quantity || 1) * payload.unit_price,
          notes: payload.notes || ""
        };
        
        // check if exists
        const existing = order.items.find((i: any) => i.product_id === item.product_id && i.notes === item.notes);
        if (existing) {
          existing.quantity += item.quantity;
          existing.total_price = existing.quantity * existing.unit_price;
        } else {
          order.items.push(item);
        }
        this.recalculateOrder(order);
        this.notifyListeners("orderChanged", order);
        return true as any;
      }

      case "change_item_quantity": {
        const order = this.mockState.currentOrder;
        if (!order) throw new Error("لا يوجد طلب نشط");
        const item = order.items[payload.index];
        if (item) {
          item.quantity += payload.delta;
          if (item.quantity <= 0) {
            order.items.splice(payload.index, 1);
          } else {
            item.total_price = item.quantity * item.unit_price;
          }
          this.recalculateOrder(order);
          this.notifyListeners("orderChanged", order);
        }
        return true as any;
      }

      case "remove_item": {
        const order = this.mockState.currentOrder;
        if (!order) return { success: false, message: "لا يوجد طلب" } as any;
        if (this.mockState.currentUser?.role === "cashier") {
          if (payload.manager_pin !== "1234") {
            throw new Error("رمز PIN للمدير غير صحيح");
          }
        }
        order.items.splice(payload.index, 1);
        this.recalculateOrder(order);
        this.notifyListeners("orderChanged", order);
        return { success: true, message: "تم الحذف" } as any;
      }

      case "set_item_note": {
        const order = this.mockState.currentOrder;
        if (order && order.items[payload.index]) {
          order.items[payload.index].notes = payload.note;
          this.notifyListeners("orderChanged", order);
        }
        return true as any;
      }

      case "set_table": {
        const order = this.mockState.currentOrder;
        if (order) {
          order.table_no = payload.table_number;
          this.notifyListeners("orderChanged", order);
        }
        return true as any;
      }

      case "set_customer_info": {
        const order = this.mockState.currentOrder;
        if (order) {
          order.customer_id = payload.customer_id;
          order.customer_phone = payload.phone;
          order.customer_name = payload.name;
          order.customer_address = payload.address;
          order.customer_zone = payload.zone;
          order.delivery_fee = payload.delivery_fee;
          this.recalculateOrder(order);
          this.notifyListeners("orderChanged", order);
        }
        return true as any;
      }

      case "park_order": {
        const order = this.mockState.currentOrder;
        if (order) {
          this.mockState.parkedOrders.push(order);
          this.mockState.currentOrder = null;
          this.notifyListeners("orderChanged", null);
          this.notifyListeners("parkedChanged", this.mockState.parkedOrders);
          this.notifyListeners("tableStateChanged", this.getMockTableState());
          return true as any;
        }
        return false as any;
      }

      case "resume_parked_order": {
        const order = this.mockState.parkedOrders.splice(payload.index, 1)[0];
        if (order) {
          this.mockState.currentOrder = order;
          this.notifyListeners("orderChanged", order);
          this.notifyListeners("parkedChanged", this.mockState.parkedOrders);
          this.notifyListeners("tableStateChanged", this.getMockTableState());
          return true as any;
        }
        return false as any;
      }

      case "get_parked_orders":
        return this.mockState.parkedOrders as any;

      case "confirm_order": {
        const order = this.mockState.currentOrder;
        if (!order || order.items.length === 0) throw new Error("الطلب فارغ");
        
        const shift = this.mockState.activeShift;
        if (!shift) throw new Error("لا توجد وردية مفتوحة");

        // Invoice numbers restart at 1 with every shift
        const invoice_no = shift.next_invoice_no++;
        order.id = Date.now();
        order.invoice_no = invoice_no;
        order.status = "new";
        order.shift_id = shift.id;
        order.created_at = new Date().toISOString();

        // Track as active order
        this.mockState.activeOrders.push({ ...order });

        // Clear current order workspace
        this.mockState.currentOrder = null;
        this.notifyListeners("orderChanged", null);
        this.notifyListeners("tableStateChanged", this.getMockTableState());
        
        return {
          invoice_no,
          needs_immediate_payment: order.order_type === "takeaway",
          order_id: order.id
        } as any;
      }

      case "complete_payment": {
        const orderId = payload.order_id;
        const activeOrder = this.mockState.activeOrders.find((o: any) => o.id === orderId);
        if (activeOrder) {
          activeOrder.is_paid = true;
          activeOrder.status = "completed";
          activeOrder.payment_method = payload.payment_method;
          activeOrder.amount_paid = payload.amount_paid;
        }
        this.notifyListeners("tableStateChanged", this.getMockTableState());
        return true as any;
      }

      case "load_order":
      case "load_order_by_table": {
        const found = this.mockState.activeOrders.find((o: any) =>
          o.status !== "completed" && o.status !== "cancelled" &&
          (action === "load_order" ? o.id === payload.order_id : o.order_type === "dine_in" && o.table_no === payload.table_number)
        );
        if (!found) {
          throw new Error(action === "load_order" ? "الطلب غير موجود" : "هذه الطاولة عليها طلب معلق، استرجعه من الطلبات المعلقة");
        }
        const order = structuredClone(found);
        this.mockState.currentOrder = order;
        this.notifyListeners("orderChanged", order);
        return order as any;
      }

      case "save_amendment": {
        const order = this.mockState.currentOrder;
        if (!order?.id) throw new Error("لا يوجد طلب محفوظ للتعديل");
        const idx = this.mockState.activeOrders.findIndex((o: any) => o.id === order.id);
        if (idx >= 0) this.mockState.activeOrders[idx] = structuredClone(order);
        this.mockState.currentOrder = null;
        this.notifyListeners("orderChanged", null);
        this.notifyListeners("tableStateChanged", this.getMockTableState());
        return { success: true, message: "تم حفظ التعديلات" } as any;
      }

      case "get_table_state":
        return this.getMockTableState() as any;

      case "get_active_orders":
        return this.mockState.activeOrders.filter((o: any) => o.status !== "completed" && o.status !== "cancelled") as any;

      case "get_active_by_type":
        return this.mockState.activeOrders.filter((o: any) =>
          o.order_type === payload.order_type && o.status !== "completed" && o.status !== "cancelled"
        ) as any;

      case "get_available_drivers":
        return this.mockState.drivers as any;

      case "get_active_trips":
        return this.mockState.trips as any;

      case "check_in_driver": {
        const d = this.mockState.drivers.find((x: any) => x.id === payload.driver_id);
        if (d) { d.is_checked_in = true; d.check_in_at = new Date().toISOString(); d.check_out_at = null; }
        return true as any;
      }

      case "check_out_driver": {
        const d = this.mockState.drivers.find((x: any) => x.id === payload.driver_id);
        if (d) { d.is_checked_in = false; d.check_out_at = new Date().toISOString(); }
        return true as any;
      }

      case "get_driver_attendance_today":
        return this.mockState.drivers
          .filter((d: any) => d.is_checked_in || d.check_in_at)
          .map((d: any) => {
            if (!d.check_in_at) d.check_in_at = new Date().toISOString();
            return { driver_id: d.id, display_name: d.display_name, check_in_at: d.check_in_at, check_out_at: d.is_checked_in ? null : d.check_out_at };
          }) as any;

      case "get_daily_driver_summary":
        return this.mockState.drivers.map((d: any) => {
          const trips = this.mockState.trips.filter((t: any) => t.driver_id === d.id);
          const orders = this.mockState.activeOrders.filter((o: any) => trips.some((t: any) => t.order_ids?.includes(o.id)));
          return {
            driver_id: d.id,
            driver_name: d.display_name,
            trip_count: trips.length,
            order_count: orders.length,
            fees_earned: orders.reduce((sum: number, o: any) => sum + (o.delivery_fee || 0), 0)
          };
        }).filter((row: any) => row.trip_count > 0) as any;

      case "get_trip_details": {
        const trip = this.mockState.trips.find((t: any) => t.id === payload.trip_id);
        if (!trip) throw new Error("الرحلة غير موجودة");
        const orders = this.mockState.activeOrders.filter((o: any) => trip.order_ids?.includes(o.id));
        return {
          trip_id: trip.id,
          driver_name: trip.driver_name,
          orders: orders.map((o: any) => ({ ...o, order_id: o.id })),
          total_order_value: orders.reduce((sum: number, o: any) => sum + (o.total || 0), 0),
          total_delivery_fees: orders.reduce((sum: number, o: any) => sum + (o.delivery_fee || 0), 0)
        } as any;
      }

      case "create_trip": {
        const newTrip = {
          id: Math.floor(Math.random() * 1000) + 1,
          driver_id: payload.driver_id,
          driver_name: this.mockState.drivers.find((d: any) => d.id === payload.driver_id)?.display_name || "طيار",
          order_count: payload.order_ids.length,
          status: "pending",
          dispatched_at: null,
          order_ids: payload.order_ids
        };
        this.mockState.trips.push(newTrip);
        return { success: true, trip_id: newTrip.id } as any;
      }

      case "dispatch_trip": {
        const trip = this.mockState.trips.find((t: any) => t.id === payload.trip_id);
        if (trip) {
          trip.status = "dispatched";
          trip.dispatched_at = new Date().toISOString();
        }
        return { success: true } as any;
      }

      case "return_trip": {
        const trip = this.mockState.trips.find((t: any) => t.id === payload.trip_id);
        if (!trip) throw new Error("رحلة غير موجودة");
        if (!trip.dispatched_at) throw new Error("الرحلة لم تُرسل بعد");
        trip.returned_at = new Date().toISOString();
        trip.status = "returned";
        return { success: true, message: "تم تسجيل عودة الطيار" } as any;
      }

      case "settle_trip": {
        const trip = this.mockState.trips.find((t: any) => t.id === payload.trip_id);
        if (trip) {
          trip.status = "settled";
          // also complete the associated orders in mock state
          if (trip.order_ids) {
            trip.order_ids.forEach((oid: any) => {
              const order = this.mockState.activeOrders.find((o: any) => o.id === oid);
              if (order) {
                order.status = "completed";
                order.is_paid = true;
              }
            });
          }
        }
        return { success: true, message: "تم تسوية الرحلة" } as any;
      }

      case "apply_discount": {
        const order = this.mockState.currentOrder;
        if (!order) throw new Error("لا يوجد طلب نشط");
        if (this.mockState.currentUser?.role === "cashier") {
          if (payload.manager_pin !== "1234") {
            throw new Error("رمز PIN للمدير غير صحيح");
          }
        }
        const val = payload.value;
        const discountType = payload.discount_type;
        if (discountType === "flat") {
          order.discount_amount = val;
        } else {
          order.discount_amount = (order.subtotal * val) / 100;
        }
        this.recalculateOrder(order);
        this.notifyListeners("orderChanged", order);
        return { success: true, message: "تم تطبيق الخصم" } as any;
      }

      case "cancel_order": {
        const orderId = payload.order_id;
        const activeOrder = this.mockState.activeOrders.find((o: any) => o.id === orderId);
        if (activeOrder) {
          activeOrder.status = "cancelled";
        }
        const parkedOrder = this.mockState.parkedOrders.find((o: any) => o.id === orderId);
        if (parkedOrder) {
          parkedOrder.status = "cancelled";
          this.mockState.parkedOrders = this.mockState.parkedOrders.filter((o: any) => o.id !== orderId);
          this.notifyListeners("parkedChanged", this.mockState.parkedOrders);
          this.notifyListeners("tableStateChanged", this.getMockTableState());
        }
        return { success: true, message: "تم إلغاء الطلب" } as any;
      }

      case "get_active_shift":
        return this.mockState.activeShift as any;

      case "open_shift": {
        if (this.mockState.activeShift) {
          throw new Error("توجد وردية مفتوحة بالفعل");
        }
        const shift = {
          id: Math.floor(Math.random() * 1000) + 1,
          opened_by: this.mockState.currentUser?.id || 1,
          opened_at: new Date().toISOString(),
          next_invoice_no: 1,
          is_active: true,
          summary_printed_at: null
        };
        this.mockState.activeShift = shift;
        return shift as any;
      }

      case "get_report_daily_sales":
        return this.buildMockDailySales() as any;

      case "get_shift_summary": {
        const fullSummary: any = this.buildMockShiftSummary(payload?.shift_id ?? this.mockState.activeShift?.id);
        // Mirror backend: a cashier never receives the sales totals.
        if (this.mockState.currentUser?.role === "cashier") {
          delete fullSummary.total_sales;
          delete fullSummary.cash_sales;
          delete fullSummary.expected_cash;
        }
        return fullSummary;
      }

      case "get_users_for_transfer":
        return this.mockState.users
          .filter((u: any) => u.is_active)
          .map(({ pin: _pin, ...u }: any) => u) as any;

      case "transfer_shift": {
        if (!this.mockState.activeShift) throw new Error("لا توجد وردية مفتوحة");
        const manager = this.mockState.users.find(
          (u: any) => u.pin === payload?.manager_pin && u.is_active && (u.role === "admin" || u.role === "manager")
        );
        if (!manager) throw new Error("PIN غير صحيح أو ليس لديك صلاحية");
        // Invoice numbering continues — the shift stays open under the new cashier.
        this.mockState.activeShift.opened_by = payload?.to_user_id ?? this.mockState.activeShift.opened_by;
        console.log(`[MOCK] Shift transferred to user ${payload?.to_user_id}`);
        return true as any;
      }

      case "get_expenses":
        return this.mockState.expenses.filter((e: any) => e.shift_id === this.mockState.activeShift?.id) as any;

      case "add_expense": {
        if (!this.mockState.activeShift) throw new Error("لا توجد وردية مفتوحة");
        const exp = {
          id: Math.floor(Math.random() * 1000),
          shift_id: this.mockState.activeShift.id,
          amount: payload.amount,
          description: payload.description,
          category: payload.category,
          timestamp: new Date().toISOString()
        };
        this.mockState.expenses.push(exp);
        return exp as any;
      }

      case "close_shift": {
        const shift = this.mockState.activeShift;
        if (!shift) throw new Error("لا توجد وردية مفتوحة");
        if (!shift.summary_printed_at) throw new Error("يجب طباعة التقرير اليومي قبل إغلاق الوردية");
        this.mockState.closedShifts.unshift({
          ...shift,
          closed_by: this.mockState.currentUser?.display_name,
          closed_at: new Date().toISOString(),
          is_active: false
        });
        this.mockState.activeShift = null;
        this.notifyListeners("shiftStatusChanged", { active: false });
        return true as any;
      }

      case "get_shift_history":
        return this.mockState.closedShifts as any;

      case "print_shift_summary":
        console.log(`[MOCK] Printed shift summary for shift ID: ${payload.shift_id}`);
        if (this.mockState.activeShift) this.mockState.activeShift.summary_printed_at = new Date().toISOString();
        return true as any;

      // --- Phase 3: Customer History ---
      case "get_customer_by_id": {
        const cust = this.mockState.customers.find((c: any) => c.id === payload.customer_id);
        return (cust ? cust : null) as any;
      }

      case "get_customer_history": {
        // Return mock order history for the customer
        const history = this.mockState.activeOrders
          .filter((o: any) => o.customer_id === payload.customer_id)
          .map((o: any) => ({
            id: o.id,
            invoice_no: o.invoice_no,
            order_type: o.order_type || "delivery",
            status: o.status,
            total: o.total,
            payment_method: o.payment_method,
            is_paid: o.is_paid,
            customer_address: o.customer_address || "",
            customer_zone: o.customer_zone || "",
            created_at: o.created_at || new Date().toISOString(),
            cancelled_at: null,
            cancel_reason: null,
          }));
        // Add a few mock historical entries for display purposes
        if (this.mockState.customers.find((c: any) => c.id === payload.customer_id)) {
          (history as any[]).push(
            ...([ 
              { id: 9001, invoice_no: 42, order_type: "delivery", status: "completed", total: 160.0, payment_method: "cash", is_paid: true, customer_address: "شارع المشالي", customer_zone: "مدينة فاقوس", created_at: new Date(Date.now() - 7 * 86400000).toISOString(), cancelled_at: null, cancel_reason: null },
              { id: 9002, invoice_no: 35, order_type: "delivery", status: "completed", total: 290.0, payment_method: "cash", is_paid: true, customer_address: "شارع المشالي", customer_zone: "مدينة فاقوس", created_at: new Date(Date.now() - 14 * 86400000).toISOString(), cancelled_at: null, cancel_reason: null },
              { id: 9003, invoice_no: 28, order_type: "delivery", status: "cancelled", total: 95.0, payment_method: "cash", is_paid: false, customer_address: "شارع المشالي", customer_zone: "مدينة فاقوس", created_at: new Date(Date.now() - 21 * 86400000).toISOString(), cancelled_at: new Date(Date.now() - 21 * 86400000 + 1800000).toISOString(), cancel_reason: "العميل غير موجود" },
            ] as any[])
          );
        }
        return history as any;
      }

      case "get_customer_statistics": {
        return {
          total_orders: 7,
          completed_orders: 5,
          cancelled_orders: 1,
          active_orders: 1,
          total_spent: 1250.0,
          avg_order_value: 250.0,
          largest_order: 420.0,
          first_order_at: new Date(Date.now() - 60 * 86400000).toISOString(),
          last_order_at: new Date(Date.now() - 7 * 86400000).toISOString(),
        } as any;
      }

      // --- Phase 1: Order Status History ---
      case "get_order_status_history": {
        // status labels available if needed
        const order = this.mockState.activeOrders.find((o: any) => o.id === payload.order_id);
        const now = Date.now();
        return [
          { id: 1, order_id: payload.order_id, old_status: null, new_status: "new", changed_by_id: 1, changed_by_name: "كاشير الوردية", reason: null, changed_at: new Date(now - 3600000).toISOString() },
          { id: 2, order_id: payload.order_id, old_status: "new", new_status: "preparing", changed_by_id: 1, changed_by_name: "كاشير الوردية", reason: null, changed_at: new Date(now - 2700000).toISOString() },
          { id: 3, order_id: payload.order_id, old_status: "preparing", new_status: "out_for_delivery", changed_by_id: 10, changed_by_name: "أحمد (طيار)", reason: null, changed_at: new Date(now - 1800000).toISOString() },
          ...(order?.status === "completed" ? [{ id: 4, order_id: payload.order_id, old_status: "out_for_delivery", new_status: "completed", changed_by_id: 1, changed_by_name: "كاشير الوردية", reason: null, changed_at: new Date(now - 600000).toISOString() }] : []),
          ...(order?.status === "cancelled" ? [{ id: 4, order_id: payload.order_id, old_status: "preparing", new_status: "cancelled", changed_by_id: 2, changed_by_name: "ياسر (مدير)", reason: "طلب العميل إلغاء الطلب", changed_at: new Date(now - 600000).toISOString() }] : []),
        ] as any;
      }

      // --- Phase 2: Audit Log ---
      case "get_audit_logs": {
        const sampleEvents = [
          { id: 1, event_type: "order_cancelled", user_id: 2, user_name: "ياسر (مدير)", order_id: 101, entity_type: "order", entity_id: 101, action: "إلغاء الطلب", reason: "طلب العميل", details: null, before_data: { status: "new" }, after_data: { status: "cancelled" }, timestamp: new Date(Date.now() - 3600000).toISOString() },
          { id: 2, event_type: "discount_applied", user_id: 2, user_name: "ياسر (مدير)", order_id: 102, entity_type: "order", entity_id: 102, action: "تطبيق خصم 20%", reason: null, details: { discount_type: "percent", value: 20 }, before_data: null, after_data: { discount_amount: 32, total: 128 }, timestamp: new Date(Date.now() - 7200000).toISOString() },
          { id: 3, event_type: "trip_settled", user_id: 1, user_name: "كاشير الوردية", order_id: null, entity_type: "trip", entity_id: 5, action: "تسوية رحلة", reason: null, details: { trip_id: 5, cash_collected: 450 }, before_data: null, after_data: { cash_collected: 450, fees: 40 }, timestamp: new Date(Date.now() - 10800000).toISOString() },
          { id: 4, event_type: "driver_settlement_completed", user_id: 1, user_name: "كاشير الوردية", order_id: null, entity_type: "driver", entity_id: 10, action: "تسوية يومية", reason: null, details: { driver_id: 10, date: new Date().toISOString().slice(0,10), cash_collected: 890, delivery_fees: 75 }, before_data: null, after_data: null, timestamp: new Date(Date.now() - 1800000).toISOString() },
          { id: 5, event_type: "item_removed", user_id: 2, user_name: "ياسر (مدير)", order_id: 103, entity_type: "order", entity_id: 103, action: "حذف عنصر", reason: null, details: { product_name: "بطاطس وسط", quantity: 2 }, before_data: null, after_data: null, timestamp: new Date(Date.now() - 14400000).toISOString() },
        ];
        return sampleEvents.filter(e => {
          if (payload.event_type && e.event_type !== payload.event_type) return false;
          if (payload.order_id && e.order_id !== payload.order_id) return false;
          if (payload.entity_type && e.entity_type !== payload.entity_type) return false;
          return true;
        }) as any;
      }

      // --- Phase 4: Driver Settlement ---
      case "get_driver_settlement_preview": {
        const driver = this.mockState.drivers.find((d: any) => d.id === payload.driver_id);
        if (!driver) throw new Error("السائق غير موجود");
        return {
          driver_id: payload.driver_id,
          driver_name: driver.display_name,
          settlement_date: new Date().toISOString().slice(0, 10),
          trip_count: 2,
          order_count: 5,
          total_order_value: 890.0,
          cash_collected: 740.0,
          online_paid: 150.0,
          total_delivery_fees: 75.0,
          trips: [
            {
              trip_id: 1,
              dispatched_at: new Date(Date.now() - 7200000).toISOString(),
              returned_at: new Date(Date.now() - 5400000).toISOString(),
              order_count: 3,
              cash: 450.0,
              online: 100.0,
              fees: 45.0,
              orders: [
                { order_id: 101, invoice_no: 45, customer_name: "ياسر المصري", customer_address: "شارع المشالي", customer_zone: "مدينة فاقوس", total: 160.0, delivery_fee: 15.0, payment_method: "cash", status: "delivered" },
                { order_id: 102, invoice_no: 46, customer_name: "محمد علي", customer_address: "شارع النصر", customer_zone: "شارع الانتاج", total: 190.0, delivery_fee: 10.0, payment_method: "cash", status: "delivered" },
                { order_id: 103, invoice_no: 47, customer_name: "أحمد محمد", customer_address: "طريق الغابة", customer_zone: "الغابة", total: 100.0, delivery_fee: 25.0, payment_method: "online", status: "delivered" },
              ]
            },
            {
              trip_id: 2,
              dispatched_at: new Date(Date.now() - 3600000).toISOString(),
              returned_at: new Date(Date.now() - 1800000).toISOString(),
              order_count: 2,
              cash: 290.0,
              online: 50.0,
              fees: 30.0,
              orders: [
                { order_id: 104, invoice_no: 48, customer_name: "سارة أحمد", customer_address: "شارع الملك", customer_zone: "مدينة فاقوس", total: 290.0, delivery_fee: 15.0, payment_method: "cash", status: "delivered" },
                { order_id: 105, invoice_no: 49, customer_name: "خالد إبراهيم", customer_address: "شارع الجمهورية", customer_zone: "شارع الانتاج", total: 50.0, delivery_fee: 10.0, payment_method: "online", status: "delivered" },
              ]
            }
          ]
        } as any;
      }

      case "settle_driver": {
        const driver = this.mockState.drivers.find((d: any) => d.id === payload.driver_id);
        if (!driver) throw new Error("السائق غير موجود");
        return {
          id: Math.floor(Math.random() * 1000) + 1,
          driver_name: driver.display_name,
          settlement_date: new Date().toISOString().slice(0, 10),
          trip_count: 2,
          order_count: 5,
          cash_collected: 740.0,
          online_paid: 150.0,
          total_delivery_fees: 75.0,
          total_order_value: 890.0,
          settled_at: new Date().toISOString(),
        } as any;
      }

      case "get_driver_settlements": {
        return [] as any; // start empty — populated after settle_driver calls
      }

      // ── v2 Session mocks ──────────────────────────────────────────────────

      case "session.open": {
        const newSession: CashierSession = {
          id: Date.now(),
          day_id: payload.day_id ?? 1,
          user_id: payload.user_id ?? this.mockState.currentUser?.id ?? 1,
          station: payload.station ?? 'ALL',
          is_open: true,
          opened_at: new Date().toISOString(),
          closed_at: null,
          opening_float_pt: Math.round((payload.opening_float_egp ?? 0) * 100),
          opening_float_egp: payload.opening_float_egp ?? 0,
          counted_cash_pt: null, counted_cash_egp: null,
          expected_cash_pt: Math.round((payload.opening_float_egp ?? 0) * 100),
          expected_cash_egp: payload.opening_float_egp ?? 0,
          variance_pt: null, variance_egp: null,
        };
        (this.mockState as any).sessions = [
          ...((this.mockState as any).sessions ?? []),
          newSession,
        ];
        return newSession as any;
      }

      case "session.close": {
        const sessions: CashierSession[] = (this.mockState as any).sessions ?? [];
        const idx = sessions.findIndex((s) => s.id === payload.session_id);
        if (idx === -1) throw new Error("الجلسة غير موجودة");
        const s = { ...sessions[idx] };
        const countedPt = Math.round((payload.counted_cash_egp ?? 0) * 100);
        s.is_open = false;
        s.closed_at = new Date().toISOString();
        s.counted_cash_pt = countedPt;
        s.counted_cash_egp = payload.counted_cash_egp ?? 0;
        s.variance_pt = countedPt - (s.expected_cash_pt ?? 0);
        s.variance_egp = s.variance_pt / 100;
        sessions[idx] = s;
        (this.mockState as any).sessions = sessions;
        return s as any;
      }

      case "session.handover": {
        // Close old session
        const closedRaw = await this.dispatchMock('session.close', {
          session_id: payload.from_session_id,
          counted_cash_egp: payload.counted_cash_egp ?? 0,
        });
        // New opening float = counted - drop
        const drop = payload.cash_drop_egp ?? 0;
        const newFloat = Math.max(0, (payload.counted_cash_egp ?? 0) - drop);
        const newS = await this.dispatchMock('session.open', {
          day_id: closedRaw.day_id,
          user_id: payload.to_user_id,
          station: payload.station ?? closedRaw.station,
          opening_float_egp: newFloat,
        });
        return { closed: closedRaw, new: newS } as any;
      }

      case "session.get_active": {
        const all: CashierSession[] = (this.mockState as any).sessions ?? [];
        return all.filter((s) => s.is_open) as any;
      }

      case "session.get_all": {
        return ((this.mockState as any).sessions ?? []) as any;
      }

      case "session.get_balance": {
        const allS: CashierSession[] = (this.mockState as any).sessions ?? [];
        const found = allS.find((s) => s.id === payload.session_id);
        if (!found) throw new Error("الجلسة غير موجودة");
        return {
          session_id: found.id,
          balance_pt: found.expected_cash_pt ?? 0,
          balance_egp: found.expected_cash_egp ?? 0,
          is_open: found.is_open,
        } as any;
      }

      case "session.x_report": {
        const allSessions: CashierSession[] = (this.mockState as any).sessions ?? [];
        const totalPt = allSessions.reduce((a, s) => a + (s.expected_cash_pt ?? 0), 0);
        const snapshots = allSessions.map((s) => ({
          session_id: s.id, user_id: s.user_id, station: s.station,
          is_open: s.is_open, opened_at: s.opened_at, closed_at: s.closed_at,
          opening_float_pt: s.opening_float_pt, opening_float_egp: s.opening_float_egp,
          expected_cash_pt: s.expected_cash_pt ?? 0,
          expected_cash_egp: s.expected_cash_egp ?? 0,
          counted_cash_pt: s.counted_cash_pt, counted_cash_egp: s.counted_cash_egp,
          variance_pt: s.variance_pt, variance_egp: s.variance_egp,
          breakdown: {
            OPENING_FLOAT: { pt: s.opening_float_pt, egp: s.opening_float_egp },
          },
        }));
        return {
          type: 'X', day_id: payload.day_id ?? 1,
          generated_at: new Date().toISOString(),
          sessions: snapshots,
          totals: {
            expected_cash_pt: totalPt, expected_cash_egp: totalPt / 100,
            cash_sales_pt: 0, cash_sales_egp: 0,
            driver_remittance_pt: 0, driver_remittance_egp: 0,
            expenses_pt: 0, expenses_egp: 0,
          },
        } as any;
      }

      case "session.close_day": {
        // Close all open sessions with zero variance
        const sessionsForClose: CashierSession[] = (this.mockState as any).sessions ?? [];
        for (const s of sessionsForClose.filter((ss) => ss.is_open)) {
          await this.dispatchMock('session.close', {
            session_id: s.id,
            counted_cash_egp: s.expected_cash_egp ?? 0,
          });
        }
        const xReport = await this.dispatchMock<XReport>('session.x_report', payload);
        return {
          ...xReport,
          type: 'Z',
          day_closed_at: new Date().toISOString(),
          total_variance_pt: 0,
          total_variance_egp: 0,
        } as any;
      }

      default:
        throw new Error(`الإجراء Mock غير متوفر: ${action}`);
    }
  }

  private recalculateOrder(order: any) {
    order.subtotal = order.items.reduce((acc: number, item: any) => acc + item.total_price, 0);
    order.total = order.subtotal - order.discount_amount + order.service_amount + order.delivery_fee;
  }

  private requireMockAdmin() {
    if (this.mockState.currentUser?.role !== "admin") {
      throw new Error("يتطلب صلاحيات مدير النظام");
    }
  }

  // Same formula as the backend: expected_cash = sales - expenses - all pending
  private buildMockShiftSummary(shiftId?: number) {
    const orders = this.mockState.activeOrders.filter((o: any) => o.shift_id === shiftId && o.status !== "cancelled");
    const expenses = this.mockState.expenses.filter((e: any) => e.shift_id === shiftId);
    const sum = (list: any[], key: string) => list.reduce((acc, x) => acc + (x[key] || 0), 0);
    const unpaid = orders.filter((o: any) => !o.is_paid);

    const total_sales = sum(orders, "total");
    const cash_sales = sum(
      orders.filter((o: any) => o.is_paid && (o.payment_method || "cash") === "cash"),
      "total"
    );
    const total_expenses = sum(expenses, "amount");
    const pending_delivery = sum(unpaid.filter((o: any) => o.order_type === "delivery"), "total");
    const pending_dinein = sum(unpaid.filter((o: any) => o.order_type === "dine_in"), "total");
    const pending_kitchen = sum(unpaid.filter((o: any) => o.order_type !== "delivery" && o.order_type !== "dine_in"), "total");

    const order_breakdown: Record<string, { count: number; revenue: number }> = {};
    orders.forEach((o: any) => {
      const row = (order_breakdown[o.order_type] ||= { count: 0, revenue: 0 });
      row.count += 1;
      row.revenue += (o.total || 0) - (o.delivery_fee || 0);
    });

    return {
      total_sales,
      cash_sales,
      total_expenses,
      pending_delivery,
      pending_dinein,
      pending_kitchen,
      expected_cash: cash_sales - total_expenses - pending_delivery - pending_dinein - pending_kitchen,
      order_count: orders.length,
      order_breakdown
    };
  }

  private buildMockDailySales() {
    const orders = this.mockState.activeOrders.filter((o: any) => o.status !== "cancelled");
    const group = (list: any[], keyOf: (o: any) => string) => {
      const rows: Record<string, { count: number; revenue: number }> = {};
      list.forEach((o) => {
        const row = (rows[keyOf(o)] ||= { count: 0, revenue: 0 });
        row.count += 1;
        row.revenue += o.total || 0;
      });
      return rows;
    };
    const gross_revenue = orders.reduce((acc: number, o: any) => acc + (o.total || 0), 0);
    const total_delivery_fees = orders.reduce((acc: number, o: any) => acc + (o.delivery_fee || 0), 0);
    const paid = orders.filter((o: any) => o.is_paid);

    const sold: Record<string, { product_name: string; quantity: number; revenue: number }> = {};
    orders.forEach((o: any) => o.items.forEach((item: any) => {
      const row = (sold[item.product_name] ||= { product_name: item.product_name, quantity: 0, revenue: 0 });
      row.quantity += item.quantity;
      row.revenue += item.total_price;
    }));

    return {
      date: new Date().toISOString().slice(0, 10),
      sales_by_type: {
        breakdown: Object.entries(group(orders, (o) => o.order_type)).map(([type, r]) => ({ type, ...r })),
        grand_total: { count: orders.length, revenue: gross_revenue }
      },
      payment_breakdown: {
        payments: Object.entries(group(paid, (o) => o.payment_method || "cash")).map(([method, r]) => ({ method, ...r })),
        total: paid.reduce((acc: number, o: any) => acc + (o.total || 0), 0)
      },
      gross_revenue,
      restaurant_revenue: gross_revenue - total_delivery_fees,
      total_delivery_fees,
      bestsellers: Object.values(sold).sort((a, b) => b.quantity - a.quantity).slice(0, 5)
    };
  }

  private getMockTableState() {
    const state: any = {};
    this.mockState.parkedOrders.forEach((o: any) => {
      if (o.table_no) state[o.table_no] = "معلق";
    });
    this.mockState.activeOrders.forEach((o: any) => {
      if (o.order_type === "dine_in" && o.table_no && o.status !== "completed" && o.status !== "cancelled") {
        state[o.table_no] = "#" + o.invoice_no;
      }
    });
    return state;
  }
}

export const bridge = new POSBridgeClient();
