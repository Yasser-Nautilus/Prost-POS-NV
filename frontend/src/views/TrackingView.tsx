import React, { useState, useEffect, useCallback } from "react";
import {
  Eye, RefreshCw, Loader2, X,
  UtensilsCrossed, Truck, Package, ShoppingBag, PlusCircle
} from "lucide-react";
import { bridge } from "../bridge";

interface TrackingViewProps {
  currentUser: any;
  onResumeOrder?: (order: any) => void;
}

const ORDER_TYPE_LABELS: Record<string, { label: string; icon: any; color: string }> = {
  dine_in:  { label: "صالة",        icon: UtensilsCrossed, color: "text-brand-gold bg-brand-gold/10 border-brand-gold/30" },
  takeaway: { label: "تيك أواي",     icon: ShoppingBag,    color: "text-brand-teal bg-brand-teal/10 border-brand-teal/30" },
  delivery: { label: "دليفري",       icon: Truck,           color: "text-blue-400 bg-blue-900/20 border-blue-800/30" },
  pickup:   { label: "استلام محل",   icon: Package,         color: "text-purple-400 bg-purple-900/20 border-purple-800/30" },
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  new:              { label: "جديد — في الانتظار",  color: "text-yellow-400" },
  confirmed:        { label: "مؤكد",                 color: "text-brand-gold" },
  out_for_delivery: { label: "خرج للتوصيل",          color: "text-blue-400" },
  completed:        { label: "مكتمل",                 color: "text-green-400" },
  cancelled:        { label: "ملغي",                  color: "text-red-400" },
};

