import React from "react";
import { Delete, Check } from "lucide-react";

interface NumpadProps {
  value: string;
  onChange: (val: string) => void;
  onConfirm?: () => void;
  confirmLabel?: string;
  confirmColor?: string;
}

export const Numpad: React.FC<NumpadProps> = ({
  value,
  onChange,
  onConfirm,
  confirmLabel = "موافق",
  confirmColor = "bg-brand-gold text-brand-dark hover:bg-opacity-90"
}) => {
  const handlePress = (num: string) => {
    onChange(value + num);
  };

  const handleBackspace = () => {
    if (value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const handleClear = () => {
    onChange("");
  };

  const buttons = [
    "1", "2", "3",
    "4", "5", "6",
    "7", "8", "9",
    "C", "0", "back"
  ];

  return (
    <div className="w-full max-w-xs mx-auto p-4 bg-brand-surface rounded-2xl border border-brand-border/40 shadow-2xl">
      <div className="grid grid-cols-3 gap-3">
        {buttons.map((btn, idx) => {
          if (btn === "C") {
            return (
              <button
                key={idx}
                type="button"
                onClick={handleClear}
                className="h-16 text-lg font-bold rounded-xl bg-red-950/40 text-red-400 border border-red-900/30 active:translate-y-0.5 btn-hover-active"
              >
                مسح
              </button>
            );
          }
          if (btn === "back") {
            return (
              <button
                key={idx}
                type="button"
                onClick={handleBackspace}
                className="h-16 flex items-center justify-center rounded-xl bg-brand-border/20 text-gray-300 border border-brand-border/40 active:translate-y-0.5 btn-hover-active"
              >
                <Delete size={20} />
              </button>
            );
          }
          return (
            <button
              key={idx}
              type="button"
              onClick={() => handlePress(btn)}
              className="h-16 text-2xl font-bold rounded-xl bg-brand-card text-white border border-brand-border/30 hover:border-brand-gold/40 active:translate-y-0.5 btn-hover-active"
            >
              {btn}
            </button>
          );
        })}
      </div>

      {onConfirm && (
        <button
          type="button"
          onClick={onConfirm}
          className={`w-full mt-4 h-14 rounded-xl font-bold text-lg flex items-center justify-center gap-2 active:translate-y-0.5 btn-hover-active ${confirmColor}`}
        >
          <Check size={20} />
          {confirmLabel}
        </button>
      )}
    </div>
  );
};
