import React, { useEffect, useState } from "react";
import { History } from "lucide-react";
import { bridge } from "../bridge";

interface Props {
  drivers: any[];
}

const todayCairo = () =>
  new Date().toLocaleDateString("sv-SE", { timeZone: "Africa/Cairo" }); // YYYY-MM-DD

const egp = (n: any) => `${Number(n || 0).toFixed(2)} ج.م`;

export const SettlementHistory: React.FC<Props> = ({ drivers }) => {
  const [date, setDate] = useState(todayCairo());
  const [driverId, setDriverId] = useState<string>("");
  const [rows, setRows] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!date) { setRows([]); return; }
    setLoading(true);
    setError("");
    bridge
      .call("get_driver_settlements", {
        date,
        ...(driverId ? { driver_id: parseInt(driverId) } : {}),
      })
      .then((res: any) => { if (!cancelled) setRows(res || []); })
      .catch((e: any) => { if (!cancelled) { setRows([]); setError(e?.message || "تعذر تحميل السجل"); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [date, driverId]);

  return (
    <div className="mt-8 rounded-2xl border border-brand-border bg-brand-card/40 p-5 space-y-4" data-testid="settlement-history">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-white font-bold flex items-center gap-2">
          <History size={16} className="text-brand-red" />
          سجل التسويات السابقة
        </h3>
        <div className="flex items-center gap-2">
          <select
            value={driverId}
            onChange={(e) => setDriverId(e.target.value)}
            aria-label="السائق"
            className="bg-brand-surface border border-brand-border rounded-lg px-3 py-1.5 text-white text-sm"
          >
            <option value="">كل السائقين</option>
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>{d.display_name || d.username}</option>
            ))}
          </select>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            aria-label="التاريخ"
            className="bg-brand-surface border border-brand-border rounded-lg px-3 py-1.5 text-white text-sm font-mono"
          />
        </div>
      </div>
      {error && <p className="text-red-400 text-sm" role="alert">{error}</p>}
      {loading ? (
        <p className="text-gray-400 text-sm">جاري التحميل...</p>
      ) : rows.length === 0 ? (
        <p className="text-gray-500 text-sm">لا توجد تسويات في هذا اليوم</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-right text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-brand-border/40">
                <th className="pb-2">السائق</th>
                <th className="pb-2">الرحلات</th>
                <th className="pb-2">الطلبات</th>
                <th className="pb-2">نقدي</th>
                <th className="pb-2">أونلاين</th>
                <th className="pb-2">رسوم التوصيل</th>
                <th className="pb-2">سوّاها</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-brand-border/20 text-gray-200">
                  <td className="py-2 font-bold text-white">{r.driver_name}</td>
                  <td className="py-2 font-mono">{r.trip_count}</td>
                  <td className="py-2 font-mono">{r.order_count}</td>
                  <td className="py-2 font-mono">{egp(r.cash_collected)}</td>
                  <td className="py-2 font-mono">{egp(r.online_paid)}</td>
                  <td className="py-2 font-mono">{egp(r.total_delivery_fees)}</td>
                  <td className="py-2">{r.settled_by_name || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
