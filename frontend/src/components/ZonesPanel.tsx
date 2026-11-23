import React, { useEffect, useState } from "react";
import { MapPin, Plus, Pencil, Check, X } from "lucide-react";
import { bridge } from "../bridge";

export const ZonesPanel: React.FC = () => {
  const [zones, setZones] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [name, setName] = useState("");
  const [fee, setFee] = useState("");

  const load = async () => {
    try {
      setZones((await bridge.call("get_all_zones")) || []);
    } catch (e: any) {
      setError(e?.message || "تعذر تحميل المناطق");
    }
  };
  useEffect(() => { load(); }, []);

  const startNew = () => { setEditingId("new"); setName(""); setFee(""); setError(""); };
  const startEdit = (z: any) => { setEditingId(z.id); setName(z.name); setFee(String(z.delivery_fee)); setError(""); };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const feeNum = parseFloat(fee);
    if (!name.trim()) { setError("اسم المنطقة مطلوب"); return; }
    if (isNaN(feeNum) || feeNum < 0) { setError("رسوم التوصيل غير صحيحة"); return; }
    try {
      if (editingId === "new") {
        await bridge.call("create_zone", { name: name.trim(), delivery_fee: feeNum });
      } else {
        await bridge.call("update_zone", { zone_id: editingId, name: name.trim(), delivery_fee: feeNum });
      }
      setEditingId(null);
      load();
    } catch (err: any) {
      setError(err?.message || "فشل الحفظ");
    }
  };

  const toggle = async (z: any) => {
    try {
      await bridge.call("update_zone", { zone_id: z.id, is_active: !z.is_active });
      load();
    } catch (err: any) {
      setError(err?.message || "فشل التحديث");
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6" data-testid="zones-panel">
      <div className="max-w-2xl space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <MapPin size={18} className="text-brand-red" /> مناطق التوصيل
          </h3>
          <button onClick={startNew} className="py-2 px-4 bg-brand-red text-brand-dark rounded-xl text-xs font-bold flex items-center gap-1.5">
            <Plus size={14} /> منطقة جديدة
          </button>
        </div>
        {error && <p className="text-red-400 text-sm" role="alert">{error}</p>}

        {editingId !== null && (
          <form onSubmit={save} className="bg-brand-card border border-brand-border/50 rounded-2xl p-4 flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[180px]">
              <label className="text-gray-400 text-xs block mb-1">اسم المنطقة</label>
              <input value={name} onChange={(e) => setName(e.target.value)} autoFocus
                className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-red" />
            </div>
            <div className="w-32">
              <label className="text-gray-400 text-xs block mb-1">رسوم التوصيل (ج.م)</label>
              <input type="number" min={0} step="0.5" value={fee} onChange={(e) => setFee(e.target.value)}
                className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white font-mono text-center focus:outline-none focus:border-brand-red" />
            </div>
            <button type="submit" className="p-2.5 bg-brand-red text-brand-dark rounded-lg" aria-label="حفظ المنطقة"><Check size={16} /></button>
            <button type="button" onClick={() => setEditingId(null)} className="p-2.5 bg-brand-surface text-gray-300 rounded-lg" aria-label="إلغاء"><X size={16} /></button>
          </form>
        )}

        <div className="space-y-2">
          {zones.map((z) => (
            <div key={z.id} className={`flex items-center gap-3 p-3 bg-brand-card/60 border border-brand-border/40 rounded-xl ${z.is_active ? "" : "opacity-50"}`}>
              <span className="flex-1 text-white font-bold">{z.name}</span>
              <span className="font-mono text-gray-300 text-sm">{Number(z.delivery_fee).toFixed(2)} ج.م</span>
              <button onClick={() => startEdit(z)} className="p-2 text-gray-400 hover:text-brand-red" aria-label="تعديل المنطقة"><Pencil size={14} /></button>
              <button onClick={() => toggle(z)} className="py-1 px-3 text-xs rounded-lg border border-brand-border/50 text-gray-300 hover:border-brand-red">
                {z.is_active ? "إيقاف" : "تفعيل"}
              </button>
            </div>
          ))}
          {zones.length === 0 && <p className="text-gray-500 text-sm">لا توجد مناطق</p>}
        </div>
      </div>
    </div>
  );
};
