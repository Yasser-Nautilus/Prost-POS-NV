import React, { useState, useEffect } from "react";
import { X, Calendar, Plus, Power, Loader2 } from "lucide-react";
import { bridge } from "../bridge";
import { PinDialog } from "./PinDialog";

interface ShiftDialogProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: any;
  onShiftStatusChange: () => void;
}

export const ShiftDialog: React.FC<ShiftDialogProps> = ({
  isOpen,
  onClose,
  currentUser,
  onShiftStatusChange
}) => {
  const [activeShift, setActiveShift] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [expenses, setExpenses] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // New Expense form — categories must match backend: supplies | delivery_fees | other
  const [expAmount, setExpAmount] = useState("");
  const [expDesc, setExpDesc] = useState("");
  const [expCat, setExpCat] = useState("supplies");

  // PIN gate for close shift (all roles must provide manager PIN per backend)
  const [showPinGate, setShowPinGate] = useState(false);

  const isManagerOrAbove = currentUser?.role === "manager" || currentUser?.role === "admin";

  const fetchShiftData = async () => {
    setLoading(true);
    try {
      const shift = await bridge.call("get_active_shift");
      setActiveShift(shift);

      if (shift) {
        // Bridge auto-resolves shift_id from active shift when not passed
        const sumData = await bridge.call("get_shift_summary");
        setSummary(sumData);

        const expData = await bridge.call("get_expenses");
        setExpenses(expData || []);
      } else {
        setSummary(null);
        setExpenses([]);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchShiftData();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleAddExpense = async (e: React.FormEvent) => {
    e.preventDefault();
    const amount = parseFloat(expAmount);
    if (isNaN(amount) || amount <= 0 || !expDesc) return;

    try {
      // Bridge auto-resolves shift_id and user_id from session
      await bridge.call("add_expense", {
        amount,
        description: expDesc,
        category: expCat,   // must be: supplies | delivery_fees | other
      });
      setExpAmount("");
      setExpDesc("");
      fetchShiftData();
    } catch (err: any) {
      alert("فشل إضافة المصروف: " + err.message);
    }
  };

  const handleOpenShift = async () => {
    try {
      setLoading(true);
      // Call open_shift with current user's id — bridge handles the rest
      await bridge.call("open_shift", { user_id: currentUser?.id });
      onShiftStatusChange();
      fetchShiftData();
    } catch (err: any) {
      alert("فشل فتح الوردية: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  // For manager/admin: close directly; for cashier: require manager PIN
  const handleCloseShiftClick = () => {
    if (isManagerOrAbove) {
      // Manager can close directly — still needs to pass their own PIN or we skip
      // Per progress.md: close_shift requires manager_pin
      setShowPinGate(true);
    } else {
      setShowPinGate(true);
    }
  };

  const performCloseShift = async (managerPin: string) => {
    try {
      setLoading(true);
      // Bridge auto-resolves shift_id from active shift
      await bridge.call("close_shift", { manager_pin: managerPin });
      onShiftStatusChange();
      fetchShiftData();
      onClose();
    } catch (err: any) {
      alert("فشل إغلاق الوردية: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const CATEGORY_LABELS: Record<string, string> = {
    supplies: "مستلزمات وخامات",
    delivery_fees: "رسوم توصيل",
    other: "مصروفات عامة",
  };

  return (
    <>
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/75 backdrop-blur-md">
        <div className="w-full max-w-4xl mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">

          {/* Header */}
          <div className="flex justify-between items-center px-6 py-4 border-b border-brand-border/60 bg-brand-card">
            <h3 className="font-bold text-lg text-brand-gold flex items-center gap-2">
              <Calendar size={20} />
              إدارة وردية الصندوق
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
            >
              <X size={20} />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 grid grid-cols-1 md:grid-cols-5 gap-6">

            {/* Right Panel: Shift Info & Financials (3 cols) */}
            <div className="md:col-span-3 space-y-6">
              {activeShift ? (
                <>
                  {/* Shift Metadata */}
                  <div className="bg-brand-card p-4 rounded-2xl border border-brand-border/40 flex justify-between items-center">
                    <div>
                      <span className="text-gray-400 text-xs block">تاريخ وبداية الوردية</span>
                      <span className="text-white font-medium block mt-1">
                        {new Date(activeShift.opened_at).toLocaleString("ar-EG")}
                      </span>
                    </div>
                    <div className="py-1 px-3 bg-brand-teal/10 text-brand-teal rounded-lg font-bold text-sm">
                      نشطة حالياً
                    </div>
                  </div>

                  {/* Shift Stats Summary Grid */}
                  {summary && (
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-brand-card/40 p-4 rounded-xl border border-brand-border/30">
                        <span className="text-gray-400 text-xs block">مبيعات الوردية (الإجمالي)</span>
                        <span className="text-2xl font-black text-white mt-1 block">
                          {(summary.total_sales || 0).toFixed(2)} ج.م
                        </span>
                      </div>
                      <div className="bg-brand-card/40 p-4 rounded-xl border border-brand-border/30">
                        <span className="text-gray-400 text-xs block">إجمالي المصروفات الخارجة</span>
                        <span className="text-2xl font-black text-red-400 mt-1 block">
                          {(summary.total_expenses || 0).toFixed(2)} - ج.م
                        </span>
                      </div>
                      <div className="bg-brand-card/40 p-4 rounded-xl border border-brand-border/30">
                        <span className="text-gray-400 text-xs block">صالة وتيك أواي معلقة</span>
                        <span className="text-xl font-bold text-yellow-500 mt-1 block">
                          {((summary.pending_dinein || 0) + (summary.pending_kitchen || 0)).toFixed(2)} ج.م
                        </span>
                      </div>
                      <div className="bg-brand-card/40 p-4 rounded-xl border border-brand-border/30">
                        <span className="text-gray-400 text-xs block">معلق طيارين (دليفري)</span>
                        <span className="text-xl font-bold text-yellow-500 mt-1 block">
                          {(summary.pending_delivery || 0).toFixed(2)} ج.م
                        </span>
                      </div>
                      <div className="bg-brand-card p-4 rounded-xl border border-brand-gold/30 col-span-2 flex justify-between items-center bg-gradient-to-r from-brand-card to-brand-gold/5">
                        <div>
                          <span className="text-brand-gold text-xs block font-bold">النقدية الفعلية المفترضة بالدرج</span>
                          <span className="text-3xl font-black text-brand-gold mt-1 block">
                            {(summary.expected_cash || 0).toFixed(2)} ج.م
                          </span>
                        </div>
                        {/* Only manager/admin can close shift */}
                        {isManagerOrAbove && (
                          <button
                            onClick={handleCloseShiftClick}
                            disabled={loading}
                            className="py-3 px-5 bg-red-600 hover:bg-red-700 text-white font-bold rounded-xl flex items-center gap-1.5 active:translate-y-0.5 btn-hover-active disabled:opacity-50"
                          >
                            {loading ? <Loader2 size={18} className="animate-spin" /> : <Power size={18} />}
                            إغلاق الوردية
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-12 bg-brand-card/20 rounded-3xl border border-brand-border/30 flex flex-col items-center justify-center">
                  <Power size={48} className="text-red-500/80 mb-3" />
                  <h4 className="text-lg font-bold text-white mb-2">لا توجد وردية مفتوحة حالياً</h4>
                  <p className="text-gray-400 text-sm max-w-sm mb-6">
                    الوردية مغلقة. يرجى فتح وردية جديدة حتى تتمكن من بدء المعاملات وطباعة الفواتير.
                  </p>
                  {/* Any logged-in user can open a shift per progress.md */}
                  <button
                    onClick={handleOpenShift}
                    disabled={loading}
                    className="py-3 px-6 bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold rounded-xl active:translate-y-0.5 btn-hover-active disabled:opacity-50 flex items-center gap-2"
                  >
                    {loading ? <Loader2 size={18} className="animate-spin" /> : <Power size={18} />}
                    فتح وردية صندوق جديدة
                  </button>
                </div>
              )}
            </div>

            {/* Left Panel: Expenses Logging & History (2 cols) */}
            <div className="md:col-span-2 border-r md:border-r border-brand-border/50 pr-0 md:pr-6 space-y-6">
              {activeShift && (
                <>
                  {/* Expense Form */}
                  <form onSubmit={handleAddExpense} className="space-y-4">
                    <h4 className="text-sm font-bold text-brand-gold flex items-center gap-1">
                      <Plus size={16} />
                      تسجيل مصروفات خارجة (نثريات)
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-gray-400 text-xs block mb-1">المبلغ (ج.م)</label>
                        <input
                          type="number"
                          required
                          min="0.01"
                          step="0.01"
                          placeholder="0.00"
                          value={expAmount}
                          onChange={(e) => setExpAmount(e.target.value)}
                          className="w-full bg-brand-card border border-brand-border/50 rounded-lg p-2 text-white focus:outline-none focus:border-brand-gold text-center font-mono font-bold"
                        />
                      </div>
                      <div>
                        <label className="text-gray-400 text-xs block mb-1">البند</label>
                        <select
                          value={expCat}
                          onChange={(e) => setExpCat(e.target.value)}
                          className="w-full bg-brand-card border border-brand-border/50 rounded-lg p-2 text-white focus:outline-none focus:border-brand-gold"
                        >
                          <option value="supplies">مستلزمات وخامات</option>
                          <option value="delivery_fees">رسوم توصيل</option>
                          <option value="other">مصروفات عامة</option>
                        </select>
                      </div>
                      <div className="col-span-2">
                        <label className="text-gray-400 text-xs block mb-1">الوصف التفصيلي</label>
                        <input
                          type="text"
                          required
                          placeholder="مثال: شراء كراتين كول سلو..."
                          value={expDesc}
                          onChange={(e) => setExpDesc(e.target.value)}
                          className="w-full bg-brand-card border border-brand-border/50 rounded-lg p-2 text-white focus:outline-none focus:border-brand-gold"
                        />
                      </div>
                    </div>
                    <button
                      type="submit"
                      className="w-full py-2 bg-brand-card hover:bg-brand-border/40 text-brand-gold border border-brand-gold/30 hover:border-brand-gold rounded-lg font-semibold text-sm active:translate-y-0.5 btn-hover-active"
                    >
                      تسجيل وحفظ المصروف
                    </button>
                  </form>

                  {/* Expenses history list */}
                  <div className="space-y-2">
                    <h5 className="text-xs font-semibold text-gray-400">سجل المصروفات بالوردية الحالية:</h5>
                    <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1">
                      {expenses.length > 0 ? (
                        expenses.map((exp) => (
                          <div key={exp.id} className="p-2 bg-brand-card/30 border border-brand-border/20 rounded-lg flex justify-between items-center text-xs">
                            <div>
                              <span className="text-white font-medium block">{exp.description}</span>
                              <span className="text-gray-500 mt-0.5 inline-block">
                                {CATEGORY_LABELS[exp.category] || exp.category}
                              </span>
                            </div>
                            <span className="font-bold text-red-400">-{exp.amount} ج.م</span>
                          </div>
                        ))
                      ) : (
                        <p className="text-gray-500 text-xs italic py-2 text-center">لا توجد مصروفات مسجلة.</p>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>

          </div>
        </div>
      </div>

      {/* PIN gate for close shift — always requires manager PIN per backend */}
      <PinDialog
        isOpen={showPinGate}
        onClose={() => setShowPinGate(false)}
        onSuccess={(_managerUser, rawPin) => {
          setShowPinGate(false);
          performCloseShift(rawPin);
        }}
        title="أدخل رمز PIN للمدير لإغلاق الوردية"
      />
    </>
  );
};
