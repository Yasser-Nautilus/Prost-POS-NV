import React, { useState, useEffect } from "react";
import { BarChart3, TrendingUp, DollarSign, RefreshCw, Printer, Eye, X, Loader2 } from "lucide-react";
import { bridge } from "../bridge";

interface ReportsViewProps {
  currentUser: any;
}

const ORDER_TYPE_LABELS: Record<string, string> = {
  dine_in: "صالة",
  takeaway: "تيك أواي",
  delivery: "دليفري",
  pickup: "استلام محل",
};

const PAYMENT_METHOD_LABELS: Record<string, string> = {
  cash: "كاش",
  visa: "فيزا",
  online: "أونلاين",
};

export const ReportsView: React.FC<ReportsViewProps> = ({ currentUser: _currentUser }) => {
  const [salesSummary, setSalesSummary] = useState<any>(null);
  const [recentShifts, setRecentShifts] = useState<any[]>([]);
  const [dailySales, setDailySales] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // Shift detail — manager opens one shift and sees how it went
  const [detailShift, setDetailShift] = useState<any>(null);
  const [detailSummary, setDetailSummary] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchReportData = async () => {
    setLoading(true);
    try {
      // Fetch current active shift summary
      const sum = await bridge.call("get_shift_summary");
      setSalesSummary(sum);

      // Fetch real shift history from database
      const history = await bridge.call("get_shift_history");
      setRecentShifts(history || []);

      // Today's sales, including bestsellers
      const daily = await bridge.call("get_report_daily_sales");
      setDailySales(daily);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReportData();
  }, []);

  const handleOpenShiftDetail = async (shift: any) => {
    setDetailShift(shift);
    setDetailSummary(null);
    setDetailLoading(true);
    try {
      // Backend computes the summary for any shift by id
      const sum = await bridge.call("get_shift_summary", { shift_id: shift.id });
      setDetailSummary(sum);
    } catch (err: any) {
      alert("فشل تحميل تفاصيل الوردية: " + err.message);
      setDetailShift(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleReprintShiftReport = async (shiftId: number) => {
    try {
      await bridge.call("print_shift_summary", { shift_id: shiftId });
      alert("تم إرسال التقرير إلى الطابعة");
    } catch (err: any) {
      alert("فشل الطباعة: " + err.message);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)] bg-brand-dark">
        <RefreshCw className="animate-spin text-brand-gold" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل التقارير...</p>
      </div>
    );
  }

  return (
    <>
    <div className="flex-1 overflow-y-auto p-6 space-y-6 h-[calc(100vh-64px)] bg-brand-dark">

      {/* Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-brand-card p-5 rounded-2xl border border-brand-border/40 flex justify-between items-center">
          <div>
            <span className="text-gray-400 text-xs block">مبيعات الوردية الحالية</span>
            <span className="text-2xl font-black text-white mt-1 block">
              {(salesSummary?.total_sales || 0).toFixed(2)} ج.م
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-brand-gold/10 text-brand-gold flex items-center justify-center">
            <TrendingUp size={24} />
          </div>
        </div>

        <div className="bg-brand-card p-5 rounded-2xl border border-brand-border/40 flex justify-between items-center">
          <div>
            <span className="text-gray-400 text-xs block">نثريات ومصروفات</span>
            <span className="text-2xl font-black text-red-400 mt-1 block">
              {(salesSummary?.total_expenses || 0).toFixed(2)} ج.م
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-red-950/20 text-red-400 flex items-center justify-center">
            <DollarSign size={24} />
          </div>
        </div>

        <div className="bg-brand-card p-5 rounded-2xl border border-brand-border/40 flex justify-between items-center">
          <div>
            <span className="text-gray-400 text-xs block">النقدية المتوقعة بالدرج</span>
            <span className="text-2xl font-black text-brand-teal mt-1 block">
              {(salesSummary?.expected_cash || 0).toFixed(2)} ج.م
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-brand-teal/10 text-brand-teal flex items-center justify-center">
            <DollarSign size={24} />
          </div>
        </div>

        <div className="bg-brand-card p-5 rounded-2xl border border-brand-border/40 flex justify-between items-center">
          <div>
            <span className="text-gray-400 text-xs block">عدد فواتير الوردية</span>
            <span className="text-2xl font-black text-white mt-1 block">
              {salesSummary?.order_count != null
                ? `${salesSummary.order_count} فاتورة`
                : "—"}
            </span>
          </div>
          <div className="h-12 w-12 rounded-xl bg-brand-border/20 text-gray-300 flex items-center justify-center">
            <BarChart3 size={24} />
          </div>
        </div>
      </div>

      {/* Today's Sales Panel */}
      <div className="bg-brand-card p-6 rounded-3xl border border-brand-border/50 space-y-6">
        <div className="flex flex-wrap justify-between items-center gap-3 border-b border-brand-border/60 pb-4">
          <h3 className="text-xl font-bold text-brand-gold flex items-center gap-2">
            <TrendingUp size={22} />
            مبيعات اليوم
          </h3>
          <div className="flex flex-wrap gap-5 text-xs text-gray-400">
            <span>
              إجمالي المبيعات{" "}
              <b className="text-white font-mono">{(dailySales?.gross_revenue || 0).toFixed(2)} ج.م</b>
            </span>
            <span>
              إيراد المطعم{" "}
              <b className="text-brand-teal font-mono">{(dailySales?.restaurant_revenue || 0).toFixed(2)} ج.م</b>
            </span>
            <span>
              رسوم التوصيل{" "}
              <b className="text-white font-mono">{(dailySales?.total_delivery_fees || 0).toFixed(2)} ج.م</b>
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="space-y-2">
            <h4 className="text-sm font-bold text-white">حسب نوع الطلب</h4>
            {(dailySales?.sales_by_type?.breakdown || []).map((row: any) => (
              <div key={row.type} className="flex justify-between gap-3 text-sm py-1.5 border-b border-brand-border/20">
                <span className="text-gray-300">
                  {ORDER_TYPE_LABELS[row.type] || row.type} ({row.count})
                </span>
                <span className="font-bold text-white font-mono">{row.revenue.toFixed(2)} ج.م</span>
              </div>
            ))}
            {!dailySales?.sales_by_type?.breakdown?.length && (
              <p className="text-xs text-gray-500">لا توجد مبيعات مكتملة اليوم</p>
            )}
          </div>

          <div className="space-y-2">
            <h4 className="text-sm font-bold text-white">حسب طريقة الدفع</h4>
            {(dailySales?.payment_breakdown?.payments || []).map((row: any) => (
              <div key={row.method} className="flex justify-between gap-3 text-sm py-1.5 border-b border-brand-border/20">
                <span className="text-gray-300">
                  {PAYMENT_METHOD_LABELS[row.method] || row.method} ({row.count})
                </span>
                <span className="font-bold text-white font-mono">{row.revenue.toFixed(2)} ج.م</span>
              </div>
            ))}
            {!dailySales?.payment_breakdown?.payments?.length && (
              <p className="text-xs text-gray-500">لا توجد مدفوعات اليوم</p>
            )}
          </div>

          <div className="space-y-2">
            <h4 className="text-sm font-bold text-white">الأصناف الأكثر مبيعًا</h4>
            {(dailySales?.bestsellers || []).slice(0, 10).map((row: any) => (
              <div key={row.product_name} className="flex justify-between gap-3 text-sm py-1.5 border-b border-brand-border/20">
                <span className="text-gray-300">
                  {row.product_name} ({row.quantity})
                </span>
                <span className="font-bold text-white font-mono">{row.revenue.toFixed(2)} ج.م</span>
              </div>
            ))}
            {!dailySales?.bestsellers?.length && (
              <p className="text-xs text-gray-500">لم يتم بيع أي صنف اليوم</p>
            )}
          </div>
        </div>
      </div>

      {/* Main Reports Panel */}
      <div className="bg-brand-card p-6 rounded-3xl border border-brand-border/50 space-y-6">
        <div className="flex justify-between items-center border-b border-brand-border/60 pb-4">
          <h3 className="text-xl font-bold text-brand-gold flex items-center gap-2">
            <BarChart3 size={22} />
            سجل تقارير الورديات السابقة
          </h3>
          <button
            onClick={fetchReportData}
            className="p-2 bg-brand-surface border border-brand-border/60 hover:border-brand-gold text-white rounded-lg active:scale-95 transition-all"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        {/* Shift log table */}
        <div className="overflow-x-auto">
          <table className="w-full text-right text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-brand-border/40 pb-2">
                <th className="pb-3">رقم الوردية</th>
                <th className="pb-3">تاريخ الفتح</th>
                <th className="pb-3">فتحتها</th>
                <th className="pb-3 text-left">الحالة</th>
                <th className="pb-3 text-left">تاريخ الإغلاق</th>
                <th className="pb-3 text-center">الإجراءات</th>
              </tr>
            </thead>
            <tbody>
              {recentShifts.map((shift) => (
                <tr
                  key={shift.id}
                  onClick={() => handleOpenShiftDetail(shift)}
                  className="border-b border-brand-border/20 hover:bg-brand-surface/30 cursor-pointer"
                >
                  <td className="py-3 font-bold font-mono text-white">#{shift.id}</td>
                  <td className="py-3 text-gray-300">
                    {shift.opened_at ? new Date(shift.opened_at).toLocaleDateString("ar-EG") : "—"}
                  </td>
                  <td className="py-3 text-gray-300">{shift.opened_by_name || shift.opened_by || "—"}</td>
                  <td className="py-3 text-left font-bold text-white font-mono">
                    {shift.is_active ? <span className="text-brand-teal text-xs font-bold">نشطة</span> : "مغلقة"}
                  </td>
                  <td className="py-3 text-left font-bold text-gray-400 font-mono">
                    {shift.closed_at ? new Date(shift.closed_at).toLocaleDateString("ar-EG") : "—"}
                  </td>
                  <td className="py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleOpenShiftDetail(shift); }}
                        className="py-1.5 px-3 bg-brand-card hover:bg-brand-border/40 text-brand-teal border border-brand-teal/30 hover:border-brand-teal rounded-lg text-xs font-semibold flex items-center gap-1 active:translate-y-0.5 btn-hover-active"
                      >
                        <Eye size={12} />
                        عرض التفاصيل
                      </button>
                      {!shift.is_active && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleReprintShiftReport(shift.id); }}
                          className="py-1.5 px-3 bg-brand-card hover:bg-brand-border/40 text-brand-gold border border-brand-gold/30 hover:border-brand-gold rounded-lg text-xs font-semibold flex items-center gap-1 active:translate-y-0.5 btn-hover-active"
                        >
                          <Printer size={12} />
                          إعادة طباعة التقرير
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>

    {/* Shift detail modal — manager sees how one shift went */}
    {detailShift && (
      <div
        className="fixed inset-0 z-40 flex items-center justify-center bg-black/75 backdrop-blur-md"
        onClick={() => setDetailShift(null)}
      >
        <div
          className="w-full max-w-2xl mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex justify-between items-center px-6 py-4 border-b border-brand-border/60 bg-brand-card">
            <h3 className="font-bold text-lg text-brand-gold flex items-center gap-2">
              <BarChart3 size={20} />
              تفاصيل الوردية #{detailShift.id}
            </h3>
            <button
              onClick={() => setDetailShift(null)}
              className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
            >
              <X size={20} />
            </button>
          </div>

          <div className="p-6 space-y-5 max-h-[80vh] overflow-y-auto">
            {/* Who / when */}
            <div className="bg-brand-card p-4 rounded-2xl border border-brand-border/40 flex flex-wrap justify-between gap-3 text-xs">
              <div>
                <span className="text-gray-400 block">فُتحت</span>
                <span className="text-white font-medium">
                  {detailShift.opened_by_name || detailShift.opened_by || "—"}
                  {detailShift.opened_at ? " · " + new Date(detailShift.opened_at).toLocaleString("ar-EG") : ""}
                </span>
              </div>
              <div className="text-left">
                <span className="text-gray-400 block">الحالة</span>
                <span className={detailShift.is_active ? "text-brand-teal font-bold" : "text-gray-300"}>
                  {detailShift.is_active ? "نشطة" : "مغلقة"}
                  {detailShift.closed_at ? " · " + new Date(detailShift.closed_at).toLocaleString("ar-EG") : ""}
                </span>
              </div>
            </div>

            {detailLoading ? (
              <div className="py-12 flex justify-center">
                <Loader2 className="animate-spin text-brand-gold" size={28} />
              </div>
            ) : detailSummary ? (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-brand-card/40 p-4 rounded-xl border border-brand-border/30">
                    <span className="text-gray-400 text-xs block">إجمالي المبيعات (كل الطرق)</span>
                    <span className="text-2xl font-black text-white mt-1 block">
                      {(detailSummary.total_sales || 0).toFixed(2)} ج.م
                    </span>
                  </div>
                  <div className="bg-green-950/30 p-4 rounded-xl border border-green-800/30">
                    <span className="text-green-400 text-xs block font-semibold">مبيعات كاش فقط</span>
                    <span className="text-2xl font-black text-green-300 mt-1 block">
                      {(detailSummary.cash_sales || 0).toFixed(2)} ج.م
                    </span>
                  </div>
                  <div className="bg-brand-card/40 p-4 rounded-xl border border-brand-border/30">
                    <span className="text-gray-400 text-xs block">المصروفات الخارجة</span>
                    <span className="text-2xl font-black text-red-400 mt-1 block">
                      {(detailSummary.total_expenses || 0).toFixed(2)} - ج.م
                    </span>
                  </div>
                  <div className="bg-brand-card/40 p-4 rounded-xl border border-brand-border/30">
                    <span className="text-gray-400 text-xs block">غير مكيّش (معلّق)</span>
                    <span className="text-xl font-bold text-yellow-500 mt-1 block">
                      {((detailSummary.pending_dinein || 0) + (detailSummary.pending_kitchen || 0) + (detailSummary.pending_delivery || 0)).toFixed(2)} ج.م
                    </span>
                  </div>
                </div>

                <div className="bg-brand-card p-4 rounded-xl border border-brand-gold/30 bg-gradient-to-r from-brand-card to-brand-gold/5">
                  <span className="text-brand-gold text-xs block font-bold">المفروض بالدرج (كاش متوقع — بدون جرد فعلي)</span>
                  <span className="text-3xl font-black text-brand-gold mt-1 block">
                    {(detailSummary.expected_cash || 0).toFixed(2)} ج.م
                  </span>
                </div>

                {/* What was sold — by order type */}
                <div>
                  <h4 className="text-sm font-bold text-white mb-2">
                    اللي اتباع (حسب النوع) — {detailSummary.order_count || 0} فاتورة
                  </h4>
                  {Object.keys(detailSummary.order_breakdown || {}).length > 0 ? (
                    Object.entries(detailSummary.order_breakdown).map(([type, row]: any) => (
                      <div key={type} className="flex justify-between gap-3 text-sm py-1.5 border-b border-brand-border/20">
                        <span className="text-gray-300">
                          {ORDER_TYPE_LABELS[type] || type} ({row.count})
                        </span>
                        <span className="font-bold text-white font-mono">
                          {(row.revenue || 0).toFixed(2)} ج.م
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-gray-500">لا توجد مبيعات في هذه الوردية</p>
                  )}
                </div>
              </>
            ) : (
              <p className="text-gray-500 text-sm text-center py-8">لا توجد بيانات</p>
            )}
          </div>
        </div>
      </div>
    )}
    </>
  );
};
