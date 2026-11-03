/**
 * CustomerHistoryModal — Order history and stats for a single customer.
 *
 * Usage:
 *   <CustomerHistoryModal
 *     customerId={123}
 *     customerName="ياسر المصري"
 *     onClose={() => setCustomerId(null)}
 *   />
 *
 * Alternatively, trigger by phone lookup:
 *   <CustomerHistoryModal
 *     phone="01012345678"
 *     onClose={() => ...}
 *   />
 */

import { useState, useEffect } from "react";
import {
  X, Package, CheckCircle, XCircle, Clock,
  DollarSign, TrendingUp, Calendar, Loader2, BarChart2,
  Phone
} from "lucide-react";
import { bridge } from "../bridge";

interface CustomerHistoryModalProps {
  customerId?: number;
  phone?: string;
  customerName?: string;
  onClose: () => void;
}

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  completed:          { label: "مكتمل",            color: "text-green-400" },
  cancelled:          { label: "ملغي",              color: "text-red-400" },
  new:                { label: "جديد",              color: "text-blue-400" },
  preparing:          { label: "قيد التحضير",       color: "text-amber-400" },
  ready:              { label: "جاهز",              color: "text-teal-400" },
  out_for_delivery:   { label: "خارج للتوصيل",      color: "text-cyan-400" },
  delivered:          { label: "تم التسليم",        color: "text-green-300" },
};

const fmtEGP = (n: number) => `${n.toFixed(2)} ج.م`;
const fmtDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString("ar-EG", {
        day: "numeric", month: "short", year: "numeric",
      })
    : "—";
const fmtRelative = (iso: string | null) => {
  if (!iso) return "—";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days === 0) return "اليوم";
  if (days === 1) return "أمس";
  return `منذ ${days} يوم`;
};

