import React, { useState, useEffect } from "react";
import { X, Check, Wallet, CreditCard, Globe, CornerDownLeft } from "lucide-react";
import { Numpad } from "./Numpad";

interface PaymentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  total: number;
  orderType?: string;
  onConfirm: (method: string, amountPaid: number, change: number) => void | Promise<void>;
  onConfirmSplit?: (parts: { method: string; amount: number }[], cashReceived: number) => void | Promise<void>;
}

type SplitRow = { method: string; amount: string };
const METHOD_LABELS: Record<string, string> = { cash: "نقدي", visa: "فيزا", online: "أونلاين" };
const toPt = (v: string) => Math.round((parseFloat(v) || 0) * 100);

export const PaymentDialog: React.FC<PaymentDialogProps> = ({
  isOpen,
  onClose,
  total,
  orderType,
  onConfirm,
  onConfirmSplit
}) => {
  const submitting = React.useRef(false);
  const [busy, setBusy] = useState(false);
  const submit = async (action: () => void | Promise<void>) => {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    try { await action(); }
    finally { submitting.current = false; setBusy(false); }
  };
  const [splitMode, setSplitMode] = useState(false);
  const [rows, setRows] = useState<SplitRow[]>([]);
  const [people, setPeople] = useState("2");
  const [cashGiven, setCashGiven] = useState("");
  const [method, setMethod] = useState("cash");
  const [cashReceived, setCashReceived] = useState("");
  const [change, setChange] = useState(0);

  useEffect(() => {
    const received = parseFloat(cashReceived) || 0;
    if (received >= total) {
      setChange(received - total);
    } else {
      setChange(0);
    }
  }, [cashReceived, total]);

  // CHANGED: reset payment inputs every time the dialog opens, so the previous
  // payment's amount/method doesn't carry over to the next order (e.g. 250 paid
  // before showing up again as "amount paid" on a new 500 bill). The Enter-to-
  // confirm shortcut keeps working, but cash must be entered explicitly.
  useEffect(() => {
    if (isOpen) {
      setMethod("cash");
      setCashReceived("");
      setChange(0);
      setSplitMode(false);
      setRows([]);
      setCashGiven("");
    }
  }, [isOpen]);

  const totalPt = Math.round(total * 100);
  const paidPt = rows.reduce((a, r) => a + toPt(r.amount), 0);
  const remainingPt = totalPt - paidPt;
  const cashSharePt = rows.filter((r) => r.method === "cash").reduce((a, r) => a + toPt(r.amount), 0);
  const givenPt = cashGiven.trim() ? toPt(cashGiven) : cashSharePt;
  const splitChangePt = Math.max(0, givenPt - cashSharePt);

  const startSplit = () => {
    setSplitMode(true);
    setRows([
      { method: "cash", amount: (total / 2).toFixed(2) },
      { method: "visa", amount: (total - Math.round(total * 100 / 2) / 100).toFixed(2) },
    ]);
  };

  const splitEqually = () => {
    const n = Math.max(2, Math.min(10, parseInt(people) || 2));
    const each = Math.floor(totalPt / n);
    const next: SplitRow[] = [];
    for (let i = 0; i < n; i++) {
      const pt = i === n - 1 ? totalPt - each * (n - 1) : each;
      next.push({ method: rows[i]?.method || "cash", amount: (pt / 100).toFixed(2) });
    }
    setRows(next);
  };

  const handleSplitConfirm = () => {
    if (!onConfirmSplit) return;
    if (rows.some((r) => toPt(r.amount) <= 0)) {
      alert("كل دفعة يجب أن تكون أكبر من صفر");
      return;
    }
    if (remainingPt !== 0) {
      alert("مجموع الدفعات لا يساوي إجمالي الطلب");
      return;
    }
    if (givenPt < cashSharePt) {
      alert("النقد المستلم أقل من حصة النقد");
      return;
    }
    void submit(() => onConfirmSplit!(rows.map((r) => ({ method: r.method, amount: toPt(r.amount) / 100 })), givenPt / 100));
  };

  const handleQuickCash = (amt: number) => {
    setCashReceived(amt.toString());
  };

  const handlePayConfirm = () => {
    const received = method === "cash" ? Number(cashReceived) : total;
    if (method === "cash" && (!cashReceived.trim() || !Number.isFinite(received) || received < 0)) {
      alert("أدخل المبلغ النقدي المستلم");
      return;
    }
    if (method === "cash" && received < total) {
      alert("المبلغ المدفوع أقل من إجمالي الطلب");
      return;
    }
    const finalChange = method === "cash" ? (received - total) : 0;
    void submit(() => onConfirm(method, received, finalChange));
  };

  // CHANGED: press Enter to confirm the payment
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (splitMode) handleSplitConfirm(); else handlePayConfirm();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, method, cashReceived, total, splitMode, rows, cashGiven]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-4xl mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200 flex flex-col md:flex-row">
        
        {/* Right side: Payment parameters & Keyboard */}
        <div className="flex-1 p-6 flex flex-col justify-between border-l border-brand-border/60">
          <div>
            <div className="flex justify-between items-center mb-6">
              <h3 className="font-bold text-xl text-brand-red">تسوية وإغلاق الفاتورة</h3>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30 md:hidden"
              >
                <X size={20} />
              </button>
            </div>

            {/* Payment Method Selector */}
            <div className={`grid grid-cols-3 gap-3 mb-3 ${splitMode ? "hidden" : ""}`}>
              <button
                type="button"
                onClick={() => {
                  setMethod("cash");
                  setCashReceived("");
                }}
                className={`py-4 rounded-2xl border font-bold flex flex-col items-center justify-center gap-2 transition-all ${
                  method === "cash"
                    ? "bg-brand-red/10 border-brand-red text-brand-red"
                    : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                }`}
              >
                <Wallet size={24} />
                <span>نقدي (كاش)</span>
              </button>
              <button
                type="button"
                disabled={orderType === "delivery"}
                onClick={() => {
                  setMethod("visa");
                  setCashReceived(total.toString());
                }}
                className={`py-4 rounded-2xl border font-bold flex flex-col items-center justify-center gap-2 transition-all ${
                  orderType === "delivery"
                    ? "opacity-40 cursor-not-allowed bg-brand-card border-brand-border/50 text-gray-500"
                    : method === "visa"
                      ? "bg-brand-red/10 border-brand-red text-brand-red"
                      : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                }`}
              >
                <CreditCard size={24} />
                <span>بطاقة فيزا</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setMethod("online");
                  setCashReceived(total.toString());
                }}
                className={`py-4 rounded-2xl border font-bold flex flex-col items-center justify-center gap-2 transition-all ${
                  method === "online"
                    ? "bg-brand-red/10 border-brand-red text-brand-red"
                    : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                }`}
              >
                <Globe size={24} />
                <span>دفع أونلاين</span>
              </button>
            </div>

            {onConfirmSplit && orderType !== "delivery" && !splitMode && (
              <button
                type="button"
                onClick={startSplit}
                className="w-full mb-6 py-2.5 rounded-xl border border-dashed border-brand-border/70 text-gray-300 hover:text-white hover:border-brand-red font-bold text-sm"
              >
                تقسيم الفاتورة / دفع مختلط (كاش + فيزا)
              </button>
            )}

            {splitMode && (
              <div className="space-y-3 mb-6" data-testid="split-payment">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-white">دفع مختلط / تقسيم الفاتورة</h4>
                  <button type="button" onClick={() => setSplitMode(false)} className="text-xs text-gray-400 hover:text-white underline">رجوع لدفعة واحدة</button>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-400">قسّم بالتساوي على</span>
                  <input
                    type="number" min={2} max={10} value={people}
                    onChange={(e) => setPeople(e.target.value)}
                    aria-label="عدد الأشخاص"
                    className="w-16 bg-brand-card border border-brand-border/50 rounded-lg p-1.5 text-white text-center font-mono"
                  />
                  <button type="button" onClick={splitEqually} className="px-3 py-1.5 rounded-lg bg-brand-card border border-brand-border/50 text-white font-semibold hover:border-brand-red">تقسيم</button>
                </div>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {rows.map((r, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <select
                        value={r.method}
                        aria-label={`طريقة الدفعة ${i + 1}`}
                        onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, method: e.target.value } : x))}
                        className="bg-brand-card border border-brand-border/50 rounded-lg p-2 text-white"
                      >
                        {Object.keys(METHOD_LABELS).map((m) => <option key={m} value={m}>{METHOD_LABELS[m]}</option>)}
                      </select>
                      <input
                        type="number" step="0.01" min="0" value={r.amount}
                        aria-label={`مبلغ الدفعة ${i + 1}`}
                        onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))}
                        className="flex-1 bg-brand-card border border-brand-border/50 rounded-lg p-2 text-white font-mono text-left"
                      />
                      {rows.length > 2 && (
                        <button type="button" aria-label={`حذف الدفعة ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))} className="text-gray-400 hover:text-red-400 p-1"><X size={16} /></button>
                      )}
                    </div>
                  ))}
                </div>
                {rows.length < 10 && (
                  <button
                    type="button"
                    onClick={() => setRows([...rows, { method: "cash", amount: Math.max(0, remainingPt / 100).toFixed(2) }])}
                    className="text-sm text-brand-red font-bold"
                  >
                    + إضافة دفعة
                  </button>
                )}
                {cashSharePt > 0 && (
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-gray-400">النقد المستلم (اختياري، لحساب الفكة)</span>
                    <input
                      type="number" step="0.01" min="0" value={cashGiven}
                      aria-label="النقد المستلم"
                      onChange={(e) => setCashGiven(e.target.value)}
                      className="w-28 bg-brand-card border border-brand-border/50 rounded-lg p-1.5 text-white font-mono text-left"
                    />
                  </div>
                )}
              </div>
            )}

            {/* Cash Calculations */}
            {!splitMode && method === "cash" && (
              <div className="space-y-4 mb-6">
                <div>
                  <label className="text-gray-400 text-sm block mb-1">فئات سريعة:</label>
                  <div className="flex gap-2">
                    {[total, 50, 100, 200, 500].map((amt) => {
                      const roundedAmt = Math.ceil(amt);
                      if (roundedAmt < total && amt !== total) return null;
                      return (
                        <button
                          key={amt}
                          type="button"
                          onClick={() => handleQuickCash(roundedAmt)}
                          className="flex-1 py-2 px-1 text-sm font-semibold rounded-lg bg-brand-card border border-brand-border/40 hover:border-brand-red text-white btn-hover-active"
                        >
                          {roundedAmt} ج.م
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="w-full">
            <button
              type="button"
              disabled={busy || (splitMode && remainingPt !== 0)}
              onClick={splitMode ? handleSplitConfirm : handlePayConfirm}
              className="w-full h-16 disabled:opacity-40 disabled:cursor-not-allowed rounded-2xl bg-brand-teal text-white hover:bg-opacity-90 font-bold text-xl flex items-center justify-center gap-2 active:translate-y-0.5 shadow-lg btn-hover-active"
            >
              <Check size={24} />
              إنهاء وتأكيد الدفع ({total.toFixed(2)} ج.م)
              <span className="flex items-center gap-1 text-sm font-semibold opacity-80 bg-white/15 px-2 py-1 rounded-lg">
                <CornerDownLeft size={16} />
                Enter
              </span>
            </button>
          </div>
        </div>

        {/* Left side: Totals summary and numeric entry */}
        <div className="w-full md:w-96 p-6 bg-brand-card flex flex-col justify-between">
          <div className="hidden md:flex justify-end mb-4">
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
            >
              <X size={20} />
            </button>
          </div>

          <div className="space-y-4 mb-6 bg-brand-surface/40 p-5 rounded-2xl border border-brand-border/30">
            <div className="flex justify-between items-center text-gray-400">
              <span>إجمالي الطلب:</span>
              <span className="text-xl font-bold text-white">{total.toFixed(2)} ج.م</span>
            </div>
            {splitMode && (
              <>
                <div className="flex justify-between items-center text-gray-400">
                  <span>مجموع الدفعات:</span>
                  <span className="text-xl font-bold text-white">{(paidPt / 100).toFixed(2)} ج.م</span>
                </div>
                <div className="h-px bg-brand-border/60" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-300 font-bold">{remainingPt >= 0 ? "المتبقي للدفع:" : "زيادة عن الإجمالي:"}</span>
                  <span className={`text-2xl font-black ${remainingPt === 0 ? "text-brand-teal" : "text-brand-red"}`}>
                    {(Math.abs(remainingPt) / 100).toFixed(2)} ج.م
                  </span>
                </div>
                {cashSharePt > 0 && (
                  <div className="flex justify-between items-center text-gray-400">
                    <span>الفكة:</span>
                    <span className="text-lg font-bold text-white">{(splitChangePt / 100).toFixed(2)} ج.م</span>
                  </div>
                )}
              </>
            )}
            {!splitMode && method === "cash" && (
              <>
                <div className="flex justify-between items-center text-gray-400">
                  <span>المبلغ المدفوع:</span>
                  <span className="text-2xl font-black text-brand-red">
                    {(parseFloat(cashReceived) || 0).toFixed(2)} ج.م
                  </span>
                </div>
                <div className="h-px bg-brand-border/60" />
                <div className="flex justify-between items-center">
                  <span className="text-gray-300 font-bold">المتبقي (الفكة):</span>
                  <span className="text-2xl font-black text-brand-teal">
                    {change.toFixed(2)} ج.م
                  </span>
                </div>
              </>
            )}
          </div>

          {splitMode ? (
            <div className="flex-1 flex flex-col justify-center items-center text-center p-6 border-2 border-dashed border-brand-border/50 rounded-2xl">
              <Wallet size={40} className="text-brand-red mb-3" />
              <p className="text-gray-300 font-medium">أدخل مبلغ كل دفعة وطريقتها</p>
              <p className="text-gray-500 text-sm mt-1">يجب أن يساوي المجموع إجمالي الطلب</p>
            </div>
          ) : method === "cash" ? (
            <Numpad
              value={cashReceived}
              onChange={(val) => {
                if (val.includes("..")) return;
                setCashReceived(val);
              }}
            />
          ) : (
            <div className="flex-1 flex flex-col justify-center items-center text-center p-8 border-2 border-dashed border-brand-border/50 rounded-2xl">
              <CreditCard size={48} className="text-brand-red mb-3 animate-pulse" />
              <p className="text-gray-300 font-medium">سيتم تحصيل كامل المبلغ</p>
              <p className="text-3xl font-black text-white mt-2">{total.toFixed(2)} ج.م</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
