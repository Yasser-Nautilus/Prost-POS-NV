import React, { useState } from "react";
import { X, Percent, DollarSign } from "lucide-react";
import { Numpad } from "./Numpad";
import { PinDialog } from "./PinDialog";

interface DiscountDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (discountType: "flat" | "percent", amount: number, managerPin?: string) => void;
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
  const [showPinGate, setShowPinGate] = useState(false);

  if (!isOpen) return null;

  const handleApplyClick = () => {
    const numAmount = parseFloat(amount);
    if (isNaN(numAmount) || numAmount <= 0) return;

    // Validation: percent cannot exceed 100%, flat cannot exceed subtotal
    if (discountType === "percent" && numAmount > 100) return;
    if (discountType === "flat" && numAmount > subtotal) return;

    // Managers and admins can apply discounts directly per progress.md
    if (currentUser?.role === "manager" || currentUser?.role === "admin") {
      onApply(discountType, numAmount);
      onClose();
    } else {
      // Cashier must get manager PIN override
      setShowPinGate(true);
    }
  };

  const handlePinSuccess = (_managerUser: any, rawPin: string) => {
    const numAmount = parseFloat(amount);
    // Forward the manager's raw PIN so bridge can verify it server-side
    onApply(discountType, numAmount, rawPin);
    setShowPinGate(false);
    onClose();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
        <div className="w-full max-w-md mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
          
          {/* Header */}
          <div className="flex justify-between items-center px-6 py-4 border-b border-brand-border/60 bg-brand-card">
            <h3 className="font-bold text-lg text-brand-gold">تطبيق الخصم على الطلب</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
            >
              <X size={20} />
            </button>
          </div>

          {/* Body */}
          <div className="p-6">
            {/* Toggle discount type */}
            <div className="grid grid-cols-2 gap-3 mb-6">
              <button
                type="button"
                onClick={() => {
                  setDiscountType("flat");
                  setAmount("");
                }}
                className={`py-3 rounded-xl border font-bold flex items-center justify-center gap-2 transition-all ${
                  discountType === "flat"
                    ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
                    : "bg-brand-card border-brand-border/50 text-gray-400 hover:text-white"
                }`}
              >
                <DollarSign size={18} />
                قيمة ثابتة (ج.م)
              </button>
              <button
                type="button"
                onClick={() => {
                  setDiscountType("percent");
                  setAmount("");
                }}
                className={`py-3 rounded-xl border font-bold flex items-center justify-center gap-2 transition-all ${
                  discountType === "percent"
                    ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
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

            <Numpad
              value={amount}
              onChange={(val) => {
                // Formatting checks
                if (discountType === "percent" && parseFloat(val) > 100) return;
                if (val.includes("..")) return;
                setAmount(val);
              }}
              onConfirm={handleApplyClick}
              confirmLabel="تطبيق الخصم"
              confirmColor="bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold"
            />
          </div>
        </div>
      </div>

      <PinDialog
        isOpen={showPinGate}
        onClose={() => setShowPinGate(false)}
        onSuccess={handlePinSuccess}
        title="موافقة المدير مطلوبة لتطبيق الخصم"
      />
    </>
  );
};
