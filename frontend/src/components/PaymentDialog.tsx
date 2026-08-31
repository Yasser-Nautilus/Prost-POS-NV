import React, { useState, useEffect } from "react";
import { X, Check, Wallet, CreditCard, Globe } from "lucide-react";
import { Numpad } from "./Numpad";

interface PaymentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  total: number;
  onConfirm: (method: string, amountPaid: number, change: number) => void;
}

export const PaymentDialog: React.FC<PaymentDialogProps> = ({
  isOpen,
  onClose,
  total,
  onConfirm
}) => {
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

  if (!isOpen) return null;

  const handleQuickCash = (amt: number) => {
    setCashReceived(amt.toString());
  };

  const handlePayConfirm = () => {
    const received = parseFloat(cashReceived) || total;
    if (method === "cash" && received < total) {
      alert("المبلغ المدفوع أقل من إجمالي الطلب");
      return;
    }
    const finalChange = method === "cash" ? (received - total) : 0;
    onConfirm(method, received, finalChange);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
      <div className="w-full max-w-4xl mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200 flex flex-col md:flex-row">
        
        {/* Right side: Payment parameters & Keyboard */}
        <div className="flex-1 p-6 flex flex-col justify-between border-l border-brand-border/60">
          <div>
            <div className="flex justify-between items-center mb-6">
              <h3 className="font-bold text-xl text-brand-gold">تسوية وإغلاق الفاتورة</h3>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30 md:hidden"
              >
                <X size={20} />
              </button>
            </div>

            {/* Payment Method Selector */}
            <div className="grid grid-cols-3 gap-3 mb-6">
              <button
                type="button"
                onClick={() => {
                  setMethod("cash");
                  setCashReceived("");
                }}
                className={`py-4 rounded-2xl border font-bold flex flex-col items-center justify-center gap-2 transition-all ${
                  method === "cash"
                    ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
                    : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                }`}
              >
                <Wallet size={24} />
                <span>نقدي (كاش)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setMethod("card");
                  setCashReceived(total.toString());
                }}
                className={`py-4 rounded-2xl border font-bold flex flex-col items-center justify-center gap-2 transition-all ${
                  method === "card"
                    ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
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
                    ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
                    : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                }`}
              >
                <Globe size={24} />
                <span>دفع أونلاين</span>
              </button>
            </div>

            {/* Cash Calculations */}
            {method === "cash" && (
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
                          className="flex-1 py-2 px-1 text-sm font-semibold rounded-lg bg-brand-card border border-brand-border/40 hover:border-brand-gold text-white btn-hover-active"
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
              onClick={handlePayConfirm}
              className="w-full h-16 rounded-2xl bg-brand-teal text-white hover:bg-opacity-90 font-bold text-xl flex items-center justify-center gap-2 active:translate-y-0.5 shadow-lg btn-hover-active"
            >
              <Check size={24} />
              إنهاء وتأكيد الدفع ({total.toFixed(2)} ج.م)
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
            {method === "cash" && (
              <>
                <div className="flex justify-between items-center text-gray-400">
                  <span>المبلغ المدفوع:</span>
                  <span className="text-2xl font-black text-brand-gold">
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

          {method === "cash" ? (
            <Numpad
              value={cashReceived}
              onChange={(val) => {
                if (val.includes("..")) return;
                setCashReceived(val);
              }}
            />
          ) : (
            <div className="flex-1 flex flex-col justify-center items-center text-center p-8 border-2 border-dashed border-brand-border/50 rounded-2xl">
              <CreditCard size={48} className="text-brand-gold mb-3 animate-pulse" />
              <p className="text-gray-300 font-medium">سيتم تحصيل كامل المبلغ</p>
              <p className="text-3xl font-black text-white mt-2">{total.toFixed(2)} ج.م</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
