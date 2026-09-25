import React, { useState, useEffect } from "react";
import {
  Eye, RefreshCw, AlertCircle, Loader2, X, ShoppingBag,
  UtensilsCrossed, Truck, Package, CheckCircle2
} from "lucide-react";
import { bridge } from "../bridge";

interface TrackingViewProps {
  currentUser: any;
}

const ORDER_TYPE_LABELS: Record<string, { label: string; icon: any; color: string }> = {
  dine_in:  { label: "صالة",           icon: UtensilsCrossed, color: "text-brand-gold bg-brand-gold/10 border-brand-gold/30" },
  takeaway: { label: "تيك أواي",        icon: ShoppingBag,    color: "text-brand-teal bg-brand-teal/10 border-brand-teal/30" },
  delivery: { label: "دليفري",          icon: Truck,           color: "text-blue-400 bg-blue-900/20 border-blue-800/30" },
  pickup:   { label: "استلام",          icon: Package,         color: "text-purple-400 bg-purple-900/20 border-purple-800/30" },
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  new:              { label: "جديد — في الانتظار",    color: "text-yellow-400" },
  confirmed:        { label: "مؤكد",                  color: "text-brand-gold" },
  out_for_delivery: { label: "خرج للتوصيل",           color: "text-blue-400" },
  completed:        { label: "مكتمل",                  color: "text-brand-teal" },
  cancelled:        { label: "ملغي",                   color: "text-red-400" },
};

