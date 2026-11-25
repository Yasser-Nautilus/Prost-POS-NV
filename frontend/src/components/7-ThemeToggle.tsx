import { useState } from "react";
import { Moon, Sun } from "lucide-react";
import { applyTheme, getTheme, type Theme } from "../theme";

export const ThemeToggle: React.FC<{ className?: string }> = ({ className = "" }) => {
  const [theme, setTheme] = useState<Theme>(getTheme());
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => { applyTheme(next); setTheme(next); }}
      aria-label={next === "light" ? "الوضع الفاتح" : "الوضع الداكن"}
      title={next === "light" ? "الوضع الفاتح" : "الوضع الداكن"}
      className={`flex items-center justify-center min-h-12 min-w-12 rounded-xl border bg-brand-card/80 border-brand-border/40 text-gray-300 hover:text-brand-red hover:border-brand-red/40 active:scale-95 transition-all ${className}`}
    >
      {theme === "dark" ? <Sun size={22} /> : <Moon size={22} />}
    </button>
  );
};
