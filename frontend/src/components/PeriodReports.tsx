import React, { useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import { bridge } from "../bridge";

const MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
const EXPENSE_LABELS: Record<string, string> = {
  supplies: "مستلزمات",
  delivery_fees: "رسوم توصيل",
  other: "أخرى",
};

const money = (v: any) => `${Number(v || 0).toFixed(2)} ج.م`;

export const PeriodReports: React.FC = () => {
  const now = new Date();
  const [mode, setMode] = useState<"monthly" | "yearly">("monthly");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const call = mode === "monthly"
      ? bridge.call("get_report_monthly", { year, month })
      : bridge.call("get_report_yearly", { year });
    call
      .then((res: any) => { if (!cancelled) setData(res); })
      .catch((e: any) => { if (!cancelled) { setData(null); setError(e?.message || "تعذر تحميل التقرير"); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [mode, year, month]);

  const summary = data?.summary;
  const rows: any[] = mode === "monthly" ? (summary?.daily || []) : (summary?.months || []);
  const expenses = data?.expenses?.categories || {};
  const net = (summary?.total_sales || 0) - (summary?.total_expenses || 0);

  return (
    <div className="bg-brand-card p-6 rounded-3xl border border-brand-border/50 space-y-5" data-testid="period-reports">
      <div className="flex flex-wrap justify-between items-center gap-3 border-b border-brand-border/60 pb-4">
        <h3 className="text-xl font-bold text-brand-red flex items-center gap-2">
          <CalendarDays size={22} />
          التقارير الشهرية والسنوية
        </h3>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl overflow-hidden border border-brand-border/60">
            {(["monthly", "yearly"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-4 py-1.5 text-sm font-bold ${mode === m ? "bg-brand-red text-brand-dark" : "bg-brand-surface text-gray-300"}`}
              >
                {m === "monthly" ? "شهري" : "سنوي"}
              </button>
            ))}
          </div>
          {mode === "monthly" && (
            <select
              value={month}
              onChange={(e) => setMonth(parseInt(e.target.value))}
              aria-label="الشهر"
              className="bg-brand-surface border border-brand-border/60 rounded-lg px-3 py-1.5 text-white text-sm"
            >
              {MONTHS.map((n, i) => <option key={n} value={i + 1}>{n}</option>)}
            </select>
          )}
          <input
            type="number"
            value={year}
            min={2000}
            max={2100}
            onChange={(e) => { const v = parseInt(e.target.value); if (v) setYear(v); }}
            aria-label="السنة"
            className="w-24 bg-brand-surface border border-brand-border/60 rounded-lg px-3 py-1.5 text-white text-sm font-mono text-center"
          />
        </div>
      </div>

      {error && <p className="text-red-400 text-sm" role="alert">{error}</p>}
      {loading && <p className="text-gray-400 text-sm">جاري التحميل...</p>}

      {summary && !loading && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-brand-surface/60 rounded-xl p-4">
              <span className="text-gray-400 text-xs block">إجمالي المبيعات</span>
              <b className="text-2xl text-white font-mono">{money(summary.total_sales)}</b>
            </div>
            <div className="bg-brand-surface/60 rounded-xl p-4">
              <span className="text-gray-400 text-xs block">إجمالي المصروفات</span>
              <b className="text-2xl text-red-400 font-mono">{money(summary.total_expenses)}</b>
            </div>
            <div className="bg-brand-surface/60 rounded-xl p-4">
              <span className="text-gray-400 text-xs block">الصافي</span>
              <b className="text-2xl text-brand-teal font-mono">{money(net)}</b>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-1 max-h-72 overflow-y-auto">
              <h4 className="text-sm font-bold text-white mb-2">{mode === "monthly" ? "حسب اليوم" : "حسب الشهر"}</h4>
              {rows.filter((r) => r.sales || r.expenses).map((r) => (
                <div key={r.date || r.month} className="flex justify-between gap-3 text-sm py-1.5 border-b border-brand-border/20">
                  <span className="text-gray-300 font-mono">{mode === "monthly" ? r.date : MONTHS[r.month - 1]}</span>
                  <span className="font-mono text-white">{money(r.sales)} <span className="text-red-400">/ {money(r.expenses)}</span></span>
                </div>
              ))}
              {!rows.some((r) => r.sales || r.expenses) && <p className="text-xs text-gray-500">لا توجد حركة في هذه الفترة</p>}
            </div>
            <div className="space-y-4">
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-white">الأصناف الأكثر مبيعًا</h4>
                {(data.bestsellers || []).map((b: any) => (
                  <div key={b.product_name} className="flex justify-between gap-3 text-sm py-1 border-b border-brand-border/20">
                    <span className="text-gray-300">{b.product_name} ({b.quantity})</span>
                    <span className="font-mono text-white">{money(b.revenue)}</span>
                  </div>
                ))}
                {!data.bestsellers?.length && <p className="text-xs text-gray-500">لا توجد مبيعات</p>}
              </div>
              {mode === "monthly" && (
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-white">المصروفات حسب النوع</h4>
                  {Object.keys(expenses).map((k) => (
                    <div key={k} className="flex justify-between text-sm py-1 border-b border-brand-border/20">
                      <span className="text-gray-300">{EXPENSE_LABELS[k] || k}</span>
                      <span className="font-mono text-white">{money(expenses[k])}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
