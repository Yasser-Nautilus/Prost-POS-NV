import React, { useState, useEffect } from "react";
import { 
  ShoppingBag, Search, Tag, CreditCard, RotateCcw, 
  Plus, Minus, Trash2, AlertCircle, Archive, X 
} from "lucide-react";
import { bridge } from "../bridge";
import { DiscountDialog } from "../components/DiscountDialog";
import { PaymentDialog } from "../components/PaymentDialog";
import { CustomerLookup } from "../components/CustomerLookup";
import { PinDialog } from "../components/PinDialog";
import { TableGrid } from "../components/TableGrid";

interface POSViewProps {
  currentUser: any;
}

export const POSView: React.FC<POSViewProps> = ({ currentUser }) => {
  // POS States
  const [categories, setCategories] = useState<any[]>([]);
  const [selectedCatId, setSelectedCatId] = useState<number | null>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  
  const [currentOrder, setCurrentOrder] = useState<any>(null);
  const [parkedCount, setParkedCount] = useState(0);
  const [parkedOrders, setParkedOrders] = useState<any[]>([]);
  const [selectedTable, setSelectedTable] = useState<number | null>(null);
  const [pendingOrderId, setPendingOrderId] = useState<number | null>(null);
  const [pendingTotal, setPendingTotal] = useState(0); // captured before confirm clears cart
  const [isAmending, setIsAmending] = useState(false); // true when editing existing order

  // Dialog Toggles
  const [isDiscountOpen, setIsDiscountOpen] = useState(false);
  const [isPaymentOpen, setIsPaymentOpen] = useState(false);
  const [isCustomerLookupOpen, setIsCustomerLookupOpen] = useState(false);
  const [isTableGridOpen, setIsTableGridOpen] = useState(false);
  const [isParkedPanelOpen, setIsParkedPanelOpen] = useState(false);
  const [showPinGate, setShowPinGate] = useState(false);
  const [pendingDeleteIdx, setPendingDeleteIdx] = useState<number | null>(null);

  // Table occupancy state (table_no -> invoice label)
  const [occupiedTables, setOccupiedTables] = useState<Record<number, string>>({});

  // Load Categories on init
  useEffect(() => {
    fetchCategories();
    fetchCurrentOrder();
    fetchParkedCount();
    fetchTableState();

    // Subscribe to backend changes
    const handleOrderChange = (order: any) => {
      setCurrentOrder(order);
      // If the order has an invoice_no it was loaded from DB (amending mode)
      if (order?.invoice_no) {
        setIsAmending(true);
        if (order.table_no) setSelectedTable(order.table_no);
      } else {
        // Fresh/new order — clear amending flag
        setIsAmending(false);
      }
    };
    const handleParkedChange = (parkedList: any[]) => {
      setParkedCount(parkedList?.length || 0);
    };
    const handleTableStateChange = (state: Record<string, string>) => {
      const parsed: Record<number, string> = {};
      Object.entries(state || {}).forEach(([k, v]) => {
        parsed[parseInt(k)] = v;
      });
      setOccupiedTables(parsed);
    };

    bridge.subscribe("orderChanged", handleOrderChange);
    bridge.subscribe("parkedChanged", handleParkedChange);
    bridge.subscribe("tableStateChanged", handleTableStateChange);

    return () => {
      bridge.unsubscribe("orderChanged", handleOrderChange);
      bridge.unsubscribe("parkedChanged", handleParkedChange);
      bridge.unsubscribe("tableStateChanged", handleTableStateChange);
    };
  }, []);

  // Fetch products when category changes
  useEffect(() => {
    if (selectedCatId !== null) {
      fetchProducts(selectedCatId);
    }
  }, [selectedCatId]);

  const fetchCategories = async () => {
    try {
      const res = await bridge.call("get_active_categories");
      setCategories(res || []);
      if (res && res.length > 0) {
        setSelectedCatId(res[0].id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchProducts = async (catId: number) => {
    try {
      const res = await bridge.call("get_products_by_category", { category_id: catId });
      setProducts(res || []);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchCurrentOrder = async () => {
    try {
      let res = await bridge.call("get_current_order");
      if (!res) {
        // Create new dine-in order by default
        res = await bridge.call("new_order", { order_type: "dine_in" });
      }
      setCurrentOrder(res);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchParkedCount = async () => {
    try {
      const res = await bridge.call("get_parked_orders");
      setParkedCount(res?.length || 0);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchTableState = async () => {
    try {
      const state = await bridge.call("get_table_state");
      if (state && typeof state === "object") {
        const parsed: Record<number, string> = {};
        Object.entries(state).forEach(([k, v]) => {
          parsed[parseInt(k)] = v as string;
        });
        setOccupiedTables(parsed);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleProductSearch = async (query: string) => {
    setSearchQuery(query);
    if (!query) {
      if (selectedCatId !== null) fetchProducts(selectedCatId);
      return;
    }
    try {
      const res = await bridge.call("search_products", { query });
      setProducts(res || []);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddProduct = async (prod: any) => {
    try {
      await bridge.call("add_item", {
        product_id: prod.id,
        product_name: prod.name,
        quantity: 1,
        unit_price: prod.price,
        notes: ""
      });
    } catch (e: any) {
      alert("فشل إضافة المنتج: " + e.message);
    }
  };

  const handleQtyChange = async (idx: number, delta: number) => {
    try {
      await bridge.call("change_item_quantity", { index: idx, delta });
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDeleteItemClick = (idx: number) => {
    // Per progress.md: cashiers need manager PIN to remove items; managers/admin can delete freely
    if (currentUser?.role === "manager" || currentUser?.role === "admin") {
      performDeleteItem(idx);
    } else {
      setPendingDeleteIdx(idx);
      setShowPinGate(true);
    }
  };

  const performDeleteItem = async (idx: number) => {
    const targetIdx = idx !== undefined ? idx : pendingDeleteIdx;
    if (targetIdx === null) return;
    try {
      await bridge.call("remove_item", { index: targetIdx });
      setPendingDeleteIdx(null);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleSetOrderType = async (type: string) => {
    try {
      // Guard: if items already exist, confirm before switching (clears cart)
      if (currentOrder && currentOrder.items.length > 0) {
        const choice = window.confirm(
          "تحويل نوع الطلب سيمسح العناصر الحالية. هل تريد المتابعة؟\n\n" +
          "اضغط OK للمتابعة، أو Cancel لإلغاء."
        );
        if (!choice) return;
      }

      await bridge.call("new_order", { order_type: type });
      setSelectedTable(null);
      setIsAmending(false);

      // For dine-in: open table picker immediately
      if (type === "dine_in") {
        setIsTableGridOpen(true);
      }
      // Delivery/pickup: add items first, customer info prompted at checkout
    } catch (e: any) {
      alert(e.message);
    }
  };


  const handleTableSelect = async (tableNo: number) => {
    try {
      await bridge.call("set_table", { table_number: tableNo });
      setSelectedTable(tableNo);
      setIsTableGridOpen(false);
    } catch (e: any) {
      alert("فشل تعيين الطاولة: " + e.message);
    }
  };

  const handleCustomerSelect = async (customer: any, address: any) => {
    try {
      await bridge.call("set_customer_info", {
        customer_id: customer.id,
        name: customer.name,
        phone: customer.phone,
        address: address.street_name,
        zone: address.zone_name,
        delivery_fee: address.delivery_fee
      });
      setIsCustomerLookupOpen(false);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleApplyDiscount = async (type: "flat" | "percent", amount: number, managerPin?: string) => {
    if (!currentOrder) return;
    try {
      // Per progress.md: apply_discount requires manager authorization
      // manager/admin can apply directly; cashiers supply managerPin from the PinDialog gate in DiscountDialog
      await bridge.call("apply_discount", {
        value: amount,
        discount_type: type,
        ...(managerPin ? { manager_pin: managerPin } : {}),
      });
    } catch (e: any) {
      alert("فشل تطبيق الخصم: " + e.message);
    }
  };

  const handleParkOrder = async () => {
    if (!currentOrder || currentOrder.items.length === 0) return;
    try {
      await bridge.call("park_order");
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleCheckoutClick = async () => {
    if (!currentOrder || currentOrder.items.length === 0) return;

    // Validation: delivery and pickup both need a customer phone
    if ((currentOrder.order_type === "delivery" || currentOrder.order_type === "pickup") && !currentOrder.customer_phone) {
      alert("يرجى اختيار عميل لهذا الطلب");
      setIsCustomerLookupOpen(true);
      return;
    }

    // Validation: dine-in needs a table
    if (currentOrder.order_type === "dine_in" && !selectedTable) {
      alert("يرجى اختيار رقم الطاولة أولاً");
      setIsTableGridOpen(true);
      return;
    }

    // ── Amending mode: save changes to existing order ──────────────────
    if (isAmending) {
      try {
        const capturedTotal = currentOrder?.total || 0;
        await bridge.call("save_amendment");
        setIsAmending(false);
        // For non-delivery orders, open payment so cashier can collect
        if (currentOrder.order_type !== "delivery") {
          setPendingOrderId(currentOrder.id);
          setPendingTotal(capturedTotal);
          setIsPaymentOpen(true);
        } else {
          setSelectedTable(null);
          await fetchCurrentOrder();
          alert("تم حفظ تعديلات الطلب بنجاح!");
        }
      } catch (e: any) {
        alert("فشل حفظ التعديلات: " + e.message);
      }
      return;
    }

    // ── Normal mode: confirm new order ────────────────────────────────
    try {
      // Capture total NOW before confirm_order resets the order state
      const capturedTotal = currentOrder?.total || 0;

      // Step 1: confirm_order — validates, saves to DB, prints kitchen ticket
      const confirmRes = await bridge.call<{
        invoice_no: string;
        needs_immediate_payment: boolean;
        order_id: number;
      }>("confirm_order");

      if (confirmRes.needs_immediate_payment) {
        // Step 2A: Takeaway/dine-in — show PaymentDialog to collect payment
        setPendingOrderId(confirmRes.order_id);
        setPendingTotal(capturedTotal); // use captured total, not current (cleared) order
        setIsPaymentOpen(true);
      } else {
        // Step 2B: Delivery — no immediate payment (driver collects)
        // Clear workspace and start fresh
        setSelectedTable(null);
        await fetchCurrentOrder();
        fetchParkedCount();
        alert(`تم تأكيد الطلب بنجاح! رقم الفاتورة: ${confirmRes.invoice_no}`);
      }
    } catch (e: any) {
      alert("فشل تأكيد الطلب: " + e.message);
    }
  };

  const handlePaymentConfirm = async (paymentMethod: string, amountPaid: number, _change: number) => {
    if (!pendingOrderId) return;
    try {
      // complete_payment — marks order paid, prints customer receipt
      await bridge.call("complete_payment", {
        order_id: pendingOrderId,
        payment_method: paymentMethod,
        amount_paid: amountPaid,
      });

      setIsPaymentOpen(false);
      setPendingOrderId(null);
      setSelectedTable(null);

      // Clear workspace and start fresh
      await fetchCurrentOrder();
      fetchParkedCount();

      alert("تم تأكيد الطلب وتسجيل الدفع بنجاح!");
    } catch (e: any) {
      alert("فشل تسجيل الدفع: " + e.message);
    }
  };

  // Parked orders panel
  const handleOpenParkedPanel = async () => {
    try {
      const res = await bridge.call("get_parked_orders");
      setParkedOrders(res || []);
      setIsParkedPanelOpen(true);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleResumeParked = async (index: number) => {
    try {
      await bridge.call("resume_parked_order", { index });
      setIsParkedPanelOpen(false);
      setSelectedTable(null);
      await fetchCurrentOrder();
      fetchParkedCount();
    } catch (e: any) {
      alert("فشل استرجاع الطلب: " + e.message);
    }
  };

  const handleClearOrder = async () => {
    if (!window.confirm("هل أنت متأكد من رغبتك في مسح الطلب الحالي بالكامل؟")) return;
    try {
      await bridge.call("new_order", { order_type: currentOrder?.order_type || "dine_in" });
    } catch (e: any) {
      console.error(e);
    }
  };

  return (
    <div className="flex-1 flex flex-col md:flex-row h-[calc(100vh-64px)] overflow-hidden">
      
      {/* Right Column: Order Cart Workspace (40% width) */}
      <div className="w-full md:w-[420px] bg-brand-surface border-l border-brand-border/60 flex flex-col min-h-0">
        
        {/* Order Type Header */}
        <div className="p-4 bg-brand-card/80 border-b border-brand-border/40 space-y-3 shrink-0">
          {/* Amending indicator */}
          {isAmending && (
            <div className="py-1.5 px-3 bg-yellow-900/20 border border-yellow-700/40 rounded-lg text-xs text-yellow-400 font-bold flex items-center justify-between">
              <span>⚠️ تعديل طلب موجود</span>
              <button
                onClick={() => { setIsAmending(false); bridge.call("new_order", { order_type: "dine_in" }); }}
                className="text-[10px] text-gray-400 hover:text-white"
              >
                إلغاء التعديل
              </button>
            </div>
          )}
          <div className="grid grid-cols-4 gap-2">
            {[
              { id: "dine_in", name: "صالة" },
              { id: "takeaway", name: "تيك أواي" },
              { id: "delivery", name: "دليفري" },
              { id: "pickup", name: "استلام محل" }
            ].map((ot) => (
              <button
                key={ot.id}
                type="button"
                onClick={() => handleSetOrderType(ot.id)}
                className={`py-2 px-1 text-xs font-bold rounded-xl border transition-all ${
                  currentOrder?.order_type === ot.id
                    ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
                    : "bg-brand-surface border-brand-border/40 text-gray-400 hover:text-white"
                }`}
              >
                {ot.name}
              </button>
            ))}
          </div>

          {/* Delivery customer info block */}
          {currentOrder?.order_type === "delivery" && (
            <div className="p-3 bg-brand-surface/60 border border-brand-border/50 rounded-xl flex justify-between items-center text-xs">
              {currentOrder.customer_name ? (
                <div>
                  <span className="text-white font-bold block">{currentOrder.customer_name}</span>
                  <span className="text-gray-400 block mt-1 font-mono">{currentOrder.customer_phone}</span>
                  <span className="text-brand-gold mt-1 block">العنوان: {currentOrder.customer_address}</span>
                </div>
              ) : (
                <span className="text-gray-400 italic">لم يتم اختيار عميل (مطلوب قبل التأكيد)</span>
              )}
              <button
                onClick={() => setIsCustomerLookupOpen(true)}
                className="py-1 px-3 bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold rounded-lg"
              >
                {currentOrder.customer_name ? "تغيير" : "اختيار عميل"}
              </button>
            </div>
          )}

          {/* Pickup customer info block */}
          {currentOrder?.order_type === "pickup" && (
            <div className="p-3 bg-brand-surface/60 border border-brand-border/50 rounded-xl flex justify-between items-center text-xs">
              {currentOrder.customer_name ? (
                <div>
                  <span className="text-white font-bold block">{currentOrder.customer_name}</span>
                  <span className="text-gray-400 block mt-1 font-mono">{currentOrder.customer_phone}</span>
                </div>
              ) : (
                <span className="text-gray-400 italic">لم يتم اختيار عميل (مطلوب قبل التأكيد)</span>
              )}
              <button
                onClick={() => setIsCustomerLookupOpen(true)}
                className="py-1 px-3 bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold rounded-lg"
              >
                {currentOrder.customer_name ? "تغيير" : "اختيار عميل"}
              </button>
            </div>
          )}

          {/* Dine-in table info block */}
          {currentOrder?.order_type === "dine_in" && (
            <div className="p-3 bg-brand-surface/60 border border-brand-border/50 rounded-xl flex justify-between items-center text-xs">
              {selectedTable ? (
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">طاولة رقم:</span>
                  <span className="text-2xl font-black text-brand-gold font-mono">{selectedTable}</span>
                </div>
              ) : (
                <span className="text-red-400 italic">لم يتم اختيار طاولة بعد!</span>
              )}
              <button
                onClick={() => setIsTableGridOpen(true)}
                className="py-1 px-3 bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold rounded-lg"
              >
                {selectedTable ? "تغيير الطاولة" : "اختيار طاولة"}
              </button>
            </div>
          )}
        </div>

        {/* Order Item Lines */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {currentOrder?.items && currentOrder.items.length > 0 ? (
            currentOrder.items.map((item: any, idx: number) => (
              <div
                key={idx}
                className="p-3 bg-brand-card/40 border border-brand-border/30 rounded-xl flex justify-between items-center hover:bg-brand-card/60 transition-all"
              >
                {/* Product Name & Qty */}
                <div className="flex-1">
                  <span className="text-white font-bold text-sm block">{item.product_name}</span>
                  <span className="text-xs text-brand-gold font-bold mt-1 inline-block">
                    {item.unit_price} ج.م
                  </span>
                  {item.notes && (
                    <span className="text-[10px] text-gray-500 block mt-0.5 bg-brand-dark/20 p-1 rounded">
                      ملاحظة: {item.notes}
                    </span>
                  )}
                </div>

                {/* Controls */}
                <div className="flex items-center gap-3">
                  <div className="flex items-center bg-brand-card border border-brand-border/40 rounded-xl p-1">
                    <button
                      onClick={() => handleQtyChange(idx, 1)}
                      className="h-8 w-8 text-white hover:text-brand-gold flex items-center justify-center rounded-lg active:scale-95"
                    >
                      <Plus size={16} />
                    </button>
                    <span className="w-8 text-center text-white font-bold font-mono">{item.quantity}</span>
                    <button
                      onClick={() => handleQtyChange(idx, -1)}
                      className="h-8 w-8 text-white hover:text-brand-gold flex items-center justify-center rounded-lg active:scale-95"
                    >
                      <Minus size={16} />
                    </button>
                  </div>

                  <button
                    onClick={() => handleDeleteItemClick(idx)}
                    className="h-9 w-9 text-red-400 hover:text-red-300 bg-red-950/20 hover:bg-red-950/50 border border-red-900/30 rounded-xl flex items-center justify-center"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-500 space-y-2">
              <ShoppingBag size={48} className="text-brand-border/50" />
              <p className="text-sm">سلة المشتريات فارغة</p>
              <p className="text-xs">اضغط على أي وجبة في اليسار لإضافتها للطلب</p>
            </div>
          )}
        </div>

        {/* Totals Summary */}
        <div className="p-4 bg-brand-card border-t border-brand-border/60 space-y-4 shrink-0">
          <div className="space-y-2 text-xs">
            <div className="flex justify-between items-center text-gray-400">
              <span>المجموع الفرعي:</span>
              <span className="font-bold font-mono text-white">{(currentOrder?.subtotal || 0).toFixed(2)} ج.م</span>
            </div>
            {currentOrder?.discount_amount > 0 && (
              <div className="flex justify-between items-center text-red-400">
                <span>الخصم المطبق:</span>
                <span className="font-bold font-mono">-{currentOrder.discount_amount.toFixed(2)} ج.م</span>
              </div>
            )}
            {currentOrder?.delivery_fee > 0 && (
              <div className="flex justify-between items-center text-brand-gold">
                <span>خدمة التوصيل (الطيار):</span>
                <span className="font-bold font-mono">+{currentOrder.delivery_fee.toFixed(2)} ج.m</span>
              </div>
            )}
            <div className="h-px bg-brand-border/30" />
            <div className="flex justify-between items-center">
              <span className="text-base font-bold text-white">الإجمالي الكلي:</span>
              <span className="text-2xl font-black text-brand-gold font-mono">
                {(currentOrder?.total || 0).toFixed(2)} ج.م
              </span>
            </div>
          </div>

          {/* Action keys */}
          <div className="grid grid-cols-3 gap-2">
            <button
              onClick={handleClearOrder}
              className="py-3 bg-brand-border/20 border border-brand-border/40 hover:bg-brand-border/40 text-gray-300 font-bold rounded-xl text-xs active:translate-y-0.5 btn-hover-active flex items-center justify-center gap-1"
            >
              <RotateCcw size={14} />
              مسح
            </button>
            <button
              onClick={handleParkOrder}
              disabled={!currentOrder || currentOrder.items.length === 0}
              className="py-3 bg-brand-card hover:bg-brand-border/20 text-brand-gold border border-brand-gold/20 rounded-xl text-xs font-bold active:translate-y-0.5 btn-hover-active flex items-center justify-center gap-1 disabled:opacity-50"
            >
              <Tag size={14} />
              تعليق
            </button>
            <button
              onClick={() => setIsDiscountOpen(true)}
              disabled={!currentOrder || currentOrder.items.length === 0}
              className="py-3 bg-brand-card hover:bg-brand-border/20 text-brand-gold border border-brand-gold/20 rounded-xl text-xs font-bold active:translate-y-0.5 btn-hover-active flex items-center justify-center gap-1 disabled:opacity-50"
            >
              <Tag size={14} />
              خصم
            </button>
          </div>

          {/* Parked orders retrieval button */}
          {parkedCount > 0 && (
            <button
              onClick={handleOpenParkedPanel}
              className="w-full py-2.5 bg-brand-card hover:bg-brand-border/20 text-brand-gold border border-brand-gold/30 rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition-all"
            >
              <Archive size={14} />
              استرجاع طلب معلّق ({parkedCount})
            </button>
          )}

          <button
            onClick={handleCheckoutClick}
            disabled={!currentOrder || currentOrder.items.length === 0}
            className={`w-full py-4 ${isAmending ? "bg-orange-500 hover:bg-orange-400" : "bg-brand-gold hover:bg-opacity-95"} text-brand-dark disabled:opacity-50 font-black text-lg rounded-2xl flex items-center justify-center gap-2 shadow-lg active:translate-y-0.5 btn-hover-active transition-colors`}
          >
            <CreditCard size={20} />
            {isAmending ? "حفظ التعديلات" : "تأكيد ودفع الفاتورة"}
          </button>
        </div>

      </div>

      {/* Left Column: Product Selection Area (60% width) */}
      <div className="flex-1 flex flex-col bg-brand-dark">
        
        {/* Category horizontal bar & search */}
        <div className="p-4 bg-brand-card/30 border-b border-brand-border/40 flex flex-col md:flex-row gap-4 items-center justify-between">
          
          {/* Search bar */}
          <div className="relative w-full md:w-72">
            <input
              type="text"
              placeholder="ابحث عن وجبة أو مشروب..."
              value={searchQuery}
              onChange={(e) => handleProductSearch(e.target.value)}
              className="w-full bg-brand-card border border-brand-border/60 rounded-xl py-2 px-4 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-gold text-right"
            />
            <Search className="absolute left-3 top-2.5 text-gray-500" size={16} />
          </div>

          {/* Category Tabs */}
          <div className="flex gap-2 overflow-x-auto w-full md:w-auto pb-1 md:pb-0 pr-1">
            {categories.map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => {
                  setSelectedCatId(cat.id);
                  setSearchQuery("");
                }}
                className={`py-2 px-4 text-xs font-bold rounded-full border whitespace-nowrap transition-all ${
                  selectedCatId === cat.id && !searchQuery
                    ? "bg-brand-gold text-brand-dark border-brand-gold"
                    : "bg-brand-card border-brand-border/40 text-gray-400 hover:text-white"
                }`}
              >
                {cat.name}
              </button>
            ))}
          </div>
        </div>

        {/* Product Cards Grid */}
        <div className="flex-1 overflow-y-auto p-6">
          {products.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {products.map((prod) => (
                <div
                  key={prod.id}
                  onClick={() => handleAddProduct(prod)}
                  className="p-4 bg-brand-card hover:bg-brand-border/10 border border-brand-border/40 rounded-2xl cursor-pointer flex flex-col justify-between h-40 transition-all hover:scale-[1.03] active:scale-[0.97] group"
                >
                  <div>
                    <h4 className="text-white font-bold text-sm leading-snug group-hover:text-brand-gold transition-colors">
                      {prod.name}
                    </h4>
                  </div>
                  <div className="flex justify-between items-center mt-4">
                    <span className="text-brand-gold font-extrabold text-base">
                      {prod.price} <span className="text-[10px] font-semibold">ج.م</span>
                    </span>
                    <div className="h-8 w-8 rounded-full bg-brand-gold/10 text-brand-gold flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <Plus size={16} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center text-gray-500">
              <AlertCircle size={48} className="text-brand-border/50 mb-2" />
              <p className="text-sm">لا توجد وجبات لعرضها</p>
            </div>
          )}
        </div>

      </div>

      {/* Dialogs and keypads */}
      <DiscountDialog
        isOpen={isDiscountOpen}
        onClose={() => setIsDiscountOpen(false)}
        onApply={handleApplyDiscount}
        currentUser={currentUser}
        subtotal={currentOrder?.subtotal || 0}
      />

      <PaymentDialog
        isOpen={isPaymentOpen}
        onClose={() => {
          setIsPaymentOpen(false);
          setPendingOrderId(null);
          setPendingTotal(0);
        }}
        total={pendingTotal}
        orderType={currentOrder?.order_type}
        onConfirm={handlePaymentConfirm}
      />

      <CustomerLookup
        isOpen={isCustomerLookupOpen}
        onClose={() => setIsCustomerLookupOpen(false)}
        onSelect={handleCustomerSelect}
      />

      <TableGrid
        isOpen={isTableGridOpen}
        selectedTable={selectedTable}
        onSelect={handleTableSelect}
        onClose={() => setIsTableGridOpen(false)}
        occupiedTables={occupiedTables}
      />

      <PinDialog
        isOpen={showPinGate}
        onClose={() => {
          setShowPinGate(false);
          setPendingDeleteIdx(null);
        }}
        onSuccess={(_managerUser, rawPin) => {
          // Pass manager pin so bridge can audit the removal
          if (pendingDeleteIdx !== null) {
            bridge.call("remove_item", { index: pendingDeleteIdx, manager_pin: rawPin })
              .then(() => setPendingDeleteIdx(null))
              .catch((e: any) => alert(e.message));
          }
        }}
        title="موافقة المدير مطلوبة لحذف عنصر من السلة"
      />

      {/* Parked Orders Slide-Out Panel */}
      {isParkedPanelOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
          <div className="w-full max-w-md mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="p-5 border-b border-brand-border/40 flex items-center justify-between">
              <h3 className="font-bold text-xl text-brand-gold">الطلبات المعلّقة</h3>
              <button
                onClick={() => setIsParkedPanelOpen(false)}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
              >
                <X size={20} />
              </button>
            </div>
            <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
              {parkedOrders.length > 0 ? (
                parkedOrders.map((order: any, idx: number) => (
                  <button
                    key={idx}
                    onClick={() => handleResumeParked(idx)}
                    className="w-full p-4 bg-brand-card/60 border border-brand-border/40 rounded-xl text-right hover:bg-brand-card hover:border-brand-gold/30 transition-all group"
                  >
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs text-gray-500 font-bold uppercase">
                        {order.order_type === "dine_in" ? "صالة" : order.order_type === "takeaway" ? "تيك أواي" : order.order_type === "delivery" ? "دليفري" : "استلام"}
                      </span>
                      <span className="text-brand-gold font-black text-lg font-mono">
                        {(order.total || 0).toFixed(2)} ج.م
                      </span>
                    </div>
                    <div className="text-xs text-gray-400">
                      {order.items?.length || 0} عناصر
                    </div>
                  </button>
                ))
              ) : (
                <div className="text-center text-gray-500 py-8">
                  <Archive size={32} className="mx-auto mb-2 text-brand-border/50" />
                  <p className="text-sm">لا توجد طلبات معلّقة</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
