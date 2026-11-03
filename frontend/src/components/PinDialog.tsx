import React, { useState } from "react";
import { X, Lock } from "lucide-react";
import { Numpad } from "./Numpad";
import { bridge } from "../bridge";

interface PinDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (managerUser: any, rawPin: string) => void;
  title?: string;
}

export const PinDialog: React.FC<PinDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  title = "تصريح المدير المطلوب"
}) => {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!pin) return;
    setLoading(true);
    setError("");
    try {
      const managerUser = await bridge.call("verify_manager_pin", { pin });
      onSuccess(managerUser, pin);
      setPin("");
      onClose();
    } catch (e: any) {
      setError(e.message || "رمز PIN خاطئ أو المستخدم ليس مديراً");
      setPin("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
      <div className="w-full max-w-md mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
        
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-brand-border/60 bg-brand-card">
          <div className="flex items-center gap-2 text-brand-gold">
            <Lock size={18} />
            <h3 className="font-bold text-lg">{title}</h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 flex flex-col items-center">
          <div className="w-full mb-6">
            <div className="flex justify-center gap-3 mb-2">
              {[0, 1, 2, 3].map((idx) => (
                <div
                  key={idx}
                  className={`w-4 h-4 rounded-full border border-brand-gold/60 transition-colors ${
                    pin.length > idx ? "bg-brand-gold" : "bg-transparent"
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
            onChange={(val) => {
              if (val.length <= 4) setPin(val);
            }}
            onConfirm={handleSubmit}
            confirmLabel={loading ? "جاري التحقق..." : "تأكيد الرمز"}
            confirmColor="bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold"
          />
        </div>
      </div>
    </div>
  );
};
