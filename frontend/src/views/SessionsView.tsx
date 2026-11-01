import React, { useState, useEffect, useCallback } from "react";
import {
  Wallet, Plus, Power, RefreshCw, BarChart3, Lock,
  User, Clock, AlertTriangle, CheckCircle2, FileText, Loader2, X
} from "lucide-react";
import { bridge } from "../bridge";
import type { CashierSession, XReport, SessionStation } from "../bridge";
import { PinDialog } from "../components/PinDialog";

interface SessionsViewProps {
  currentUser: any;
}

// ── Stat Card ────────────────────────────────────────────────────────────────

const StatCard: React.FC<{
  label: string;
  value: string;
  icon: React.ReactNode;
  color?: string;
}> = ({ label, value, icon, color = "text-brand-gold" }) => (
  <div className="bg-brand-card p-5 rounded-2xl border border-brand-border/40 flex justify-between items-center">
    <div>
      <span className="text-gray-400 text-xs block">{label}</span>
      <span className={`text-2xl font-black mt-1 block ${color}`}>{value}</span>
    </div>
    <div className={`h-12 w-12 rounded-xl bg-brand-card flex items-center justify-center ${color}`} style={{ backgroundColor: 'rgba(207,168,96,0.1)' }}>
      {icon}
    </div>
  </div>
);

// ── Open Session Dialog ──────────────────────────────────────────────────────

