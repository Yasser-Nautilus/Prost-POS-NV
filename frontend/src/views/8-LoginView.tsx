import React, { useState, useEffect } from "react";
import { Users, ShieldAlert, Loader2 } from "lucide-react";
import { Numpad } from "../components/Numpad";
import { bridge } from "../bridge";
import loginBackground from "../assets/prostsh-brand.webp";
import { ThemeToggle } from "../components/ThemeToggle";
import prostshP from "../assets/prostsh-p.png";

interface LoginViewProps {
  onLoginSuccess: (user: any) => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<any[]>([]);

  useEffect(() => {
    // Load users list for displaying tiles
    bridge.call("get_all_users")
      .then((res) => setUsers(res || []))
      .catch(console.error);
  }, []);

  const handleLoginSubmit = async () => {
    if (!pin) return;
    setLoading(true);
    setError("");
    try {
      const user = await bridge.call("login", { pin });
      onLoginSuccess(user);
    } catch (e: any) {
      setError(e.message || "فشل تسجيل الدخول. رمز PIN خاطئ.");
      setPin("");
    } finally {
      setLoading(false);
    }
  };

  const handleUserTileClick = () => {
    setPin("");
    setError("الرجاء إدخال رمز PIN الخاص بك أدناه");
  };

  return (
    <main
      className="relative min-h-screen overflow-y-auto bg-brand-dark bg-right bg-no-repeat"
      style={{ backgroundImage: `url(${loginBackground})`, backgroundSize: "auto 135%" }}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background: "linear-gradient(90deg, rgba(10, 10, 12, 0.97) 0%, rgba(10, 10, 12, 0.89) 33%, rgba(10, 10, 12, 0.62) 52%, rgba(10, 10, 12, 0.12) 78%, rgba(10, 10, 12, 0.08) 100%)",
        }}
      />
      <div className="relative z-10 mr-auto ml-0 flex min-h-screen w-full max-w-[900px] flex-col items-center justify-center gap-6 px-6 py-8 md:flex-row md:gap-8 md:px-12" dir="rtl">

      {/* Right column: Branding & Cashier Tiles */}
      <div
        role="region"
        aria-label="قائمة الموظفين — اختر حسابك"
        className="login-art w-full min-w-0 flex-1 text-right space-y-6 flex flex-col justify-center"
      >
        <div className="space-y-2">
          <div className="inline-block py-1.5 px-4 bg-brand-red/10 border border-brand-red/30 rounded-full text-brand-red text-sm font-bold">
            نظام إدارة المبيعات الذكي v1.0
          </div>
          <h1 className="text-4xl font-black text-white leading-tight drop-shadow-lg">
            بروستش <span className="red-gradient-text">Prostsh</span>
          </h1>
          <p className="text-gray-200 text-base leading-relaxed">
            قم باختيار حسابك أو إدخال رمز PIN الخاص بك مباشرة للوصول إلى لوحة المبيعات.
          </p>
        </div>

        {/* User Tiles Grid */}
        <div className="space-y-3">
          <div className="flex items-center gap-3 justify-end">
            <div className="h-px flex-1 bg-brand-border/50" aria-hidden="true" />
            <h3 className="text-xs font-bold text-gray-300 flex items-center gap-1.5">
              الموظفون المتاحون بالوردية
              <Users size={14} className="text-brand-red" />
            </h3>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {users.filter((u) => !(u.role === "cashier" && u.cashier_slot == null)).length > 0 ? (
              users
                .filter((u) => !(u.role === "cashier" && u.cashier_slot == null))
                .map((u) => (
                <div
                  key={u.id}
                  onClick={handleUserTileClick}
                  className="p-4 bg-brand-card/85 backdrop-blur-md hover:bg-brand-border/70 border border-brand-border/60 rounded-2xl cursor-pointer text-right transition-all hover:scale-[1.02] active:scale-[0.98] group"
                >
                  <span className="text-white font-bold block text-base group-hover:text-brand-red transition-colors">
                    {u.display_name}
                  </span>
                  <span className="text-xs text-gray-400 mt-1 inline-block">
                    {u.role === "admin" ? "مدير النظام" : u.role === "manager" ? "مدير المطعم" : "كاشير صندوق"}
                  </span>
                </div>
              ))
            ) : (
              // Fallback placeholder tiles
              <>
                <div onClick={handleUserTileClick} className="p-4 bg-brand-card border border-brand-border/40 rounded-2xl cursor-pointer text-right">
                  <span className="text-white font-bold block">كاشير الوردية</span>
                  <span className="text-xs text-gray-400 mt-1">كاشير صندوق</span>
                </div>
                <div onClick={handleUserTileClick} className="p-4 bg-brand-card border border-brand-border/40 rounded-2xl cursor-pointer text-right">
                  <span className="text-white font-bold block">ياسر المصري</span>
                  <span className="text-xs text-gray-400 mt-1">مدير النظام</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Left column: Security lock & Numpad block */}
      <div
        role="region"
        aria-label="لوحة PIN — أدخل رمز الدخول"
        className="w-full max-w-sm shrink-0 p-6 bg-brand-card/90 backdrop-blur-xl border border-brand-red/25 rounded-3xl shadow-2xl shadow-black/50 flex flex-col items-center"
      >
        <div className="h-20 w-20 rounded-full bg-brand-red/10 text-brand-red flex items-center justify-center mb-4">
          {loading ? (
            <Loader2 size={32} className="animate-spin" />
          ) : (
            <img src={prostshP} alt="شعار بروستش" className="h-12 w-auto drop-shadow-lg" />
          )}
        </div>

        <ThemeToggle className="fixed top-4 left-4 z-50" />
        <h3 className="text-xl font-bold text-white mb-1">تسجيل الدخول للنظام</h3>
        <p className="text-gray-400 text-sm mb-6 text-center">أدخل رمز الـ PIN الخاص بك</p>

        <input type="password" aria-label="رمز PIN" value={pin}
          autoComplete="current-password" onChange={(e) => setPin(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleLoginSubmit(); }}
          className="sr-only" />
        {/* PIN Dot indicators */}
        <div className="flex justify-center gap-3 mb-6">
          {Array.from({ length: Math.max(4, Math.min(pin.length, 12)) }, (_, idx) => (
            <div
              key={idx}
              className={`w-4 h-4 rounded-full border border-brand-red/60 transition-colors ${
                pin.length > idx ? "bg-brand-red" : "bg-transparent"
              }`}
            />
          ))}
        </div>

        {error && (
          <div className="w-full mb-4 py-2 px-3 bg-red-950/40 border border-red-900/50 rounded-xl text-red-400 text-xs text-center font-medium flex items-center justify-center gap-1.5 animate-bounce">
            <ShieldAlert size={14} />
            {error}
          </div>
        )}

        <Numpad
          value={pin}
          maxLength={Number.POSITIVE_INFINITY}
          onChange={(val) => {
            setPin(val);
          }}
          onConfirm={handleLoginSubmit}
          confirmLabel={loading ? "جاري التحقق..." : "تأكيد PIN"}
          confirmColor="bg-brand-red text-brand-dark hover:bg-opacity-90 font-bold"
        />
      </div>

      </div>
    </main>
  );
};
