import React, { useState } from "react";
import { X, Percent, DollarSign, Lock } from "lucide-react";
import { Numpad } from "./Numpad";

interface DiscountDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (discountType: "flat" | "percent", amount: number, managerPin?: string) => Promise<void>;
  currentUser: any;
  subtotal: number;
}

export const DiscountDialog: React.FC<DiscountDialogProps> = ({
  isOpen,
  onClose,
  onApply,
  currentUser,
  subtotal
}) => {
  const [discountType, setDiscountType] = useState<"flat" | "percent">("flat");
  const [amount, setAmount] = useState("");
  // "amount" = entering discount value; "pin" = cashier entering manager PIN
  const [step, setStep] = useState<"amount" | "pin">("amount");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const reset = () => {
    setStep("amount");
    setPin("");
    setError("");
    setLoading(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleApplyClick = () => {
    const numAmount = parseFloat(amount);
    if (isNaN(numAmount) || numAmount <= 0) return;

    if (discountType === "percent" && numAmount > 100) return;
    if (discountType === "flat" && numAmount > subtotal) return;

    if (currentUser?.role === "manager" || currentUser?.role === "admin") {
      applyWithPin(undefined);
    } else {
      setStep("pin");
      setPin("");
      setError("");
    }
  };

  const applyWithPin = async (managerPin: string | undefined) => {
    const numAmount = parseFloat(amount);
    setLoading(true);
    setError("");
    try {
      await onApply(discountType, numAmount, managerPin);
      reset();
      onClose();
    } catch (e: any) {
      setError(e.message || "فشل تطبيق الخصم");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-md mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">

        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-brand-border/60 bg-brand-card">
          <h3 className="font-bold text-lg text-brand-red">
            {step === "pin" ? "موافقة المدير مطلوبة لتطبيق الخصم" : "تطبيق الخصم على الطلب"}
          </h3>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6">
          {step === "amount" ? (
            <>
              {/* Toggle discount type */}
              <div className="grid grid-cols-2 gap-3 mb-6">
                <button
                  type="button"
                  onClick={() => { setDiscountType("flat"); setAmount(""); }}
                  className={`py-3 rounded-xl border font-bold flex items-center justify-center gap-2 transition-all ${
                    discountType === "flat"
                      ? "bg-brand-red/10 border-brand-red text-brand-red"
                      : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                  }`}
                >
                  <DollarSign size={18} />
                  قيمة ثابتة (ج.م)
                </button>
                <button
                  type="button"
                  onClick={() => { setDiscountType("percent"); setAmount(""); }}
                  className={`py-3 rounded-xl border font-bold flex items-center justify-center gap-2 transition-all ${
                    discountType === "percent"
                      ? "bg-brand-red/10 border-brand-red text-brand-red"
                      : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                  }`}
                >
                  <Percent size={18} />
                  نسبة مئوية (%)
                </button>
              </div>

              <div className="mb-4">
                <input
                  type="text"
                  readOnly
                  value={amount ? `${amount} ${discountType === "flat" ? "ج.م" : "%"}` : "0"}
                  className="w-full text-center text-3xl font-extrabold bg-transparent border-none text-white focus:outline-none placeholder-gray-600"
                />
              </div>

              {error && (
                <div className="mb-4 py-2 px-3 bg-red-950/40 border border-red-900/50 rounded-xl text-red-400 text-sm text-center font-medium">
                  {error}
                </div>
              )}

              <Numpad
                value={amount}
                onChange={(val) => {
                  if (discountType === "percent" && parseFloat(val) > 100) return;
                  if (val.includes("..")) return;
                  setAmount(val);
                }}
                onConfirm={handleApplyClick}
                confirmLabel={loading ? "جاري التطبيق..." : "تطبيق الخصم"}
                confirmColor="bg-brand-red text-brand-dark hover:bg-opacity-90 font-bold"
              />
            </>
          ) : (
            /* PIN step — cashier must supply manager PIN */
            <>
              <div className="flex items-center gap-2 justify-center text-brand-red mb-4">
                <Lock size={18} />
              </div>

              <div className="w-full mb-6">
                <div className="flex justify-center gap-3 mb-2">
                  {[0, 1, 2, 3].map((idx) => (
                    <div
                      key={idx}
                      className={`w-4 h-4 rounded-full border border-brand-red/60 transition-colors ${
                        pin.length > idx ? "bg-brand-red" : "bg-transparent"
                      }`}
                    />
                  ))}
                </div>
                <input
                  type="password"
                  readOnly
                  value={pin}
                  placeholder="••••"
                  className="w-full text-center text-3xl tracking-widest bg-transparent border-none text-white focus:outline-none placeholder-gray-600"
                />
              </div>

              {error && (
                <div className="w-full mb-4 py-2 px-3 bg-red-950/40 border border-red-900/50 rounded-xl text-red-400 text-sm text-center font-medium">
                  {error}
                </div>
              )}

              <Numpad
                value={pin}
                onChange={(val) => { if (val.length <= 4) setPin(val); }}
                onConfirm={() => { if (pin) applyWithPin(pin); }}
                confirmLabel={loading ? "جاري التحقق..." : "تأكيد الرمز"}
                confirmColor="bg-brand-red text-brand-dark hover:bg-opacity-90 font-bold"
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
};
