import React, { useEffect, useState } from "react";
import { X, Lock } from "lucide-react";

interface ManagerApprovalDialogProps {
  isOpen: boolean;
  title: string;
  /** Short description of what is being approved (order #, item name...). */
  subtitle?: string;
  reasonLabel?: string;
  confirmLabel?: string;
  /** Resolve with an error message to keep the dialog open, or nothing to close it. */
  onConfirm: (managerPin: string, reason: string) => Promise<string | void> | string | void;
  onClose: () => void;
}

/**
 * Manager approval for a destructive action (cancel an order, remove an item).
 * The cashier stays logged in: the manager types their own PIN, which the
 * backend uses to identify who approved. A reason is mandatory.
 */
export const ManagerApprovalDialog: React.FC<ManagerApprovalDialogProps> = ({
  isOpen,
  title,
  subtitle,
  reasonLabel = "السبب (مطلوب)",
  confirmLabel = "تأكيد",
  onConfirm,
  onClose,
}) => {
  const [reason, setReason] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setReason("");
      setPin("");
      setError("");
      setBusy(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const submit = async () => {
    if (!reason.trim()) { setError("يجب إدخال السبب"); return; }
    if (!pin.trim()) { setError("يجب إدخال رمز PIN المدير"); return; }
    setBusy(true);
    setError("");
    try {
      const err = await onConfirm(pin.trim(), reason.trim());
      if (err) {
        setError(err);
        setPin("");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 backdrop-blur-md" dir="rtl" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div
        role="dialog"
        aria-label={title}
        className="w-full max-w-sm mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl p-6 space-y-4"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-bold text-xl text-red-400 flex items-center gap-2">
              <Lock size={18} />
              {title}
            </h3>
            {subtitle && <p className="text-gray-400 text-xs mt-1">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="إغلاق"
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
          >
            <X size={18} />
          </button>
        </div>
        <div>
          <label className="text-gray-400 text-xs block mb-1.5">{reasonLabel}</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            aria-label="السبب"
            className="w-full bg-brand-dark border border-brand-border/50 rounded-xl p-3 text-white text-sm focus:outline-none focus:border-red-500 resize-none"
            placeholder="اكتب السبب..."
          />
        </div>
        <div>
          <label className="text-gray-400 text-xs block mb-1.5">PIN المدير</label>
          <input
            type="password"
            value={pin}
            aria-label="رمز PIN للمدير"
            onChange={(e) => setPin(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            className="w-full bg-brand-dark border border-brand-border/50 rounded-xl p-3 text-white font-mono text-center text-lg tracking-widest focus:outline-none focus:border-red-500"
            placeholder="••••"
          />
        </div>
        {error && (
          <div role="alert" className="py-2 px-3 bg-red-950/40 border border-red-900/50 rounded-xl text-red-400 text-sm text-center font-medium">
            {error}
          </div>
        )}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 bg-brand-card border border-brand-border/40 text-gray-300 font-bold rounded-xl hover:bg-brand-border/20 transition-all"
          >
            تراجع
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="flex-1 py-3 bg-red-900/40 text-red-300 border border-red-900/50 font-bold rounded-xl hover:bg-red-900/60 transition-all disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