const OpenSessionDialog: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  currentUser: any;
  onSuccess: () => void;
}> = ({ isOpen, onClose, currentUser, onSuccess }) => {
  const [station, setStation] = useState<SessionStation>("ALL");
  const [floatStr, setFloatStr] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!isOpen) return null;

  const stations: { value: SessionStation; label: string; desc: string }[] = [
    { value: "ALL", label: "الكل", desc: "كاونتر + توصيل" },
    { value: "COUNTER", label: "كاونتر", desc: "محلي + تيك أواي فقط" },
    { value: "DELIVERY", label: "توصيل", desc: "طلبات التوصيل فقط" },
  ];

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    try {
      await bridge.sessionOpen({
        user_id: currentUser.id,
        station,
        opening_float_egp: parseFloat(floatStr) || 0,
      });
      onSuccess();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-brand-surface border border-brand-border/60 rounded-3xl shadow-2xl w-full max-w-md p-6 space-y-5 animate-in fade-in zoom-in-95 duration-200" dir="rtl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Plus size={20} className="text-brand-gold" />
            فتح وردية صندوق
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Station selection */}
        <div className="space-y-2">
          <span className="text-xs text-gray-400 font-bold">نوع المحطة</span>
          <div className="grid grid-cols-3 gap-2">
            {stations.map((s) => (
              <button
                key={s.value}
                onClick={() => setStation(s.value)}
                className={`p-3 rounded-xl border text-center transition-all ${
                  station === s.value
                    ? "bg-brand-gold/10 border-brand-gold/40 text-brand-gold"
                    : "bg-brand-card border-brand-border/30 text-gray-400 hover:text-white hover:border-brand-border"
                }`}
              >
                <span className="block text-sm font-bold">{s.label}</span>
                <span className="block text-[10px] mt-0.5 opacity-70">{s.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Opening float */}
        <div className="space-y-2">
          <span className="text-xs text-gray-400 font-bold">عهدة أول الوردية (ج.م)</span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={floatStr}
              onChange={(e) => setFloatStr(e.target.value)}
              placeholder="0.00"
              className="flex-1 bg-brand-card border border-brand-border/40 rounded-xl px-4 py-3 text-white text-lg font-bold text-center outline-none focus:border-brand-gold/50 transition-colors"
              autoFocus
            />
          </div>
          <div className="flex gap-2 flex-wrap">
            {[200, 500, 1000, 2000].map((v) => (
              <button
                key={v}
                onClick={() => setFloatStr(String(v))}
                className="px-3 py-1.5 bg-brand-card border border-brand-border/30 rounded-lg text-xs text-gray-300 hover:text-brand-gold hover:border-brand-gold/30 transition-all"
              >
                {v} ج.م
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-red-950/30 border border-red-900/40 rounded-xl p-3 text-red-400 text-xs flex items-center gap-2">
            <AlertTriangle size={14} />
            {error}
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={loading}
          className="w-full py-3 bg-gradient-to-l from-brand-gold to-yellow-600 text-brand-dark font-bold rounded-xl hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
          فتح الوردية
        </button>
      </div>
    </div>
  );
};

// ── Close Session Dialog ─────────────────────────────────────────────────────

const CloseSessionDialog: React.FC<{
  isOpen: boolean;
  session: CashierSession | null;
  onClose: () => void;
  onSuccess: () => void;
}> = ({ isOpen, session, onClose, onSuccess }) => {
  const [countStr, setCountStr] = useState("");
  const [reason, setReason] = useState("");
  const [showPin, setShowPin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!isOpen || !session) return null;

  const expectedEgp = session.expected_cash_egp ?? session.opening_float_egp;
  const counted = parseFloat(countStr) || 0;
  const varianceEgp = counted - expectedEgp;
  const needsApproval = Math.abs(varianceEgp) > 20;

  const doClose = async (pin?: string) => {
    setLoading(true);
    setError("");
    try {
      await bridge.sessionClose({
        session_id: session.id,
        counted_cash_egp: counted,
        variance_reason: reason || undefined,
        manager_pin: pin,
      });
      onSuccess();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = () => {
    if (needsApproval && !reason.trim()) {
      setError("يجب كتابة سبب الفرق عندما يكون أكثر من 20 ج.م");
      return;
    }
    if (needsApproval) {
      setShowPin(true);
    } else {
      doClose();
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
        <div className="bg-brand-surface border border-brand-border/60 rounded-3xl shadow-2xl w-full max-w-md p-6 space-y-5" dir="rtl">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Lock size={20} className="text-red-400" />
              إغلاق وردية — {session.station}
            </h2>
            <button onClick={onClose} className="text-gray-500 hover:text-white">
              <X size={20} />
            </button>
          </div>

          {/* Expected */}
          <div className="bg-brand-card rounded-xl p-4 border border-brand-border/30">
            <div className="flex justify-between items-center">
              <span className="text-gray-400 text-xs">النقدية المتوقعة بالدرج</span>
              <span className="text-brand-teal font-black text-xl">{expectedEgp.toFixed(2)} ج.م</span>
            </div>
          </div>

          {/* Count input */}
          <div className="space-y-2">
            <span className="text-xs text-gray-400 font-bold">العدّ الفعلي للنقدية (ج.م)</span>
            <input
              type="number"
              value={countStr}
              onChange={(e) => setCountStr(e.target.value)}
              placeholder="أدخل المبلغ الفعلي"
              className="w-full bg-brand-card border border-brand-border/40 rounded-xl px-4 py-3 text-white text-lg font-bold text-center outline-none focus:border-brand-gold/50"
              autoFocus
            />
          </div>

          {/* Variance indicator */}
          {countStr && (
            <div className={`rounded-xl p-3 border flex items-center gap-2 text-sm font-bold ${
              Math.abs(varianceEgp) < 0.01
                ? "bg-brand-teal/10 border-brand-teal/30 text-brand-teal"
                : Math.abs(varianceEgp) <= 20
                ? "bg-yellow-950/20 border-yellow-900/30 text-yellow-400"
                : "bg-red-950/30 border-red-900/40 text-red-400"
            }`}>
              {Math.abs(varianceEgp) < 0.01 ? (
                <><CheckCircle2 size={16} /> لا يوجد فرق</>
              ) : (
                <><AlertTriangle size={16} /> فرق: {varianceEgp > 0 ? "+" : ""}{varianceEgp.toFixed(2)} ج.م</>
              )}
            </div>
          )}

          {/* Reason (required for large variance) */}
          {needsApproval && (
            <div className="space-y-2">
              <span className="text-xs text-red-400 font-bold">سبب الفرق (مطلوب للاعتماد)</span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="اكتب سبب الفرق..."
                className="w-full bg-brand-card border border-red-900/30 rounded-xl px-4 py-2 text-white text-sm outline-none resize-none h-16 focus:border-red-400/50"
              />
            </div>
          )}

          {error && (
            <div className="bg-red-950/30 border border-red-900/40 rounded-xl p-3 text-red-400 text-xs flex items-center gap-2">
              <AlertTriangle size={14} /> {error}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={loading || !countStr}
            className="w-full py-3 bg-gradient-to-l from-red-600 to-red-700 text-white font-bold rounded-xl hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Power size={18} />}
            إغلاق الوردية
          </button>
        </div>
      </div>
      <PinDialog
        isOpen={showPin}
        onClose={() => setShowPin(false)}
        onSuccess={(_managerUser, rawPin) => { setShowPin(false); doClose(rawPin); }}
        title="اعتماد المدير"
      />
    </>
  );
};

// ── X-Report Dialog ──────────────────────────────────────────────────────────

const XReportDialog: React.FC<{
  isOpen: boolean;
  onClose: () => void;
}> = ({ isOpen, onClose }) => {
  const [report, setReport] = useState<XReport | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      bridge.sessionXReport().then(setReport).catch(console.error).finally(() => setLoading(false));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-brand-surface border border-brand-border/60 rounded-3xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6 space-y-5" dir="rtl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <FileText size={20} className="text-blue-400" />
            تقرير X — لقطة لحظية
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X size={20} />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="animate-spin text-brand-gold" size={32} />
          </div>
        ) : report ? (
          <>
            {/* Totals */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-brand-card rounded-xl p-3 border border-brand-border/30 text-center">
                <span className="text-[10px] text-gray-400 block">النقدية المتوقعة</span>
                <span className="text-lg font-black text-brand-teal">{report.totals.expected_cash_egp.toFixed(2)}</span>
              </div>
              <div className="bg-brand-card rounded-xl p-3 border border-brand-border/30 text-center">
                <span className="text-[10px] text-gray-400 block">مبيعات نقدية</span>
                <span className="text-lg font-black text-brand-gold">{report.totals.cash_sales_egp.toFixed(2)}</span>
              </div>
              <div className="bg-brand-card rounded-xl p-3 border border-brand-border/30 text-center">
                <span className="text-[10px] text-gray-400 block">تحصيل سائقين</span>
                <span className="text-lg font-black text-blue-400">{report.totals.driver_remittance_egp.toFixed(2)}</span>
              </div>
              <div className="bg-brand-card rounded-xl p-3 border border-brand-border/30 text-center">
                <span className="text-[10px] text-gray-400 block">مصروفات</span>
                <span className="text-lg font-black text-red-400">{report.totals.expenses_egp.toFixed(2)}</span>
              </div>
            </div>

            {/* Session details */}
            <div className="space-y-3">
              <span className="text-xs text-gray-400 font-bold">ورديات اليوم ({report.sessions.length})</span>
              {report.sessions.map((snap) => (
                <div key={snap.session_id} className="bg-brand-card rounded-xl border border-brand-border/30 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className={`h-2 w-2 rounded-full ${snap.is_open ? "bg-brand-teal animate-pulse" : "bg-gray-500"}`} />
                      <span className="text-sm font-bold text-white">{snap.station}</span>
                      <span className="text-xs text-gray-500">#{snap.session_id}</span>
                    </div>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                      snap.is_open
                        ? "bg-brand-teal/10 text-brand-teal"
                        : "bg-gray-800 text-gray-400"
                    }`}>
                      {snap.is_open ? "مفتوحة" : "مغلقة"}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <span className="text-[10px] text-gray-500 block">العهدة</span>
                      <span className="text-sm font-bold text-white">{snap.opening_float_egp.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500 block">المتوقع</span>
                      <span className="text-sm font-bold text-brand-teal">{snap.expected_cash_egp.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500 block">الفرق</span>
                      <span className={`text-sm font-bold ${
                        snap.variance_egp === null ? "text-gray-500" :
                        snap.variance_egp === 0 ? "text-brand-teal" :
                        "text-red-400"
                      }`}>
                        {snap.variance_egp !== null ? `${snap.variance_egp > 0 ? "+" : ""}${snap.variance_egp.toFixed(2)}` : "—"}
                      </span>
                    </div>
                  </div>
                  {/* Breakdown */}
                  {Object.keys(snap.breakdown).length > 0 && (
                    <div className="mt-3 pt-3 border-t border-brand-border/20 grid grid-cols-2 gap-2">
                      {Object.entries(snap.breakdown).map(([type, entry]) => (
                        <div key={type} className="flex justify-between items-center text-xs">
                          <span className="text-gray-500">{type}</span>
                          <span className="text-gray-300 font-mono">{entry.egp.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {report.sessions.length === 0 && (
                <div className="text-center text-gray-500 py-8 text-sm">لا توجد ورديات صندوق لهذا اليوم</div>
              )}
            </div>
          </>
        ) : (
          <div className="text-center text-gray-500 py-8">فشل في تحميل التقرير</div>
        )}

        <button
          onClick={onClose}
          className="w-full py-2.5 bg-brand-card border border-brand-border/40 text-gray-300 font-bold rounded-xl hover:bg-brand-border/20 transition-all"
        >
          إغلاق
        </button>
      </div>
    </div>
  );
};

// ── Session Card ─────────────────────────────────────────────────────────────

const SessionCard: React.FC<{
  session: CashierSession;
  onClose: (s: CashierSession) => void;
}> = ({ session, onClose }) => {
  const stationColors: Record<string, string> = {
    ALL: "from-brand-gold/20 to-yellow-900/20 border-brand-gold/30",
    COUNTER: "from-blue-900/20 to-indigo-900/20 border-blue-800/30",
    DELIVERY: "from-purple-900/20 to-fuchsia-900/20 border-purple-800/30",
  };
  const stationLabels: Record<string, string> = {
    ALL: "الكل",
    COUNTER: "كاونتر",
    DELIVERY: "توصيل",
  };

  return (
    <div className={`bg-gradient-to-br ${stationColors[session.station] || stationColors.ALL} rounded-2xl border p-5 space-y-4 hover:shadow-lg transition-shadow`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-white/5 flex items-center justify-center">
            <Wallet size={20} className="text-brand-gold" />
          </div>
          <div>
            <span className="text-sm font-bold text-white block">{stationLabels[session.station]} #{session.id}</span>
            <span className="text-[10px] text-gray-400 block mt-0.5">
              <Clock size={10} className="inline ml-1" />
              {session.opened_at ? new Date(session.opened_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" }) : "—"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-brand-teal animate-pulse" />
          <span className="text-xs text-brand-teal font-bold">مفتوحة</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-black/20 rounded-xl p-3 text-center">
          <span className="text-[10px] text-gray-400 block">العهدة</span>
          <span className="text-base font-black text-white">{session.opening_float_egp.toFixed(2)}</span>
          <span className="text-[10px] text-gray-500 block">ج.م</span>
        </div>
        <div className="bg-black/20 rounded-xl p-3 text-center">
          <span className="text-[10px] text-gray-400 block">المتوقع حالياً</span>
          <span className="text-base font-black text-brand-teal">
            {(session.expected_cash_egp ?? session.opening_float_egp).toFixed(2)}
          </span>
          <span className="text-[10px] text-gray-500 block">ج.م</span>
        </div>
      </div>

      {/* Actions */}
      <button
        onClick={() => onClose(session)}
        className="w-full py-2.5 bg-red-950/30 border border-red-900/30 text-red-400 font-bold rounded-xl text-sm hover:bg-red-950/50 hover:border-red-800/40 active:scale-[0.98] transition-all flex items-center justify-center gap-2"
      >
        <Power size={14} />
        إغلاق الوردية
      </button>
    </div>
  );
};

// ── Main Sessions View ───────────────────────────────────────────────────────

export const SessionsView: React.FC<SessionsViewProps> = ({ currentUser }) => {
  const [sessions, setSessions] = useState<CashierSession[]>([]);
  const [allSessions, setAllSessions] = useState<CashierSession[]>([]);
  const [loading, setLoading] = useState(true);

  // Dialogs
  const [showOpen, setShowOpen] = useState(false);
  const [showClose, setShowClose] = useState(false);
  const [closeTarget, setCloseTarget] = useState<CashierSession | null>(null);
  const [showXReport, setShowXReport] = useState(false);

  const isManagerOrAbove = currentUser?.role === "manager" || currentUser?.role === "admin";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const active = await bridge.sessionGetActive();
      const all = await bridge.sessionGetAll();
      setSessions(active);
      setAllSessions(all);
    } catch (e) {
      console.error("Failed to load sessions:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCloseSession = (s: CashierSession) => {
    setCloseTarget(s);
    setShowClose(true);
  };

  // Quick stats
  const openCount = sessions.length;
  const closedCount = allSessions.filter((s) => !s.is_open).length;
  const totalExpected = sessions.reduce((a, s) => a + (s.expected_cash_egp ?? s.opening_float_egp), 0);

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)] bg-brand-dark">
        <RefreshCw className="animate-spin text-brand-gold" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل ورديات الصندوق...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 h-[calc(100vh-64px)] bg-brand-dark" dir="rtl">

      {/* Summary row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          label="ورديات مفتوحة"
          value={String(openCount)}
          icon={<Wallet size={24} />}
          color={openCount > 0 ? "text-brand-teal" : "text-gray-500"}
        />
        <StatCard
          label="ورديات مغلقة اليوم"
          value={String(closedCount)}
          icon={<CheckCircle2 size={24} />}
          color="text-gray-400"
        />
        <StatCard
          label="إجمالي النقدية المتوقعة"
          value={`${totalExpected.toFixed(2)} ج.م`}
          icon={<BarChart3 size={24} />}
          color="text-brand-gold"
        />
        <StatCard
          label="المستخدم الحالي"
          value={currentUser?.display_name || "—"}
          icon={<User size={24} />}
          color="text-white"
        />
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => setShowOpen(true)}
          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-l from-brand-gold to-yellow-600 text-brand-dark font-bold rounded-xl hover:brightness-110 active:scale-[0.98] transition-all text-sm"
        >
          <Plus size={16} />
          فتح وردية جديدة
        </button>
        {isManagerOrAbove && (
          <button
            onClick={() => setShowXReport(true)}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-card border border-brand-border/40 text-white font-bold rounded-xl hover:bg-brand-border/20 active:scale-[0.98] transition-all text-sm"
          >
            <FileText size={16} className="text-blue-400" />
            تقرير X (لقطة لحظية)
          </button>
        )}
        <button
          onClick={refresh}
          className="flex items-center gap-2 px-4 py-2.5 bg-brand-card border border-brand-border/40 text-gray-400 font-bold rounded-xl hover:text-white active:scale-[0.98] transition-all text-sm"
        >
          <RefreshCw size={14} />
          تحديث
        </button>
      </div>

      {/* Active sessions grid */}
      <div>
        <h2 className="text-base font-bold text-white mb-4 flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-brand-teal animate-pulse" />
          الورديات المفتوحة
        </h2>
        {sessions.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {sessions.map((s) => (
              <SessionCard key={s.id} session={s} onClose={handleCloseSession} />
            ))}
          </div>
        ) : (
          <div className="bg-brand-card rounded-2xl border border-brand-border/30 p-12 text-center space-y-3">
            <Wallet size={40} className="mx-auto text-gray-600" />
            <p className="text-gray-500 text-sm">لا توجد ورديات مفتوحة حالياً</p>
            <button
              onClick={() => setShowOpen(true)}
              className="text-brand-gold text-sm font-bold hover:underline"
            >
              فتح وردية جديدة ←
            </button>
          </div>
        )}
      </div>

      {/* Closed sessions table */}
      {allSessions.filter((s) => !s.is_open).length > 0 && (
        <div>
          <h2 className="text-base font-bold text-white mb-4">الورديات المغلقة اليوم</h2>
          <div className="bg-brand-card rounded-2xl border border-brand-border/30 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-brand-surface text-gray-400 text-xs">
                  <th className="py-3 px-4 text-right font-bold">المحطة</th>
                  <th className="py-3 px-4 text-right font-bold">وقت الفتح</th>
                  <th className="py-3 px-4 text-right font-bold">وقت الإغلاق</th>
                  <th className="py-3 px-4 text-right font-bold">العهدة</th>
                  <th className="py-3 px-4 text-right font-bold">المتوقع</th>
                  <th className="py-3 px-4 text-right font-bold">الفعلي</th>
                  <th className="py-3 px-4 text-right font-bold">الفرق</th>
                </tr>
              </thead>
              <tbody>
                {allSessions.filter((s) => !s.is_open).map((s) => {
                  const varianceColor =
                    s.variance_pt === null || s.variance_pt === 0
                      ? "text-brand-teal"
                      : Math.abs(s.variance_pt!) <= 2000
                      ? "text-yellow-400"
                      : "text-red-400";
                  return (
                    <tr key={s.id} className="border-t border-brand-border/20 hover:bg-brand-surface/50 transition-colors">
                      <td className="py-3 px-4 text-white font-bold">{s.station}</td>
                      <td className="py-3 px-4 text-gray-400">
                        {s.opened_at ? new Date(s.opened_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" }) : "—"}
                      </td>
                      <td className="py-3 px-4 text-gray-400">
                        {s.closed_at ? new Date(s.closed_at).toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" }) : "—"}
                      </td>
                      <td className="py-3 px-4 text-white">{s.opening_float_egp.toFixed(2)}</td>
                      <td className="py-3 px-4 text-brand-teal">{(s.expected_cash_egp ?? 0).toFixed(2)}</td>
                      <td className="py-3 px-4 text-white">{s.counted_cash_egp !== null ? s.counted_cash_egp.toFixed(2) : "—"}</td>
                      <td className={`py-3 px-4 font-bold ${varianceColor}`}>
                        {s.variance_egp !== null ? `${s.variance_egp > 0 ? "+" : ""}${s.variance_egp.toFixed(2)}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Dialogs */}
      <OpenSessionDialog
        isOpen={showOpen}
        onClose={() => setShowOpen(false)}
        currentUser={currentUser}
        onSuccess={refresh}
      />
      <CloseSessionDialog
        isOpen={showClose}
        session={closeTarget}
        onClose={() => { setShowClose(false); setCloseTarget(null); }}
        onSuccess={refresh}
      />
      <XReportDialog
        isOpen={showXReport}
        onClose={() => setShowXReport(false)}
      />
    </div>
  );
};
