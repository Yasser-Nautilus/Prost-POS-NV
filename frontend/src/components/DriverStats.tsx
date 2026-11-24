import React, { useEffect, useState } from "react";
import { Bike } from "lucide-react";
import { bridge } from "../bridge";

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const DriverStats: React.FC = () => {
  const [period, setPeriod] = useState<"day" | "month">("day");
  const [date, setDate] = useState(todayStr());
  const [rows, setRows] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!date) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    bridge.call("get_driver_stats", { period, date })
      .then((res: any) => { if (!cancelled) setRows(res || []); })
      .catch((e: any) => { if (!cancelled) { setRows([]); setError(e?.message || "تعذر تحميل إحصائيات السائقين"); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [period, date]);

  return (
    <div className="bg-brand-card p-6 rounded-3xl border border-brand-border/50 space-y-4" data-testid="driver-stats">
      <div className="flex flex-wrap justify-between items-center gap-3 border-b border-brand-border/60 pb-4">
        <h3 className="text-xl font-bold text-brand-red flex items-center gap-2">
          <Bike size={22} />
          إحصائيات السائقين
        </h3>
        <div className="flex items-center gap-2">
          <div className="flex rounded-xl overflow-hidden border border-brand-border/60">
            {(["day", "month"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-4 py-1.5 text-sm font-bold ${period === p ? "bg-brand-red text-brand-dark" : "bg-brand-surface text-gray-300"}`}
              >
                {p === "day" ? "يومي" : "شهري"}
              </button>
            ))}
          </div>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            aria-label="التاريخ"
            className="bg-brand-surface border border-brand-border/60 rounded-lg px-3 py-1.5 text-white text-sm font-mono"
          />
        </div>
      </div>
      {error && <p className="text-red-400 text-sm" role="alert">{error}</p>}
      {loading && <p className="text-gray-400 text-sm">جاري التحميل...</p>}
      {!loading && !error && (
        rows.length === 0 ? (
          <p className="text-xs text-gray-500">لا توجد رحلات في هذه الفترة</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-xs text-right border-b border-brand-border/40">
                <th className="py-2 font-semibold">السائق</th>
                <th className="py-2 font-semibold">الرحلات</th>
                <th className="py-2 font-semibold">التوصيلات</th>
                <th className="py-2 font-semibold">متوسط زمن الرحلة</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.driver_id} className="border-b border-brand-border/20">
                  <td className="py-2 text-white font-medium">{r.driver_name}</td>
                  <td className="py-2 font-mono text-gray-300">{r.trip_count}</td>
                  <td className="py-2 font-mono text-white">{r.delivery_count}</td>
                  <td className="py-2 font-mono text-gray-300">
                    {r.avg_trip_minutes == null ? "-" : `${Math.round(r.avg_trip_minutes)} دقيقة`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
};
