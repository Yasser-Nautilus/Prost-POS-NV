import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

type Kind = "success" | "error" | "info";
interface Toast { id: number; text: string; kind: Kind }

let nextId = 1;
const listeners = new Set<(t: Toast) => void>();

const ERROR_HINTS = ["فشل", "تعذر", "تعذّر", "خطأ", "يرجى", "يجب", "مطلوب", "أقل", "لا يمكن", "لا يساوي", "غير"];
const SUCCESS_HINTS = ["تم", "بنجاح"];

function kindOf(text: string): Kind {
  if (ERROR_HINTS.some((h) => text.includes(h))) return "error";
  if (SUCCESS_HINTS.some((h) => text.includes(h))) return "success";
  return "info";
}

/** Non-blocking, in-app replacement for window.alert (installed in main.tsx). */
export function showToast(message: unknown): void {
  const text = String(message ?? "");
  if (!text) return;
  const toast = { id: nextId++, text, kind: kindOf(text) };
  listeners.forEach((l) => l(toast));
}

export function installToastAlert(): void {
  window.alert = (message?: unknown) => showToast(message);
}

const STYLE: Record<Kind, { box: string; Icon: typeof Info }> = {
  success: { box: "border-brand-teal/40 text-brand-teal", Icon: CheckCircle2 },
  error: { box: "border-brand-red/40 text-brand-red", Icon: AlertTriangle },
  info: { box: "border-brand-border text-gray-300", Icon: Info },
};

export const ToastHost: React.FC = () => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const onToast = (t: Toast) => {
      setToasts((cur) => [...cur.slice(-3), t]);
      window.setTimeout(
        () => setToasts((cur) => cur.filter((x) => x.id !== t.id)),
        t.kind === "error" ? 7000 : 3500,
      );
    };
    listeners.add(onToast);
    return () => { listeners.delete(onToast); };
  }, []);

  if (toasts.length === 0) return null;
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[200] flex flex-col gap-2 w-full max-w-md px-4" dir="rtl">
      {toasts.map((t) => {
        const { box, Icon } = STYLE[t.kind];
        return (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className={`flex items-start gap-3 rounded-2xl border bg-brand-surface px-4 py-3 shadow-2xl ${box}`}
          >
            <Icon size={22} className="mt-0.5 shrink-0" />
            <p className="flex-1 text-sm font-bold text-white leading-relaxed">{t.text}</p>
            <button
              type="button"
              aria-label="إغلاق"
              onClick={() => setToasts((cur) => cur.filter((x) => x.id !== t.id))}
              className="text-gray-400 hover:text-white"
            >
              <X size={18} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
