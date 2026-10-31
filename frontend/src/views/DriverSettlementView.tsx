/**
 * DriverSettlementView — End-of-day driver settlement management.
 *
 * Features:
 * - Select a driver → view their unsettled trips for today
 * - Full order breakdown per trip (cash vs online, fees)
 * - Preview settlement before confirming
 * - Manager confirms and atomic settlement is recorded
 * - Settlement history available per driver
 */

import { useState, useEffect, useCallback } from "react";
import {
  Wallet, ChevronRight, CheckCircle, AlertCircle, Clock,
  Package, RefreshCcw, Loader2, User, DollarSign,
  Banknote, CreditCard, TruckIcon, FileText
} from "lucide-react";
import { bridge } from "../bridge";

interface DriverSettlementViewProps {
  currentUser: any;
}

type ViewState = "select_driver" | "preview" | "success";

const fmtEGP = (n: number) => `${n.toFixed(2)} ج.م`;
const fmtTime = (iso: string | null) => iso
  ? new Date(iso).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" })
  : "—";
const fmtDate = (iso: string | null) => iso
  ? new Date(iso).toLocaleDateString("ar-EG", { day: "numeric", month: "long" })
  : "—";

export function DriverSettlementView({ currentUser: _currentUser }: DriverSettlementViewProps) {
  const [drivers, setDrivers] = useState<any[]>([]);
  const [selectedDriver, setSelectedDriver] = useState<any | null>(null);
  const [preview, setPreview] = useState<any | null>(null);
  const [viewState, setViewState] = useState<ViewState>("select_driver");
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successData, setSuccessData] = useState<any | null>(null);
  const [notes, setNotes] = useState("");
  const [expandedTrip, setExpandedTrip] = useState<number | null>(null);

  const loadDrivers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await bridge.call("get_available_drivers");
      setDrivers(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDrivers();
  }, [loadDrivers]);

  const handleSelectDriver = async (driver: any) => {
    setSelectedDriver(driver);
    setPreview(null);
    setError(null);
    setPreviewLoading(true);
    try {
      const data = await bridge.call("get_driver_settlement_preview", {
        driver_id: driver.id,
      });
      setPreview(data);
      setViewState("preview");
    } catch (e: any) {
      setError(e.message || "لا توجد رحلات مؤهلة للتسوية اليوم");
      setViewState("preview");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleConfirmSettlement = async () => {
    if (!selectedDriver || !preview) return;
    setLoading(true);
    setError(null);
    try {
      const result = await bridge.call("settle_driver", {
        driver_id: selectedDriver.id,
        notes: notes || undefined,
      });
      setSuccessData(result);
      setViewState("success");
    } catch (e: any) {
      setError(e.message || "فشل في تسجيل التسوية");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setSelectedDriver(null);
    setPreview(null);
    setError(null);
    setNotes("");
    setSuccessData(null);
    setViewState("select_driver");
    loadDrivers();
  };

  // ── Success State ─────────────────────────────────────────────────────────
  if (viewState === "success" && successData) {
    return (
      <div className="h-[calc(100vh-64px)] flex flex-col items-center justify-center p-8 gap-6">
        <div className="text-center space-y-3">
          <div className="h-20 w-20 rounded-full bg-green-500/10 border-2 border-green-500/30 flex items-center justify-center mx-auto">
            <CheckCircle className="text-green-400" size={40} />
          </div>
          <h2 className="text-2xl font-bold text-white">تمت التسوية بنجاح</h2>
          <p className="text-gray-400">تم تسجيل تسوية {successData.driver_name} ليوم {fmtDate(successData.settlement_date)}</p>
        </div>

        <div className="bg-brand-card border border-brand-border rounded-2xl p-6 w-full max-w-md space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Stat label="عدد الرحلات" value={successData.trip_count} unit="" icon={TruckIcon} color="blue" />
            <Stat label="عدد الطلبات" value={successData.order_count} unit="" icon={Package} color="purple" />
            <Stat label="نقدي" value={fmtEGP(successData.cash_collected)} unit="" icon={Banknote} color="emerald" />
            <Stat label="أونلاين" value={fmtEGP(successData.online_paid)} unit="" icon={CreditCard} color="cyan" />
          </div>
          <div className="border-t border-brand-border pt-4 flex justify-between items-center">
            <span className="text-gray-400">إجمالي رسوم التوصيل</span>
            <span className="text-brand-gold font-bold text-lg">{fmtEGP(successData.total_delivery_fees)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400">المبلغ المستحق تسليمه</span>
            <span className="text-white font-bold text-xl">{fmtEGP(successData.cash_collected)}</span>
          </div>
        </div>

        <button
          onClick={handleReset}
          className="px-8 py-3 bg-brand-gold text-brand-dark font-bold rounded-xl hover:bg-yellow-400 transition-all"
        >
          تسوية سائق آخر
        </button>
      </div>
    );
  }

  // ── Preview State ─────────────────────────────────────────────────────────
  if (viewState === "preview") {
    return (
      <div className="h-[calc(100vh-64px)] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-brand-border bg-brand-surface">
          <button
            onClick={() => setViewState("select_driver")}
            className="p-2 hover:bg-brand-card rounded-xl transition-all text-gray-400 hover:text-white"
          >
            <ChevronRight size={20} />
          </button>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-gold/10 border border-brand-gold/20 flex items-center justify-center">
              <User className="text-brand-gold" size={18} />
            </div>
            <div>
              <h2 className="text-white font-bold">{selectedDriver?.display_name}</h2>
              <p className="text-xs text-gray-400">
                تسوية يوم {new Date().toLocaleDateString("ar-EG", { weekday: "long", day: "numeric", month: "long" })}
              </p>
            </div>
          </div>
        </div>

        {previewLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="animate-spin text-brand-gold" size={32} />
          </div>
        ) : error ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center p-8">
            <div className="h-16 w-16 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <AlertCircle className="text-amber-400" size={28} />
            </div>
            <p className="text-amber-300 font-semibold text-lg">{error}</p>
            <p className="text-gray-500 text-sm">يجب أن تكون هناك رحلات عادت ولم تُسوَّ لهذا اليوم</p>
            <button onClick={() => setViewState("select_driver")} className="px-6 py-2 bg-brand-card border border-brand-border rounded-xl text-white hover:border-brand-gold/30 transition-all">
              اختر سائقًا آخر
            </button>
          </div>
        ) : preview && (
          <div className="flex-1 flex gap-0 overflow-hidden">
            {/* Trip list — left panel */}
            <div className="w-80 border-l border-brand-border overflow-y-auto flex-shrink-0 bg-brand-surface/50">
              <div className="p-4 space-y-3">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">الرحلات المؤهلة</h3>
                {preview.trips?.map((trip: any, idx: number) => (
                  <div
                    key={trip.trip_id}
                    onClick={() => setExpandedTrip(expandedTrip === trip.trip_id ? null : trip.trip_id)}
                    className={`rounded-xl border p-3 cursor-pointer transition-all ${
                      expandedTrip === trip.trip_id
                        ? "border-brand-gold/40 bg-brand-gold/5"
                        : "border-brand-border hover:border-brand-border/80 bg-brand-card/40"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-bold text-white">رحلة {idx + 1}</span>
                      <span className="text-xs text-gray-400">{trip.order_count} طلبات</span>
                    </div>
                    <div className="flex gap-3 text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        <Clock size={10} /> {fmtTime(trip.dispatched_at)}
                      </span>
                      <span>←</span>
                      <span className="flex items-center gap-1 text-green-400">
                        <CheckCircle size={10} /> {fmtTime(trip.returned_at)}
                      </span>
                    </div>
                    {expandedTrip === trip.trip_id && (
                      <div className="mt-3 space-y-1 border-t border-brand-border/50 pt-2">
                        {trip.orders?.map((order: any) => (
                          <div key={order.order_id} className="flex justify-between text-xs">
                            <span className="text-gray-400 truncate max-w-[140px]">{order.customer_name}</span>
                            <div className="flex items-center gap-1">
                              <span className={order.payment_method === "cash" ? "text-green-400" : "text-cyan-400"}>
                                {order.payment_method === "cash" ? "نقدي" : "أونلاين"}
                              </span>
                              <span className="text-white font-medium">{fmtEGP(order.total)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Summary + confirmation — right panel */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Financial summary cards */}
              <div className="grid grid-cols-2 gap-4">
                <Stat label="عدد الرحلات" value={String(preview.trip_count)} unit="" icon={TruckIcon} color="blue" />
                <Stat label="عدد الطلبات" value={String(preview.order_count)} unit="" icon={Package} color="purple" />
                <Stat label="إجمالي الطلبات" value={fmtEGP(preview.total_order_value)} unit="" icon={DollarSign} color="amber" />
                <Stat label="رسوم التوصيل" value={fmtEGP(preview.total_delivery_fees)} unit="" icon={TruckIcon} color="teal" />
              </div>

              {/* Cash handover box */}
              <div className="rounded-2xl bg-gradient-to-br from-green-900/30 to-emerald-900/20 border border-green-500/20 p-5">
                <h3 className="text-green-300 font-semibold mb-4 flex items-center gap-2">
                  <Banknote size={18} />
                  مبالغ نقدية
                </h3>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-400 text-sm">مدفوع نقداً</span>
                    <span className="text-green-400 font-bold text-lg">{fmtEGP(preview.cash_collected)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-400 text-sm">مدفوع أونلاين</span>
                    <span className="text-cyan-400 font-bold">{fmtEGP(preview.online_paid)}</span>
                  </div>
                </div>
                <div className="mt-4 pt-3 border-t border-green-500/20 flex justify-between items-center">
                  <span className="text-white font-bold">المبلغ المطلوب تسليمه</span>
                  <span className="text-2xl font-black text-white">{fmtEGP(preview.cash_collected)}</span>
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm font-semibold text-gray-300 mb-2 flex items-center gap-2">
                  <FileText size={14} />
                  ملاحظات (اختياري)
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="أي ملاحظات إضافية للتسوية..."
                  className="w-full bg-brand-card border border-brand-border rounded-xl p-3 text-white text-sm placeholder-gray-500 resize-none focus:outline-none focus:border-brand-gold/50 transition-all"
                  rows={2}
                  dir="rtl"
                />
              </div>

              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-900/20 border border-red-700/30 rounded-xl text-red-300 text-sm">
                  <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {/* Confirm button */}
              <button
                onClick={handleConfirmSettlement}
                disabled={loading}
                className="w-full py-4 bg-gradient-to-l from-brand-gold to-yellow-500 text-brand-dark font-black text-lg rounded-2xl hover:from-yellow-400 hover:to-brand-gold active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-3"
              >
                {loading ? (
                  <Loader2 size={20} className="animate-spin" />
                ) : (
                  <CheckCircle size={20} />
                )}
                تأكيد التسوية وتسجيلها
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── Driver Selection State ─────────────────────────────────────────────────
  return (
    <div className="h-[calc(100vh-64px)] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-brand-border bg-brand-surface">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-brand-gold/10 border border-brand-gold/20 flex items-center justify-center">
            <Wallet className="text-brand-gold" size={18} />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">تسوية السائقين</h1>
            <p className="text-xs text-gray-400">
              {new Date().toLocaleDateString("ar-EG", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
            </p>
          </div>
        </div>
        <button
          onClick={loadDrivers}
          className="p-2 hover:bg-brand-card rounded-xl transition-all text-gray-400 hover:text-white"
          title="تحديث"
        >
          <RefreshCcw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Driver grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="animate-spin text-brand-gold" size={32} />
          </div>
        ) : drivers.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-center">
            <User className="text-gray-600" size={40} />
            <p className="text-gray-400">لا يوجد سائقون مسجلون</p>
          </div>
        ) : (
          <>
            <h2 className="text-sm font-semibold text-gray-400 mb-4 uppercase tracking-wider">
              اختر سائقًا لعرض تفاصيل التسوية
            </h2>
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {drivers.map((driver) => (
                <button
                  key={driver.id}
                  onClick={() => handleSelectDriver(driver)}
                  disabled={!driver.is_checked_in}
                  className={`relative flex flex-col items-center gap-3 p-5 rounded-2xl border text-center transition-all group ${
                    driver.is_checked_in
                      ? "border-brand-border hover:border-brand-gold/40 bg-brand-card hover:bg-brand-card/80 cursor-pointer active:scale-[0.98]"
                      : "border-brand-border/40 bg-brand-card/30 opacity-50 cursor-not-allowed"
                  }`}
                >
                  <div className={`h-14 w-14 rounded-2xl flex items-center justify-center text-xl font-black ${
                    driver.is_checked_in
                      ? "bg-brand-gold/10 text-brand-gold group-hover:bg-brand-gold/20"
                      : "bg-gray-800 text-gray-600"
                  }`}>
                    {(driver.display_name || driver.username).charAt(0)}
                  </div>
                  <div>
                    <p className="font-bold text-white text-sm">{driver.display_name || driver.username}</p>
                    <p className={`text-xs mt-0.5 ${driver.is_checked_in ? "text-green-400" : "text-gray-500"}`}>
                      {driver.is_checked_in ? "حاضر اليوم" : "غير مسجل"}
                    </p>
                  </div>
                  {driver.is_checked_in && (
                    <div className="absolute top-3 left-3 h-2 w-2 rounded-full bg-green-400 animate-pulse" />
                  )}
                  <ChevronRight size={16} className="text-gray-500 group-hover:text-brand-gold transition-colors" />
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Shared Stat Card ──────────────────────────────────────────────────────────
function Stat({ label, value, unit, icon: Icon, color }: { label: string; value: string; unit: string; icon: any; color: string }) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-500/10 border-blue-500/20 text-blue-400",
    purple: "bg-purple-500/10 border-purple-500/20 text-purple-400",
    amber: "bg-amber-500/10 border-amber-500/20 text-amber-400",
    emerald: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400",
    cyan: "bg-cyan-500/10 border-cyan-500/20 text-cyan-400",
    teal: "bg-teal-500/10 border-teal-500/20 text-teal-400",
  };
  return (
    <div className="bg-brand-card border border-brand-border rounded-xl p-4">
      <div className={`h-8 w-8 rounded-lg border flex items-center justify-center mb-2 ${colorMap[color] || colorMap.blue}`}>
        <Icon size={14} />
      </div>
      <p className="text-gray-400 text-xs mb-0.5">{label}</p>
      <p className="text-white font-bold text-sm">{value}{unit}</p>
    </div>
  );
}
