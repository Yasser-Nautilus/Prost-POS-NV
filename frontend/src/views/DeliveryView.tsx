import React, { useState, useEffect, useCallback } from "react";
import {
  Truck, Users, UserCheck, UserMinus, Plus, MapPin, CheckCircle,
  Loader2, RotateCcw, RefreshCw, Clock, Search, BarChart3, X
} from "lucide-react";
import { bridge } from "../bridge";

interface DeliveryViewProps {
  currentUser: any;
}

/* ── Helpers ────────────────────────────────────────────────────── */

function formatElapsed(dateStr: string | null): string {
  if (!dateStr) return "—";
  const secs = Math.max(0, Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return [h, m, s].map((v) => v.toString().padStart(2, "0")).join(":");
}

function formatTime(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" });
}

function formatDuration(checkIn: string | null, checkOut: string | null): string {
  if (!checkIn) return "—";
  const end = checkOut ? new Date(checkOut).getTime() : Date.now();
  const secs = Math.max(0, Math.floor((end - new Date(checkIn).getTime()) / 1000));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return `${h}س ${m}د`;
}

/** Live elapsed timer cell */
const LiveTimer: React.FC<{ since: string | null; urgentSecs?: number }> = ({
  since, urgentSecs = 1800,
}) => {
  const [display, setDisplay] = useState(() => formatElapsed(since));
  const [urgent, setUrgent] = useState(false);
  useEffect(() => {
    const tick = () => {
      setDisplay(formatElapsed(since));
      if (since) {
        const elapsed = Math.floor((Date.now() - new Date(since).getTime()) / 1000);
        setUrgent(elapsed >= urgentSecs);
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [since, urgentSecs]);
  return (
    <span className={`font-mono font-bold tabular-nums text-xs ${urgent ? "text-red-400 animate-pulse" : "text-brand-gold"}`}>
      {display}
    </span>
  );
};

/* ── Settlement Dialog ─────────────────────────────────────────── */

const TripSettlementDialog: React.FC<{
  tripId: number;
  onClose: () => void;
  onConfirm: (tripId: number) => void;
}> = ({ tripId, onClose, onConfirm }) => {
  const [details, setDetails] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    bridge.call("get_trip_details", { trip_id: tripId })
      .then((d: any) => setDetails(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [tripId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md">
      <div className="w-full max-w-2xl mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-brand-border/40 flex items-center justify-between bg-brand-card/60">
          <div>
            <h3 className="font-bold text-xl text-brand-gold">تسوية رحلة دليفري</h3>
            {details && (
              <p className="text-xs text-gray-400 mt-0.5">الطيار: {details.driver_name} — رحلة #{details.trip_id}</p>
            )}
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-brand-border/30">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-10 flex items-center justify-center gap-2 text-gray-400">
              <Loader2 className="animate-spin" size={20} /> جاري تحميل تفاصيل الرحلة...
            </div>
          ) : !details ? (
            <div className="p-10 text-center text-red-400">فشل تحميل تفاصيل الرحلة</div>
          ) : (
            <>
              {/* Orders table */}
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-brand-card/60 text-gray-400 text-xs">
                    <th className="py-2.5 px-3 text-right">#فاتورة</th>
                    <th className="py-2.5 px-3 text-right">العميل</th>
                    <th className="py-2.5 px-3 text-right">العنوان</th>
                    <th className="py-2.5 px-3 text-center font-mono">إجمالي الطلب</th>
                    <th className="py-2.5 px-3 text-center font-mono">خدمة التوصيل</th>
                  </tr>
                </thead>
                <tbody>
                  {(details.orders || []).map((o: any, i: number) => (
                    <tr key={o.order_id} className={`border-t border-brand-border/20 ${i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}>
                      <td className="py-2.5 px-3 text-gray-400 font-mono text-xs">#{o.invoice_no || o.order_id}</td>
                      <td className="py-2.5 px-3">
                        <span className="text-white font-bold text-sm block">{o.customer_name}</span>
                        {o.customer_phone && <span className="text-gray-500 font-mono text-[10px]">{o.customer_phone}</span>}
                      </td>
                      <td className="py-2.5 px-3 text-gray-400 text-xs">
                        {o.customer_zone && <div className="text-brand-gold text-[10px] font-bold">{o.customer_zone}</div>}
                        <div className="truncate max-w-[120px]">{o.customer_address}</div>
                      </td>
                      <td className="py-2.5 px-3 text-center text-white font-bold font-mono">
                        {(o.total || 0).toFixed(2)} ج.م
                      </td>
                      <td className="py-2.5 px-3 text-center text-brand-gold font-bold font-mono">
                        {(o.delivery_fee || 0).toFixed(2)} ج.م
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Totals */}
              <div className="p-4 border-t border-brand-border/40 bg-brand-card/40 grid grid-cols-2 gap-3">
                <div className="bg-brand-dark rounded-2xl p-4 text-center border border-brand-border/20">
                  <div className="text-xs text-gray-400 mb-1">إجمالي قيمة الطلبات</div>
                  <div className="text-2xl font-black text-white font-mono">
                    {(details.total_order_value || 0).toFixed(2)}
                    <span className="text-sm font-normal text-gray-400 ml-1">ج.م</span>
                  </div>
                </div>
                <div className="bg-brand-gold/10 rounded-2xl p-4 text-center border border-brand-gold/30">
                  <div className="text-xs text-brand-gold/70 mb-1">إجمالي خدمة التوصيل</div>
                  <div className="text-2xl font-black text-brand-gold font-mono">
                    {(details.total_delivery_fees || 0).toFixed(2)}
                    <span className="text-sm font-normal text-brand-gold/60 ml-1">ج.م</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer actions */}
        <div className="p-4 border-t border-brand-border/40 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 bg-brand-card border border-brand-border/40 text-gray-300 font-bold rounded-xl hover:bg-brand-border/20 transition-all"
          >
            إلغاء
          </button>
          <button
            onClick={() => onConfirm(tripId)}
            disabled={!details}
            className="flex-1 py-3 bg-green-900/40 text-green-300 border border-green-900/50 font-bold rounded-xl hover:bg-green-900/60 transition-all disabled:opacity-40 flex items-center justify-center gap-2"
          >
            <CheckCircle size={16} />
            تأكيد التسوية
          </button>
        </div>
      </div>
    </div>
  );
};

/* ── Main View ─────────────────────────────────────────────────── */

export const DeliveryView: React.FC<DeliveryViewProps> = () => {
  const [drivers, setDrivers] = useState<any[]>([]);
  const [trips, setTrips] = useState<any[]>([]);
  const [unassignedOrders, setUnassignedOrders] = useState<any[]>([]);
  const [attendanceRecords, setAttendanceRecords] = useState<any[]>([]);
  const [dailySummary, setDailySummary] = useState<any[]>([]);
  const [selectedOrders, setSelectedOrders] = useState<number[]>([]);
  const [selectedDriverId, setSelectedDriverId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [settlementTripId, setSettlementTripId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"dispatch" | "attendance" | "summary">("dispatch");
  const [attendanceSearch, setAttendanceSearch] = useState("");

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [drvs, trps, orders, att, summary] = await Promise.all([
        bridge.call("get_available_drivers"),
        bridge.call("get_active_trips"),
        bridge.call("get_active_orders"),
        bridge.call("get_driver_attendance_today"),
        bridge.call("get_daily_driver_summary"),
      ]);
      setDrivers(drvs || []);
      setTrips(trps || []);
      setUnassignedOrders((orders || []).filter((o: any) => o.order_type === "delivery" && o.status === "new"));
      setAttendanceRecords(att || []);
      setDailySummary(summary || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const handleToggleDriver = async (drvId: number, isCheckedIn: boolean) => {
    try {
      await bridge.call(isCheckedIn ? "check_out_driver" : "check_in_driver", { driver_id: drvId });
      fetchAll();
    } catch (err: any) {
      alert("فشل تغيير حالة الطيار: " + err.message);
    }
  };

  const handleCreateTrip = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDriverId || selectedOrders.length === 0) return;
    try {
      const tripResult = await bridge.call("create_trip", {
        driver_id: parseInt(selectedDriverId),
        order_ids: selectedOrders,
      });
      if (tripResult?.trip_id) {
        await bridge.call("dispatch_trip", { trip_id: tripResult.trip_id });
      }
      setSelectedOrders([]);
      setSelectedDriverId("");
      fetchAll();
    } catch (err: any) {
      alert("فشل إنشاء الرحلة: " + err.message);
    }
  };

  const handleReturnTrip = async (tripId: number) => {
    try {
      await bridge.call("return_trip", { trip_id: tripId });
      fetchAll();
    } catch (err: any) {
      alert("فشل تسجيل عودة الطيار: " + err.message);
    }
  };

  const handleSettleConfirm = async (tripId: number) => {
    try {
      await bridge.call("settle_trip", { trip_id: tripId });
      setSettlementTripId(null);
      fetchAll();
    } catch (err: any) {
      alert("فشل تسوية الرحلة: " + err.message);
    }
  };

  // Only checked-in and NOT currently on a trip
  const availableForDispatch = drivers.filter((d) => d.is_checked_in && d.status !== "out");

  // Filter attendance by search
  const filteredAttendance = attendanceRecords.filter((r) =>
    (r.display_name || "").toLowerCase().includes(attendanceSearch.toLowerCase())
  );

  const totalDayFees = dailySummary.reduce((sum: number, d: any) => sum + (d.fees_earned || 0), 0);

  if (loading && drivers.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)] bg-brand-dark">
        <Loader2 className="animate-spin text-brand-gold" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل بيانات الدليفري...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 h-[calc(100vh-64px)] flex flex-col bg-brand-dark overflow-hidden">

      {/* ── Active Trips Table ──────────────────────────────────────── */}
      <div className="p-4 border-b border-brand-border/40">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Truck size={17} className="text-brand-gold" />
            <h3 className="font-bold text-brand-gold text-sm">الرحلات النشطة في الطريق</h3>
            <span className="bg-brand-gold/20 text-brand-gold text-[10px] font-bold px-2 py-0.5 rounded-full">{trips.length}</span>
          </div>
          <button onClick={fetchAll} className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-brand-border/30 transition-all">
            <RefreshCw size={13} />
          </button>
        </div>

        {trips.length > 0 ? (
          <div className="rounded-2xl border border-brand-border/40 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-brand-card/80 text-gray-400 text-xs">
                  <th className="py-2 px-3 text-right">#</th>
                  <th className="py-2 px-3 text-right">الطيار</th>
                  <th className="py-2 px-3 text-center">طلبات</th>
                  <th className="py-2 px-3 text-center">الحالة</th>
                  <th className="py-2 px-3 text-center">المنقضي</th>
                  <th className="py-2 px-3 text-center">إجراء</th>
                </tr>
              </thead>
              <tbody>
                {trips.map((t, i) => {
                  const isReturned = !!t.returned_at;
                  return (
                    <tr key={t.id} className={`border-t border-brand-border/20 ${i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}>
                      <td className="py-2 px-3 text-gray-500 font-mono text-xs">#{t.id}</td>
                      <td className="py-2 px-3 text-white font-bold">{t.driver_name || "—"}</td>
                      <td className="py-2 px-3 text-center">
                        <span className="bg-brand-gold/10 text-brand-gold text-xs font-bold px-2 py-0.5 rounded-full">
                          {t.order_count || t.order_ids?.length || 0}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={`py-0.5 px-2 rounded-md font-bold text-[10px] ${isReturned ? "bg-green-900/30 text-green-400" : "bg-yellow-900/20 text-yellow-400"}`}>
                          {isReturned ? "عاد للمحل" : "في الطريق"}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <LiveTimer since={isReturned ? t.returned_at : t.dispatched_at} urgentSecs={isReturned ? 300 : 1800} />
                      </td>
                      <td className="py-2 px-3 text-center">
                        {!isReturned ? (
                          <button onClick={() => handleReturnTrip(t.id)}
                            className="py-1 px-3 bg-brand-gold/10 text-brand-gold border border-brand-gold/30 hover:bg-brand-gold/20 font-bold rounded-lg text-xs flex items-center gap-1 mx-auto transition-all">
                            <RotateCcw size={11} /> رجوع
                          </button>
                        ) : (
                          <button onClick={() => setSettlementTripId(t.id)}
                            className="py-1 px-3 bg-green-900/30 text-green-400 border border-green-900/50 hover:bg-green-900/50 font-bold rounded-lg text-xs flex items-center gap-1 mx-auto">
                            <CheckCircle size={11} /> تسوية
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-5 bg-brand-card/10 rounded-2xl border border-brand-border/20 text-center text-xs text-gray-500">
            لا توجد رحلات نشطة حالياً
          </div>
        )}
      </div>

      {/* ── Bottom Tabs ─────────────────────────────────────────────── */}
      <div className="flex border-b border-brand-border/40 bg-brand-card/30">
        {([
          { id: "dispatch", label: "إرسال رحلة", icon: Truck },
          { id: "attendance", label: "حضور الطيارين", icon: Users },
          { id: "summary", label: "ملخص اليوم", icon: BarChart3 },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex-1 py-2.5 text-xs font-bold flex items-center justify-center gap-1.5 border-b-2 transition-all ${
              activeTab === id
                ? "border-brand-gold text-brand-gold"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">

        {/* ── DISPATCH TAB ─────────────────────────────────────────── */}
        {activeTab === "dispatch" && (
          <div className="p-4 max-w-lg mx-auto">
            <div className="flex items-center gap-1.5 mb-3">
              <Truck size={14} className="text-brand-gold" />
              <h4 className="text-xs font-bold text-brand-gold">إرسال رحلة جديدة</h4>
            </div>
            <form onSubmit={handleCreateTrip} className="space-y-3">
              <div>
                <label className="text-gray-400 text-xs block mb-1">الطيار المتاح</label>
                <select
                  value={selectedDriverId}
                  onChange={(e) => setSelectedDriverId(e.target.value)}
                  className="w-full bg-brand-dark border border-brand-border/50 rounded-xl p-2.5 text-white text-sm focus:outline-none focus:border-brand-gold"
                >
                  <option value="">-- اختر طياراً --</option>
                  {availableForDispatch.map((drv) => (
                    <option key={drv.id} value={drv.id}>{drv.display_name} (متاح)</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-gray-400 text-xs block mb-1 flex justify-between">
                  <span>طلبات تنتظر إرسال</span>
                  <span className="text-brand-gold">{selectedOrders.length} محددة</span>
                </label>
                {unassignedOrders.length > 0 ? (
                  <div className="rounded-xl border border-brand-border/40 overflow-hidden max-h-48 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-brand-card/60 text-gray-500">
                          <th className="py-1.5 px-2 text-right">✓</th>
                          <th className="py-1.5 px-2 text-right">العميل</th>
                          <th className="py-1.5 px-2 text-right">المنطقة</th>
                          <th className="py-1.5 px-2 text-right font-mono">المبلغ</th>
                        </tr>
                      </thead>
                      <tbody>
                        {unassignedOrders.map((o, i) => {
                          const isSel = selectedOrders.includes(o.id);
                          return (
                            <tr
                              key={o.id}
                              onClick={() => setSelectedOrders((prev) =>
                                prev.includes(o.id) ? prev.filter((x) => x !== o.id) : [...prev, o.id]
                              )}
                              className={`cursor-pointer border-t border-brand-border/20 transition-colors ${isSel ? "bg-brand-gold/10" : i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}
                            >
                              <td className="py-2 px-2">
                                <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center ${isSel ? "bg-brand-gold border-brand-gold" : "border-brand-border/50"}`}>
                                  {isSel && <span className="text-[8px] text-brand-dark font-black">✓</span>}
                                </div>
                              </td>
                              <td className="py-2 px-2 text-white font-bold">{o.customer_name || "—"}</td>
                              <td className="py-2 px-2 text-gray-400 flex items-center gap-0.5">
                                <MapPin size={9} />{o.customer_zone || "—"}
                              </td>
                              <td className="py-2 px-2 text-brand-gold font-bold font-mono">{(o.total || 0).toFixed(0)} ج.م</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="py-5 text-center text-gray-500 text-xs rounded-xl border border-brand-border/20">لا توجد طلبات تنتظر إرسال</div>
                )}
              </div>

              <button
                type="submit"
                disabled={!selectedDriverId || selectedOrders.length === 0}
                className="w-full py-3 bg-brand-gold text-brand-dark disabled:opacity-40 hover:bg-opacity-90 font-black rounded-xl flex items-center justify-center gap-2 transition-all active:scale-95"
              >
                <Plus size={15} />
                إرسال الطيار ({selectedOrders.length} طلب)
              </button>
            </form>
          </div>
        )}

        {/* ── ATTENDANCE TAB ──────────────────────────────────────── */}
        {activeTab === "attendance" && (
          <div className="p-4 space-y-4">

            {/* ── Driver Check-in / Check-out Cards ── */}
            <div>
              <div className="flex items-center gap-1.5 mb-3">
                <Users size={14} className="text-brand-gold" />
                <h4 className="text-xs font-bold text-brand-gold">حضور وانصراف الطيارين</h4>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {drivers.map((drv) => {
                  const isOut = drv.status === "out";
                  const isCheckedIn = drv.is_checked_in;
                  return (
                    <div key={drv.id} className="p-3 bg-brand-card/50 rounded-xl flex flex-col gap-2 border border-brand-border/20">
                      <div>
                        <span className="text-white font-bold text-sm block">{drv.display_name}</span>
                        <span className={`text-[10px] font-bold ${isOut ? "text-yellow-400" : isCheckedIn ? "text-green-400" : "text-gray-500"}`}>
                          {isOut ? "🚗 في رحلة" : isCheckedIn ? "✓ حاضر ومتاح" : "✕ خارج الخدمة"}
                        </span>
                      </div>
                      <button
                        onClick={() => handleToggleDriver(drv.id, isCheckedIn)}
                        disabled={isOut}
                        className={`w-full py-1.5 px-3 rounded-lg font-bold text-xs transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-1 ${
                          isCheckedIn
                            ? "bg-red-950/40 text-red-400 border border-red-900/30 hover:bg-red-950/70"
                            : "bg-green-900/20 text-green-400 border border-green-900/30 hover:bg-green-900/40"
                        }`}
                      >
                        {isCheckedIn ? <><UserMinus size={12} /> انصراف</> : <><UserCheck size={12} /> حضور</>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── Attendance Records ── */}
            <div>
              <div className="flex items-center gap-1.5 mb-3">
                <Clock size={14} className="text-brand-gold" />
                <h4 className="text-xs font-bold text-brand-gold">سجل حضور اليوم</h4>
              </div>
              <div className="relative mb-2">
                <Search size={14} className="absolute right-3 top-2.5 text-gray-500" />
                <input
                  type="text"
                  value={attendanceSearch}
                  onChange={(e) => setAttendanceSearch(e.target.value)}
                  placeholder="ابحث عن طيار..."
                  className="w-full bg-brand-card border border-brand-border/50 rounded-xl py-2 pr-8 pl-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-gold text-right"
                />
              </div>

              <div className="rounded-2xl border border-brand-border/40 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-brand-card/80 text-gray-400 text-xs">
                      <th className="py-2.5 px-3 text-right">الطيار</th>
                      <th className="py-2.5 px-3 text-center">وقت الحضور</th>
                      <th className="py-2.5 px-3 text-center">وقت الانصراف</th>
                      <th className="py-2.5 px-3 text-center">مدة الحضور</th>
                      <th className="py-2.5 px-3 text-center">الحالة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAttendance.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-gray-500 text-xs">
                          <Clock size={24} className="mx-auto mb-1.5 text-brand-border/40" />
                          لا توجد سجلات حضور لليوم
                        </td>
                      </tr>
                    ) : (
                      filteredAttendance.map((rec: any, i: number) => {
                        const isCheckedOut = !!rec.check_out_at;
                        return (
                          <tr key={i} className={`border-t border-brand-border/20 ${i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}>
                            <td className="py-2.5 px-3 text-white font-bold">{rec.display_name}</td>
                            <td className="py-2.5 px-3 text-center text-green-400 font-bold text-xs">
                              {formatTime(rec.check_in_at)}
                            </td>
                            <td className="py-2.5 px-3 text-center text-red-400 text-xs">
                              {isCheckedOut ? formatTime(rec.check_out_at) : "—"}
                            </td>
                            <td className="py-2.5 px-3 text-center text-brand-gold font-mono text-xs font-bold">
                              {formatDuration(rec.check_in_at, rec.check_out_at)}
                            </td>
                            <td className="py-2.5 px-3 text-center">
                              <span className={`py-0.5 px-2 rounded-md font-bold text-[10px] ${isCheckedOut ? "bg-red-900/20 text-red-400" : "bg-green-900/20 text-green-400"}`}>
                                {isCheckedOut ? "انصرف" : "حاضر"}
                              </span>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Which driver arrived first */}
              {filteredAttendance.length > 0 && (
                <div className="mt-2 bg-brand-gold/5 border border-brand-gold/20 rounded-xl p-3 text-xs text-center text-brand-gold">
                  🏆 أول من حضر اليوم: <span className="font-black">{filteredAttendance[0]?.display_name}</span>
                  {" "}في {formatTime(filteredAttendance[0]?.check_in_at)}
                </div>
              )}
            </div>

          </div>
        )}

        {/* ── DAILY SUMMARY TAB ───────────────────────────────────── */}
        {activeTab === "summary" && (
          <div className="p-4 space-y-3">
            <div className="text-xs text-gray-400 mb-2">ملخص رسوم التوصيل لليوم</div>
            <div className="rounded-2xl border border-brand-border/40 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-brand-card/80 text-gray-400 text-xs">
                    <th className="py-2.5 px-3 text-right">الطيار</th>
                    <th className="py-2.5 px-3 text-center">رحلات</th>
                    <th className="py-2.5 px-3 text-center">طلبات</th>
                    <th className="py-2.5 px-3 text-center font-mono">إجمالي التوصيل</th>
                  </tr>
                </thead>
                <tbody>
                  {dailySummary.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-gray-500 text-xs">
                        <BarChart3 size={24} className="mx-auto mb-1.5 text-brand-border/40" />
                        لا توجد رحلات مكتملة اليوم بعد
                      </td>
                    </tr>
                  ) : (
                    dailySummary.map((drv: any, i: number) => (
                      <tr key={drv.driver_id} className={`border-t border-brand-border/20 ${i % 2 === 0 ? "bg-brand-dark" : "bg-brand-card/20"}`}>
                        <td className="py-2.5 px-3 text-white font-bold">{drv.driver_name}</td>
                        <td className="py-2.5 px-3 text-center text-gray-400">{drv.trip_count || 0}</td>
                        <td className="py-2.5 px-3 text-center text-gray-400">{drv.order_count || 0}</td>
                        <td className="py-2.5 px-3 text-center text-brand-gold font-black font-mono">
                          {(drv.fees_earned || 0).toFixed(2)} ج.م
                        </td>
                      </tr>
                    ))
                  )}
                  {dailySummary.length > 0 && (
                    <tr className="border-t-2 border-brand-gold/30 bg-brand-gold/5">
                      <td colSpan={3} className="py-2.5 px-3 text-brand-gold font-black text-right text-sm">إجمالي التوصيل لليوم</td>
                      <td className="py-2.5 px-3 text-center text-brand-gold font-black text-lg font-mono">
                        {totalDayFees.toFixed(2)} ج.م
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>

      {/* Settlement Dialog */}
      {settlementTripId !== null && (
        <TripSettlementDialog
          tripId={settlementTripId}
          onClose={() => setSettlementTripId(null)}
          onConfirm={handleSettleConfirm}
        />
      )}
    </div>
  );
};