/** Format elapsed time from a datetime string → "HH:MM:SS" */
function formatElapsed(dateStr: string | null): string {
  if (!dateStr) return "—";
  const secs = Math.max(0, Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return [h, m, s].map((v) => v.toString().padStart(2, "0")).join(":");
}

/** Self-updating timer cell */
const LiveTimer: React.FC<{ since: string | null; urgentSecs?: number }> = ({ since, urgentSecs = 1800 }) => {
  const [display, setDisplay] = useState(() => formatElapsed(since));
  const [isUrgent, setIsUrgent] = useState(false);
  useEffect(() => {
    const update = () => {
      setDisplay(formatElapsed(since));
      if (since) {
        const elapsed = Math.floor((Date.now() - new Date(since).getTime()) / 1000);
        setIsUrgent(elapsed >= urgentSecs);
      }
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [since, urgentSecs]);
  return (
    <span className={`font-mono font-bold tabular-nums text-xs ${isUrgent ? "text-red-400 animate-pulse" : "text-brand-gold"}`}>
      {display}
    </span>
  );
};

// ─── Per-type table columns ───────────────────────────────────────────────────

const DineInTable: React.FC<{ orders: any[]; onCancel: (id: number) => void; onResume: (o: any) => void; canCancel: boolean }> =
  ({ orders, onCancel, onResume, canCancel }) => (
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-brand-card/80 text-gray-400 text-xs">
          <th className="py-2.5 px-3 text-right">#فاتورة</th>
          <th className="py-2.5 px-3 text-right">الطاولة</th>
          <th className="py-2.5 px-3 text-right">العناصر</th>
          <th className="py-2.5 px-3 text-center">الحالة</th>
          <th className="py-2.5 px-3 text-center">المنقضي</th>
          <th className="py-2.5 px-3 text-center font-mono">الإجمالي</th>
          <th className="py-2.5 px-3 text-center">إجراء</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((order, i) => {
          const status = STATUS_LABELS[order.status] || { label: order.status, color: "text-gray-400" };
          return (
            <tr key={order.id} className={`border-t border-brand-border/20 ${i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}>
              <td className="py-2.5 px-3 text-gray-400 font-mono text-xs">#{order.invoice_no || order.id}</td>
              <td className="py-2.5 px-3">
                <span className="text-brand-gold font-black text-lg font-mono">{order.table_no || "—"}</span>
              </td>
              <td className="py-2.5 px-3 text-gray-400 text-xs">
                {(order.items || []).slice(0, 2).map((it: any, j: number) => (
                  <div key={j}>{it.product_name} ×{it.quantity}</div>
                ))}
                {(order.items || []).length > 2 && <div className="text-gray-600">+{order.items.length - 2} أخرى</div>}
              </td>
              <td className="py-2.5 px-3 text-center">
                <span className={`text-[10px] font-bold ${status.color}`}>{status.label}</span>
              </td>
              <td className="py-2.5 px-3 text-center">
                <LiveTimer since={order.created_at} urgentSecs={1800} />
              </td>
              <td className="py-2.5 px-3 text-center text-brand-gold font-black font-mono text-sm">
                {(order.total || 0).toFixed(2)} ج.م
              </td>
              <td className="py-2.5 px-3">
                <div className="flex items-center gap-1.5 justify-center">
                  <button
                    onClick={() => onResume(order)}
                    className="py-1 px-2 bg-brand-gold/10 text-brand-gold border border-brand-gold/30 hover:bg-brand-gold/20 rounded-lg text-[10px] font-bold flex items-center gap-0.5 transition-all"
                    title="إضافة أصناف للطلب"
                  >
                    <PlusCircle size={11} /> إضافة
                  </button>
                  {canCancel && order.status !== "completed" && order.status !== "cancelled" && (
                    <button
                      onClick={() => onCancel(order.id)}
                      className="py-1 px-2 bg-red-950/20 text-red-400 border border-red-900/30 hover:bg-red-950/40 rounded-lg text-[10px] font-bold transition-all"
                    >
                      <X size={11} />
                    </button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

const DeliveryPickupTable: React.FC<{ orders: any[]; onCancel: (id: number) => void; onResume: (o: any) => void; canCancel: boolean }> =
  ({ orders, onCancel, onResume, canCancel }) => (
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-brand-card/80 text-gray-400 text-xs">
          <th className="py-2.5 px-3 text-right">#فاتورة</th>
          <th className="py-2.5 px-3 text-right">العميل</th>
          <th className="py-2.5 px-3 text-right">المنطقة/العنوان</th>
          <th className="py-2.5 px-3 text-center">الحالة</th>
          <th className="py-2.5 px-3 text-center">المنقضي</th>
          <th className="py-2.5 px-3 text-center font-mono">الإجمالي</th>
          <th className="py-2.5 px-3 text-center">إجراء</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((order, i) => {
          const status = STATUS_LABELS[order.status] || { label: order.status, color: "text-gray-400" };
          const canAddItems = order.status === "new"; // only unassigned delivery orders
          return (
            <tr key={order.id} className={`border-t border-brand-border/20 ${i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}>
              <td className="py-2.5 px-3 text-gray-400 font-mono text-xs">#{order.invoice_no || order.id}</td>
              <td className="py-2.5 px-3">
                <span className="text-white font-bold text-sm">{order.customer_name || "—"}</span>
                {order.customer_phone && (
                  <span className="text-gray-500 font-mono block text-[10px]">{order.customer_phone}</span>
                )}
              </td>
              <td className="py-2.5 px-3 text-gray-400 text-xs">
                {order.customer_zone && <div className="text-brand-gold">{order.customer_zone}</div>}
                {order.customer_address && <div className="truncate max-w-[120px]">{order.customer_address}</div>}
              </td>
              <td className="py-2.5 px-3 text-center">
                <span className={`text-[10px] font-bold ${status.color}`}>{status.label}</span>
              </td>
              <td className="py-2.5 px-3 text-center">
                <LiveTimer since={order.created_at} urgentSecs={1200} />
              </td>
              <td className="py-2.5 px-3 text-center text-brand-gold font-black font-mono text-sm">
                {(order.total || 0).toFixed(2)} ج.م
              </td>
              <td className="py-2.5 px-3">
                <div className="flex items-center gap-1.5 justify-center">
                  {canAddItems && (
                    <button
                      onClick={() => onResume(order)}
                      className="py-1 px-2 bg-brand-gold/10 text-brand-gold border border-brand-gold/30 hover:bg-brand-gold/20 rounded-lg text-[10px] font-bold flex items-center gap-0.5 transition-all"
                      title="إضافة أصناف للطلب"
                    >
                      <PlusCircle size={11} /> إضافة
                    </button>
                  )}
                  {canCancel && order.status !== "completed" && order.status !== "cancelled" && order.status !== "out_for_delivery" && (
                    <button
                      onClick={() => onCancel(order.id)}
                      className="py-1 px-2 bg-red-950/20 text-red-400 border border-red-900/30 hover:bg-red-950/40 rounded-lg text-[10px] font-bold transition-all"
                    >
                      <X size={11} />
                    </button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

const TakeawayTable: React.FC<{ orders: any[]; onCancel: (id: number) => void; onResume: (o: any) => void; canCancel: boolean }> =
  ({ orders, onCancel, onResume, canCancel }) => (
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-brand-card/80 text-gray-400 text-xs">
          <th className="py-2.5 px-3 text-right">#فاتورة</th>
          <th className="py-2.5 px-3 text-right">العناصر</th>
          <th className="py-2.5 px-3 text-center">الحالة</th>
          <th className="py-2.5 px-3 text-center">المنقضي</th>
          <th className="py-2.5 px-3 text-center font-mono">الإجمالي</th>
          <th className="py-2.5 px-3 text-center">إجراء</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((order, i) => {
          const status = STATUS_LABELS[order.status] || { label: order.status, color: "text-gray-400" };
          return (
            <tr key={order.id} className={`border-t border-brand-border/20 ${i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}>
              <td className="py-2.5 px-3 text-gray-400 font-mono text-xs">#{order.invoice_no || order.id}</td>
              <td className="py-2.5 px-3 text-gray-400 text-xs">
                {(order.items || []).slice(0, 3).map((it: any, j: number) => (
                  <div key={j}>{it.product_name} ×{it.quantity}</div>
                ))}
                {(order.items || []).length > 3 && <div className="text-gray-600">+{order.items.length - 3} أخرى</div>}
              </td>
              <td className="py-2.5 px-3 text-center">
                <span className={`text-[10px] font-bold ${status.color}`}>{status.label}</span>
              </td>
              <td className="py-2.5 px-3 text-center">
                <LiveTimer since={order.created_at} urgentSecs={900} />
              </td>
              <td className="py-2.5 px-3 text-center text-brand-gold font-black font-mono text-sm">
                {(order.total || 0).toFixed(2)} ج.م
              </td>
              <td className="py-2.5 px-3 text-center">
                <div className="flex items-center gap-1.5 justify-center">
                  <button
                    onClick={() => onResume(order)}
                    className="py-1 px-2 bg-brand-gold/10 text-brand-gold border border-brand-gold/30 hover:bg-brand-gold/20 rounded-lg text-[10px] font-bold flex items-center gap-0.5 transition-all"
                  >
                    <PlusCircle size={11} /> إضافة
                  </button>
                  {canCancel && order.status !== "completed" && order.status !== "cancelled" && (
                    <button
                      onClick={() => onCancel(order.id)}
                      className="py-1 px-2 bg-red-950/20 text-red-400 border border-red-900/30 hover:bg-red-950/40 rounded-lg text-[10px] font-bold transition-all"
                    >
                      <X size={11} />
                    </button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

// ─── Main View ────────────────────────────────────────────────────────────────

export const TrackingView: React.FC<TrackingViewProps> = ({ currentUser, onResumeOrder }) => {
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState<string>("all");

  // Cancel dialog state
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const [pendingCancelOrderId, setPendingCancelOrderId] = useState<number | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelPin, setCancelPin] = useState("");

  const isManagerOrAbove = currentUser?.role === "manager" || currentUser?.role === "admin";

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const res = await bridge.call("get_active_orders");
      setOrders(res || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
    const id = setInterval(fetchOrders, 30_000);
    return () => clearInterval(id);
  }, [fetchOrders]);

  const filteredOrders =
    filterType === "all" ? orders : orders.filter((o) => o.order_type === filterType);

  // Group by type for display
  const byType: Record<string, any[]> = {};
  for (const o of filteredOrders) {
    if (!byType[o.order_type]) byType[o.order_type] = [];
    byType[o.order_type].push(o);
  }

  const handleCancelClick = (orderId: number) => {
    setPendingCancelOrderId(orderId);
    setCancelReason("");
    setCancelPin("");
    setShowCancelDialog(true);
  };

  const performCancel = async () => {
    if (!pendingCancelOrderId) return;
    if (!cancelReason.trim()) { alert("يجب إدخال سبب الإلغاء"); return; }
    if (!cancelPin.trim()) { alert("يجب إدخال رمز PIN المدير"); return; }
    try {
      const ok = await bridge.call("cancel_order", {
        order_id: pendingCancelOrderId,
        manager_pin: cancelPin,
        reason: cancelReason,
      });
      if (ok) {
        setShowCancelDialog(false);
        fetchOrders();
      }
    } catch (e: any) {
      alert("فشل الإلغاء: " + e.message);
    }
  };

  const handleResume = async (order: any) => {
    try {
      await bridge.call("load_order", { order_id: order.id });
      onResumeOrder?.(order);
    } catch (e: any) {
      alert("فشل تحميل الطلب: " + e.message);
    }
  };

  const TYPE_ORDER = ["dine_in", "delivery", "pickup", "takeaway"];
  const displayTypes = filterType === "all" ? TYPE_ORDER : [filterType];

  if (loading && orders.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)]">
        <Loader2 className="animate-spin text-brand-gold" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل الطلبات...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-5 h-[calc(100vh-64px)] bg-brand-dark">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-brand-gold/10 text-brand-gold flex items-center justify-center">
            <Eye size={20} />
          </div>
          <div>
            <h2 className="text-xl font-black text-white">متابعة الطلبات النشطة</h2>
            <p className="text-xs text-gray-400">{filteredOrders.length} طلب نشط</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {[
            { id: "all", label: "الكل" },
            { id: "dine_in", label: "صالة" },
            { id: "takeaway", label: "تيك أواي" },
            { id: "delivery", label: "دليفري" },
            { id: "pickup", label: "استلام محل" },
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
            className={`p-2 bg-brand-card border border-brand-border/40 hover:border-brand-gold text-gray-400 hover:text-brand-gold rounded-xl transition-all ${loading ? "animate-spin" : ""}`}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Order tables by type */}
      {filteredOrders.length === 0 ? (
        <div className="py-20 text-center text-gray-500">
          <Eye size={48} className="mx-auto mb-3 text-brand-border/30" />
          <p>لا توجد طلبات نشطة حالياً</p>
        </div>
      ) : (
        displayTypes.map((type) => {
          const typeOrders = byType[type];
          if (!typeOrders || typeOrders.length === 0) return null;
          const typeInfo = ORDER_TYPE_LABELS[type] || ORDER_TYPE_LABELS.takeaway;
          const TypeIcon = typeInfo.icon;
          return (
            <div key={type} className="rounded-2xl border border-brand-border/40 overflow-hidden">
              <div className={`px-4 py-2.5 flex items-center gap-2 border-b border-brand-border/30 ${typeInfo.color}`}>
                <TypeIcon size={15} />
                <span className="font-bold text-sm">{typeInfo.label}</span>
                <span className="ml-auto bg-black/20 text-xs font-bold px-2 py-0.5 rounded-full">{typeOrders.length}</span>
              </div>
              {(type === "dine_in") && (
                <DineInTable
                  orders={typeOrders}
                  onCancel={handleCancelClick}
                  onResume={handleResume}
                  canCancel={isManagerOrAbove}
                />
              )}
              {(type === "delivery" || type === "pickup") && (
                <DeliveryPickupTable
                  orders={typeOrders}
                  onCancel={handleCancelClick}
                  onResume={handleResume}
                  canCancel={isManagerOrAbove}
                />
              )}
              {type === "takeaway" && (
                <TakeawayTable
                  orders={typeOrders}
                  onCancel={handleCancelClick}
                  onResume={handleResume}
                  canCancel={isManagerOrAbove}
                />
              )}
            </div>
          );
        })
      )}

      {/* Cancel Dialog */}
      {showCancelDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
          <div className="w-full max-w-sm mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200 p-6 space-y-4">
            <h3 className="font-bold text-xl text-red-400">إلغاء الطلب</h3>
            <div>
              <label className="text-gray-400 text-xs block mb-1.5">سبب الإلغاء (مطلوب)</label>
              <textarea
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                rows={2}
                className="w-full bg-brand-dark border border-brand-border/50 rounded-xl p-3 text-white text-sm focus:outline-none focus:border-red-500 resize-none"
                placeholder="اكتب سبب الإلغاء..."
              />
            </div>
            <div>
              <label className="text-gray-400 text-xs block mb-1.5">PIN المدير</label>
              <input
                type="password"
                value={cancelPin}
                onChange={(e) => setCancelPin(e.target.value)}
                className="w-full bg-brand-dark border border-brand-border/50 rounded-xl p-3 text-white font-mono text-center text-lg tracking-widest focus:outline-none focus:border-red-500"
                placeholder="••••"
                maxLength={6}
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowCancelDialog(false)}
                className="flex-1 py-3 bg-brand-card border border-brand-border/40 text-gray-300 font-bold rounded-xl hover:bg-brand-border/20 transition-all"
              >
                تراجع
              </button>
              <button
                onClick={performCancel}
                className="flex-1 py-3 bg-red-900/40 text-red-300 border border-red-900/50 font-bold rounded-xl hover:bg-red-900/60 transition-all"
              >
                تأكيد الإلغاء
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