export const TrackingView: React.FC<TrackingViewProps> = ({ currentUser }) => {
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState<string>("all");
  const [showCancelPinGate, setShowCancelPinGate] = useState(false);
  const [pendingCancelOrderId, setPendingCancelOrderId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  const isManagerOrAbove =
    currentUser?.role === "manager" || currentUser?.role === "admin";

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const res = await bridge.call("get_active_orders");
      setOrders(res || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    // Refresh every 30 seconds
    const interval = setInterval(fetchOrders, 30_000);
    return () => clearInterval(interval);
  }, []);

  const filteredOrders =
    filterType === "all"
      ? orders
      : orders.filter((o) => o.order_type === filterType);

  const [cancelPin, setCancelPin] = useState("");

  const handleCancelClick = (orderId: number) => {
    setPendingCancelOrderId(orderId);
    setCancelReason("");
    setCancelPin("");
    setShowCancelPinGate(true);
  };

  const performCancel = async () => {
    if (!pendingCancelOrderId) return;
    if (!cancelReason.trim()) {
      alert("يجب إدخال سبب الإلغاء");
      return;
    }
    if (!cancelPin.trim()) {
      alert("يجب إدخال رمز PIN المدير");
      return;
    }
    try {
      await bridge.call("cancel_order", {
        order_id: pendingCancelOrderId,
        manager_pin: cancelPin,
        reason: cancelReason,
      });
      setShowCancelPinGate(false);
      setPendingCancelOrderId(null);
      setCancelReason("");
      setCancelPin("");
      fetchOrders();
    } catch (e: any) {
      alert("فشل إلغاء الطلب: " + e.message);
    }
  };

  if (loading && orders.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)] bg-brand-dark">
        <Loader2 className="animate-spin text-brand-gold" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل الطلبات النشطة...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 h-[calc(100vh-64px)] bg-brand-dark">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-brand-gold/10 text-brand-gold flex items-center justify-center">
            <Eye size={20} />
          </div>
          <div>
            <h2 className="text-xl font-black text-white">متابعة الطلبات النشطة</h2>
            <p className="text-xs text-gray-400">
              {filteredOrders.length} طلب نشط
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Filter tabs */}
          {[
            { id: "all", label: "الكل" },
            { id: "dine_in", label: "صالة" },
            { id: "takeaway", label: "تيك أواي" },
            { id: "delivery", label: "دليفري" },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setFilterType(f.id)}
              className={`py-1.5 px-3 rounded-xl text-xs font-bold border transition-all ${
                filterType === f.id
                  ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
                  : "bg-brand-card border-brand-border/40 text-gray-400 hover:text-white"
              }`}
            >
              {f.label}
            </button>
          ))}

          <button
            onClick={fetchOrders}
            className={`p-2 bg-brand-card border border-brand-border/40 hover:border-brand-gold text-gray-400 hover:text-brand-gold rounded-xl transition-all ${
              loading ? "animate-spin text-brand-gold" : ""
            }`}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Orders grid */}
      {filteredOrders.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredOrders.map((order) => {
            const typeInfo =
              ORDER_TYPE_LABELS[order.order_type] || ORDER_TYPE_LABELS.takeaway;
            const TypeIcon = typeInfo.icon;
            const statusInfo =
              STATUS_LABELS[order.status] || { label: order.status, color: "text-gray-400" };
            const canCancel =
              isManagerOrAbove &&
              order.status !== "completed" &&
              order.status !== "cancelled" &&
              order.status !== "out_for_delivery";

            return (
              <div
                key={order.id}
                className="p-4 bg-brand-card border border-brand-border/30 rounded-2xl space-y-3 hover:border-brand-border/70 transition-all animate-in fade-in duration-150"
              >
                {/* Header */}
                <div className="flex justify-between items-start">
                  <span
                    className={`py-1 px-2.5 rounded-lg border text-[10px] font-bold flex items-center gap-1 ${typeInfo.color}`}
                  >
                    <TypeIcon size={12} />
                    {typeInfo.label}
                  </span>
                  <span className="text-xs text-gray-500 font-mono">
                    #{order.invoice_no || order.id}
                  </span>
                </div>

                {/* Table / Customer */}
                {order.order_type === "dine_in" && order.table_no && (
                  <div className="text-brand-gold font-black text-2xl font-mono">
                    طاولة {order.table_no}
                  </div>
                )}
                {(order.order_type === "delivery" || order.order_type === "pickup") &&
                  order.customer_name && (
                    <div>
                      <span className="text-white font-bold text-sm block">
                        {order.customer_name}
                      </span>
                      {order.customer_address && (
                        <span className="text-xs text-gray-400 block truncate">
                          {order.customer_address}
                        </span>
                      )}
                    </div>
                  )}

                {/* Items summary */}
                <div className="text-xs text-gray-400 space-y-0.5">
                  {(order.items || []).slice(0, 3).map((item: any, i: number) => (
                    <div key={i} className="flex justify-between">
                      <span className="truncate">{item.product_name}</span>
                      <span className="text-gray-500 ml-1 flex-shrink-0">×{item.quantity}</span>
                    </div>
                  ))}
                  {(order.items || []).length > 3 && (
                    <div className="text-gray-600 text-[10px]">
                      + {order.items.length - 3} عناصر أخرى
                    </div>
                  )}
                </div>

                {/* Status + total */}
                <div className="flex justify-between items-center pt-1 border-t border-brand-border/20">
                  <span className={`text-xs font-bold ${statusInfo.color}`}>
                    {statusInfo.label}
                  </span>
                  <span className="text-brand-gold font-black text-sm font-mono">
                    {(order.total || 0).toFixed(2)} ج.م
                  </span>
                </div>

                {/* Cancel button */}
                {canCancel && (
                  <button
                    onClick={() => handleCancelClick(order.id)}
                    className="w-full py-1.5 text-xs font-bold text-red-400 border border-red-900/30 bg-red-950/20 hover:bg-red-950/40 rounded-lg flex items-center justify-center gap-1.5 transition-all"
                  >
                    <X size={12} />
                    إلغاء الطلب
                  </button>
                )}

                {order.status === "completed" && (
                  <div className="w-full py-1.5 text-xs text-brand-teal font-bold flex items-center justify-center gap-1.5">
                    <CheckCircle2 size={12} />
                    مكتمل ومدفوع
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center py-24 text-gray-500 text-center">
          <AlertCircle size={48} className="text-brand-border/50 mb-3" />
          <p className="text-base font-bold text-gray-400 mb-1">لا توجد طلبات نشطة حالياً</p>
          <p className="text-sm">ستظهر الطلبات هنا بمجرد تأكيدها من شاشة البيع.</p>
        </div>
      )}

      {/* Cancel Modal — reason + manager PIN in one dialog */}
      {showCancelPinGate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
          <div className="w-full max-w-sm mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="p-5 border-b border-brand-border/40 flex items-center justify-between">
              <h3 className="font-bold text-lg text-red-400 flex items-center gap-2">
                <X size={18} />
                إلغاء الطلب — موافقة المدير
              </h3>
              <button
                onClick={() => {
                  setShowCancelPinGate(false);
                  setPendingCancelOrderId(null);
                  setCancelReason("");
                  setCancelPin("");
                }}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="text-gray-400 text-xs block mb-1">سبب الإلغاء (مطلوب)</label>
                <input
                  type="text"
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                  placeholder="مثال: طلب العميل إلغاء الطلب..."
                  className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white placeholder-gray-600 focus:outline-none focus:border-brand-gold text-right"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-gray-400 text-xs block mb-1">رمز PIN المدير</label>
                <input
                  type="password"
                  value={cancelPin}
                  onChange={(e) => setCancelPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
                  placeholder="● ● ● ●"
                  maxLength={4}
                  className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white placeholder-gray-500 focus:outline-none focus:border-red-500 font-mono text-center text-2xl tracking-widest"
                />
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setShowCancelPinGate(false);
                    setPendingCancelOrderId(null);
                    setCancelReason("");
                    setCancelPin("");
                  }}
                  className="flex-1 py-2.5 bg-brand-card border border-brand-border/40 text-gray-300 rounded-xl font-bold text-sm"
                >
                  إلغاء
                </button>
                <button
                  onClick={performCancel}
                  disabled={!cancelReason.trim() || cancelPin.length < 4}
                  className="flex-1 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-bold text-sm transition-all"
                >
                  تأكيد الإلغاء
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
