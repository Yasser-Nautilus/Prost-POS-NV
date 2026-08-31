import React, { useState, useEffect } from "react";
import { Lock, Users, ShieldAlert, Loader2 } from "lucide-react";
import { Numpad } from "../components/Numpad";
import { bridge } from "../bridge";

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
    <div className="min-h-screen bg-brand-dark flex flex-col md:flex-row items-center justify-center p-6 gap-8">
      
      {/* Right column: Branding & Cashier Tiles */}
      <div className="flex-1 max-w-xl text-right space-y-6 flex flex-col justify-center">
        <div className="space-y-2">
          <div className="inline-block py-1.5 px-4 bg-brand-gold/10 border border-brand-gold/30 rounded-full text-brand-gold text-sm font-bold">
            نظام إدارة المبيعات الذكي v1.0
          </div>
          <h1 className="text-4xl md:text-5xl font-black text-white leading-tight">
            بروستد <span className="gold-gradient-text">البروست</span>
          </h1>
          <p className="text-gray-400 text-lg">
            قم باختيار حسابك أو إدخال رمز PIN الخاص بك مباشرة للوصول إلى لوحة المبيعات.
          </p>
        </div>

        {/* User Tiles Grid */}
        <div className="space-y-3">
          <h3 className="text-xs font-bold text-gray-500 flex items-center gap-1.5 justify-end">
            الموظفون المتاحون بالوردية
            <Users size={14} />
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {users.length > 0 ? (
              users.map((u) => (
                <div
                  key={u.id}
                  onClick={handleUserTileClick}
                  className="p-4 bg-brand-card hover:bg-brand-border/20 border border-brand-border/40 rounded-2xl cursor-pointer text-right transition-all hover:scale-[1.02] active:scale-[0.98] group"
                >
                  <span className="text-white font-bold block text-base group-hover:text-brand-gold transition-colors">
                    {u.display_name}
                  </span>
                  <span className="text-xs text-gray-400 mt-1 inline-block">
                    {u.role === "manager" ? "مدير النظام" : "كاشير صندوق"}
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
      <div className="w-full max-w-sm p-6 bg-brand-card border border-brand-border/60 rounded-3xl shadow-2xl flex flex-col items-center">
        <div className="h-16 w-16 rounded-full bg-brand-gold/10 text-brand-gold flex items-center justify-center mb-4">
          {loading ? (
            <Loader2 size={28} className="animate-spin" />
          ) : (
            <Lock size={28} className="animate-pulse" />
          )}
        </div>
        
        <h3 className="text-xl font-bold text-white mb-1">تسجيل الدخول للنظام</h3>
        <p className="text-gray-400 text-sm mb-6 text-center">أدخل رمز الـ PIN المكون من 4 أرقام</p>

        {/* PIN Dot indicators */}
        <div className="flex justify-center gap-3 mb-6">
          {[0, 1, 2, 3].map((idx) => (
            <div
              key={idx}
              className={`w-4 h-4 rounded-full border border-brand-gold/60 transition-colors ${
                pin.length > idx ? "bg-brand-gold" : "bg-transparent"
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
          onChange={(val) => {
            if (val.length <= 4) setPin(val);
          }}
          onConfirm={handleLoginSubmit}
          confirmLabel={loading ? "جاري التحقق..." : "تأكيد PIN"}
          confirmColor="bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold"
        />
      </div>

    </div>
  );
};