export function CustomerHistoryModal({
  customerId,
  phone,
  customerName,
  onClose,
}: CustomerHistoryModalProps) {
  const [customer, setCustomer] = useState<any | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [stats, setStats] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"orders" | "stats">("orders");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        let cid = customerId;

        // Lookup by phone if only phone provided
        if (!cid && phone) {
          const cust = await bridge.call("find_customer", { phone });
          if (!cust) throw new Error("لم يتم العثور على العميل");
          setCustomer(cust);
          cid = cust.id;
        } else if (cid) {
          const cust = await bridge.call("get_customer_by_id", { customer_id: cid });
          if (!cust) throw new Error("لم يتم العثور على العميل");
          setCustomer(cust);
        }

        if (!cid) throw new Error("لا يمكن تحديد هوية العميل");

        // Load history and stats in parallel
        const [hist, st] = await Promise.all([
          bridge.call("get_customer_history", { customer_id: cid, limit: 50 }),
          bridge.call("get_customer_statistics", { customer_id: cid }),
        ]);
        setHistory(hist || []);
        setStats(st);
      } catch (e: any) {
        setError(e.message || "فشل تحميل بيانات العميل");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [customerId, phone]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
      dir="rtl"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative z-10 w-full sm:max-w-2xl bg-brand-surface border border-brand-border rounded-t-3xl sm:rounded-2xl shadow-2xl flex flex-col max-h-[90vh] sm:max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-brand-border">
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 rounded-xl bg-brand-gold/10 border border-brand-gold/20 flex items-center justify-center text-lg font-black text-brand-gold">
              {loading ? "…" : (customer?.name || customerName || "?").charAt(0)}
            </div>
            <div>
              <h2 className="text-white font-bold text-base">
                {loading ? "جاري التحميل..." : customer?.name || customerName || "عميل"}
              </h2>
              {customer?.phone && (
                <p className="text-xs text-gray-400 flex items-center gap-1 font-mono">
                  <Phone size={10} />
                  {customer.phone}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-brand-card rounded-xl transition-all text-gray-400 hover:text-white"
          >
            <X size={18} />
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-brand-border">
          <TabBtn active={activeTab === "orders"} onClick={() => setActiveTab("orders")} icon={Package} label="تاريخ الطلبات" />
          <TabBtn active={activeTab === "stats"} onClick={() => setActiveTab("stats")} icon={BarChart2} label="الإحصائيات" />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-40">
              <Loader2 className="animate-spin text-brand-gold" size={28} />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-40 gap-3 text-center p-8">
              <XCircle className="text-red-400" size={32} />
              <p className="text-red-300">{error}</p>
            </div>
          ) : activeTab === "orders" ? (
            <OrdersTab history={history} />
          ) : (
            <StatsTab stats={stats} customer={customer} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Orders Tab ────────────────────────────────────────────────────────────────
function OrdersTab({ history }: { history: any[] }) {
  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 gap-3 text-center p-8">
        <Package className="text-gray-600" size={32} />
        <p className="text-gray-400">لا توجد طلبات سابقة</p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-brand-border/30">
      {history.map((order) => {
        const statusCfg = STATUS_CONFIG[order.status] || { label: order.status, color: "text-gray-400" };
        const isCancelled = order.status === "cancelled";

        return (
          <div key={order.id} className={`px-5 py-3 ${isCancelled ? "opacity-60" : ""}`}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {isCancelled ? (
                  <XCircle size={14} className="text-red-400 flex-shrink-0" />
                ) : order.status === "completed" ? (
                  <CheckCircle size={14} className="text-green-400 flex-shrink-0" />
                ) : (
                  <Clock size={14} className="text-amber-400 flex-shrink-0" />
                )}
                <div>
                  <span className="text-white font-semibold text-sm">
                    طلب #{order.invoice_no}
                  </span>
                  {order.customer_address && (
                    <p className="text-xs text-gray-500 truncate max-w-[180px]">{order.customer_address}</p>
                  )}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className={`text-sm font-bold ${isCancelled ? "text-gray-500 line-through" : "text-white"}`}>
                  {isCancelled ? "—" : `${order.total?.toFixed(2)} ج.م`}
                </p>
                <p className={`text-xs ${statusCfg.color}`}>{statusCfg.label}</p>
              </div>
            </div>
            <div className="flex items-center justify-between mt-1.5">
              <span className="text-xs text-gray-500">{fmtDate(order.created_at)}</span>
              {order.cancel_reason && (
                <span className="text-xs text-red-400/70 italic truncate max-w-[180px]">
                  السبب: {order.cancel_reason}
                </span>
              )}
              {!order.cancel_reason && order.payment_method && (
                <span className="text-xs text-gray-500">
                  {order.payment_method === "cash" ? "💵 نقدي" : "💳 أونلاين"}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Stats Tab ─────────────────────────────────────────────────────────────────
function StatsTab({ stats, customer }: { stats: any; customer: any }) {
  if (!stats) return null;

  return (
    <div className="p-5 space-y-4">
      {/* Quick summary */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard
          icon={Package}
          label="إجمالي الطلبات"
          value={String(stats.total_orders)}
          color="blue"
        />
        <StatCard
          icon={CheckCircle}
          label="طلبات مكتملة"
          value={String(stats.completed_orders)}
          color="green"
        />
        <StatCard
          icon={DollarSign}
          label="إجمالي الإنفاق"
          value={fmtEGP(stats.total_spent)}
          color="amber"
        />
        <StatCard
          icon={TrendingUp}
          label="متوسط الطلب"
          value={fmtEGP(stats.avg_order_value)}
          color="purple"
        />
      </div>

      {/* Additional details */}
      <div className="bg-brand-card border border-brand-border rounded-xl p-4 space-y-2">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">تفاصيل إضافية</h3>
        <InfoRow icon={TrendingUp} label="أكبر طلب" value={fmtEGP(stats.largest_order)} />
        <InfoRow icon={XCircle} label="طلبات ملغاة" value={String(stats.cancelled_orders)} />
        <InfoRow icon={Clock} label="طلبات نشطة" value={String(stats.active_orders)} />
        <InfoRow icon={Calendar} label="أول طلب" value={fmtDate(stats.first_order_at)} />
        <InfoRow icon={Calendar} label="آخر طلب" value={fmtRelative(stats.last_order_at)} />
      </div>

      {/* Customer info */}
      {customer?.notes && (
        <div className="bg-amber-900/10 border border-amber-700/20 rounded-xl p-4">
          <p className="text-xs text-amber-400 font-semibold mb-1">ملاحظات</p>
          <p className="text-sm text-amber-200">{customer.notes}</p>
        </div>
      )}
    </div>
  );
}

// ── Small sub-components ──────────────────────────────────────────────────────
function TabBtn({ active, onClick, icon: Icon, label }: any) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-semibold transition-all border-b-2 ${
        active
          ? "text-brand-gold border-brand-gold"
          : "text-gray-400 border-transparent hover:text-white hover:border-brand-border"
      }`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

function StatCard({ icon: Icon, label, value, color }: any) {
  const colorMap: Record<string, string> = {
    blue:   "bg-blue-500/10 border-blue-500/20 text-blue-400",
    green:  "bg-green-500/10 border-green-500/20 text-green-400",
    amber:  "bg-amber-500/10 border-amber-500/20 text-amber-400",
    purple: "bg-purple-500/10 border-purple-500/20 text-purple-400",
  };
  return (
    <div className="bg-brand-card border border-brand-border rounded-xl p-3">
      <div className={`h-8 w-8 rounded-lg border flex items-center justify-center mb-2 ${colorMap[color]}`}>
        <Icon size={14} />
      </div>
      <p className="text-gray-400 text-xs mb-0.5">{label}</p>
      <p className="text-white font-bold text-sm">{value}</p>
    </div>
  );
}

function InfoRow({ icon: Icon, label, value }: any) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-gray-400 text-xs flex items-center gap-1.5">
        <Icon size={11} />
        {label}
      </span>
      <span className="text-white text-xs font-semibold">{value}</span>
    </div>
  );
}
