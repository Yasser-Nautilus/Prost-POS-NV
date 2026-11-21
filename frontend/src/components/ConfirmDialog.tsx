import React from "react";

interface ConfirmDialogProps {
  isOpen: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Reusable confirmation dialog — replaces browser-native window.confirm().
 * Keyboard accessible: Enter confirms, Escape cancels.
 */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  message,
  onConfirm,
  onCancel,
}) => {
  React.useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter") onConfirm();
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onConfirm, onCancel]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className="bg-brand-surface border border-brand-border/60 rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-5"
        dir="rtl"
        role="dialog"
        aria-modal="true"
      >
        <p className="text-white font-bold text-sm text-center">{message}</p>
        <div className="flex gap-3">
          <button
            onClick={onConfirm}
            className="flex-1 py-2.5 bg-gradient-to-l from-red-600 to-red-700 text-white font-bold rounded-xl hover:brightness-110 active:scale-[0.98] transition-all"
            autoFocus
          >
            تأكيد
          </button>
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 bg-brand-card border border-brand-border/40 text-gray-300 font-bold rounded-xl hover:bg-brand-border/20 transition-all"
          >
            إلغاء
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * Hook that provides a promise-based confirm function backed by ConfirmDialog.
 *
 * Usage:
 *   const { confirm, ConfirmUI } = useConfirm();
 *   // in JSX: <>{ConfirmUI}</>
 *   // in handlers: if (!(await confirm("message"))) return;
 */
export function useConfirm() {
  const [state, setState] = React.useState<{
    isOpen: boolean;
    message: string;
    resolve: ((v: boolean) => void) | null;
  }>({ isOpen: false, message: "", resolve: null });

  const confirm = React.useCallback(
    (message: string): Promise<boolean> =>
      new Promise((resolve) =>
        setState((prev) => {
          // Resolve any in-flight promise with false before replacing it.
          prev.resolve?.(false);
          return { isOpen: true, message, resolve };
        }),
      ),
    [],
  );

  const ConfirmUI = (
    <ConfirmDialog
      isOpen={state.isOpen}
      message={state.message}
      onConfirm={() => {
        state.resolve?.(true);
        setState({ isOpen: false, message: "", resolve: null });
      }}
      onCancel={() => {
        state.resolve?.(false);
        setState({ isOpen: false, message: "", resolve: null });
      }}
    />
  );

  return { confirm, ConfirmUI };
}
