 import { useState, useEffect } from "react";
import { 
  ShoppingBag, Truck, BarChart3, LogOut, User, Calendar, 
  Loader2, Eye, Package, Users, Wallet, Shield, Clock, ChevronDown
} from "lucide-react";
import { LoginView } from "./views/LoginView";
import { POSView } from "./views/POSView";
import { DeliveryView } from "./views/DeliveryView";
import { ReportsView } from "./views/ReportsView";
import { TrackingView } from "./views/TrackingView";
import { ProductsView } from "./views/ProductsView";
import { UsersView } from "./views/UsersView";
import { DriverSettlementView } from "./views/DriverSettlementView";
import { AuditLogView } from "./views/AuditLogView";
import { SessionsView } from "./views/SessionsView";
import { ShiftDialog } from "./components/ShiftDialog";
import { bridge } from "./bridge";
import prostshP from "./assets/prostsh-p.png";

type Tab = "pos" | "delivery" | "tracking" | "reports" | "products" | "users" | "settlement" | "sessions" | "audit";

// ── Confirm Dialog (replaces window.confirm) ────────────────────────────────

const ConfirmDialog: React.FC<{
  isOpen: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ isOpen, message, onConfirm, onCancel }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-brand-surface border border-brand-border/60 rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-5" dir="rtl">
        <p className="text-white font-bold text-sm text-center">{message}</p>
        <div className="flex gap-3">
          <button
            onClick={onConfirm}
            className="flex-1 py-2.5 bg-gradient-to-l from-red-600 to-red-700 text-white font-bold rounded-xl hover:brightness-110 active:scale-[0.98] transition-all"
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

// ─────────────────────────────────────────────────────────────────────────────

function App() {
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<Tab>("pos");
  const [isShiftOpen, setIsShiftOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [activeShift, setActiveShift] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  // H17: native-bridge connection state — "blocked" means no native shell
  // and demo mode isn't enabled, so no transaction may be allowed to run.
  const [bridgeMode, setBridgeMode] = useState<"native" | "mock" | "blocked">("native");
  // CHANGED: pickup order handed to POS for payment on handover ("تسليم").
  const [handoverOrder, setHandoverOrder] = useState<any | null>(null);
  // White-label branding loaded from backend config
  const [brandName, setBrandName] = useState<string>("");
  // Confirm dialog state (replaces window.confirm)
  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    message: string;
    resolve: ((v: boolean) => void) | null;
  }>({ isOpen: false, message: "", resolve: null });

  const showConfirm = (message: string): Promise<boolean> => {
    return new Promise((resolve) => {
      setConfirmDialog({ isOpen: true, message, resolve });
    });
  };

  const checkAuth = async () => {
    try {
      // H17: resolve the native-bridge connection state before doing
      // anything else — a blocked bridge must never silently answer calls.
      const mode = await bridge.getConnectionMode();
      setBridgeMode(mode);
      if (mode === "blocked") {
        setLoading(false);
        return;
      }

      // Load config (white-label branding) on startup
      try {
        const cfg = await bridge.call("get_config");
        if (cfg?.restaurant_name_ar) setBrandName(cfg.restaurant_name_ar);
      } catch { /* fallback to default */ }

      const user = await bridge.call("get_current_user");
      setCurrentUser(user);
      if (user) {
        const shift = await bridge.call("get_active_shift");
        setActiveShift(shift);
      }
    } catch (e) {
      console.error("Auth check failed:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const handleLoginSuccess = async (user: any) => {
    setCurrentUser(user);
    const shift = await bridge.call("get_active_shift");
    setActiveShift(shift);
    setActiveTab("pos");
  };

  const handleLogout = async () => {
    const confirmed = await showConfirm("هل أنت متأكد من تسجيل الخروج؟");
    if (!confirmed) return;
    try {
      await bridge.call("logout");
      setCurrentUser(null);
      setActiveShift(null);
    } catch (e) {
      console.error(e);
    }
  };

  const handleShiftChange = async () => {
    const shift = await bridge.call("get_active_shift");
    setActiveShift(shift);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-brand-dark flex flex-col items-center justify-center text-white space-y-4">
        <Loader2 className="animate-spin text-brand-red" size={48} />
        <p className="text-gray-400 font-medium">جاري تحميل نظام البيع...</p>
      </div>
    );
  }

  if (bridgeMode === "blocked") {
    // H17: no native shell and demo mode is off — block everything rather
    // than let the cashier believe a payment went through with no system
    // actually behind it.
    return (
      <div className="min-h-screen bg-brand-dark flex flex-col items-center justify-center text-white space-y-4 px-6 text-center" dir="rtl">
        <Shield className="text-red-500" size={48} />
        <h1 className="text-xl font-bold">تعذر الاتصال بنظام التشغيل الأساسي</h1>
        <p className="text-gray-400 max-w-md">
          لا يمكن معالجة أي عملية بيع أو دفع بدون هذا الاتصال. أعد تشغيل البرنامج،
          وإذا استمرت المشكلة اتصل بالدعم الفني.
        </p>
      </div>
    );
  }

  const demoModeBanner = bridgeMode === "mock" && (
    <div className="h-7 bg-amber-500 text-black text-xs font-bold flex items-center justify-center shrink-0 z-30">
      ⚠️ وضع تجريبي (Demo) — لا يوجد اتصال حقيقي بالنظام، البيانات غير حقيقية
    </div>
  );

  if (!currentUser) {
    return (
      <>
        {demoModeBanner}
        <LoginView onLoginSuccess={handleLoginSuccess} />
      </>
    );
  }

  const isManagerOrAbove =
    currentUser.role === "manager" || currentUser.role === "admin";
  const isAdmin = currentUser.role === "admin";

  // Navigation items — visible tabs depend on role
  const navItems: { id: Tab; label: string; icon: any; visible: boolean }[] = [
    { id: "pos",        label: "شاشة البيع (POS)",    icon: ShoppingBag, visible: true },
    { id: "delivery",  label: "توصيل الطلبات",       icon: Truck,       visible: true },
    { id: "tracking",  label: "متابعة الطلبات",      icon: Eye,         visible: true },
    // Cashier sees exactly four screens: sell, deliver, track, settle drivers.
    { id: "settlement",label: "تسوية السائقين",      icon: Wallet,      visible: true },
    { id: "sessions",  label: "ورديات الصندوق",      icon: Clock,       visible: isManagerOrAbove },
    { id: "reports",   label: "التقارير المالية",    icon: BarChart3,   visible: isManagerOrAbove },
    { id: "products",  label: "إدارة المنتجات",      icon: Package,     visible: isManagerOrAbove },
    { id: "audit",     label: "سجل التدقيق",         icon: Shield,      visible: isManagerOrAbove },
    { id: "users",     label: "إدارة المستخدمين",    icon: Users,       visible: isAdmin },
  ];

  // Derive brand display — first word as icon, rest as highlight
  const brandParts = brandName ? brandName.split(" ") : [];
  const brandFirst = brandParts[0] || "بروستش";
  const brandRest = brandParts.slice(1).join(" ") || "Prostsh";

  return (
    <div className="h-screen bg-brand-dark flex flex-col overflow-hidden text-white font-cairo">
      {demoModeBanner}

      {/* Top Premium Navbar Header */}
      <header className="h-16 bg-brand-surface border-b border-brand-border/60 flex items-center justify-between px-6 z-20">

        {/* Right side: Logo & Navigation */}
        <div className="flex items-center gap-6">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <img src={prostshP} alt={brandFirst} className="h-9 w-auto drop-shadow" />
            <span className="font-extrabold text-lg text-white">
              {brandFirst} <span className="red-gradient-text">{brandRest}</span>
            </span>
          </div>

          {/* Navigation links */}
          <nav className="hidden md:flex items-center gap-1">
            {navItems
              .filter((n) => n.visible)
              .map((n) => {
                const Icon = n.icon;
                return (
                  <button
                    key={n.id}
                    onClick={() => setActiveTab(n.id)}
                    title={n.label}
                    aria-label={n.label}
                    className={`group flex items-center py-2 ${activeTab === n.id ? "px-3" : "px-2.5 xl:px-3"} rounded-xl text-sm font-bold whitespace-nowrap transition-all ${
                      activeTab === n.id
                        ? "bg-brand-red/10 text-brand-red border border-brand-red/30"
                        : "text-gray-400 hover:text-white hover:bg-brand-card/40 border border-transparent"
                    }`}
                  >
                    <Icon size={16} className="shrink-0" />
                    {/* Crowded bar: the active tab keeps its label; the others
                        slide their name in on hover (always visible on wide screens). */}
                    <span
                      className={
                        activeTab === n.id
                          ? "ms-2"
                          : "overflow-hidden whitespace-nowrap max-w-0 opacity-0 ms-0 -translate-x-2 transition-all duration-300 ease-out group-hover:max-w-[14rem] group-hover:opacity-100 group-hover:ms-2 group-hover:translate-x-0 group-focus-visible:max-w-[14rem] group-focus-visible:opacity-100 group-focus-visible:ms-2 group-focus-visible:translate-x-0 2xl:max-w-[14rem] 2xl:opacity-100 2xl:ms-2 2xl:translate-x-0"
                      }
                    >
                      {n.label}
                    </span>
                  </button>
                );
              })}
          </nav>
        </div>

        {/* Left side: Shift & Cashier Profiler */}
        <div className="flex items-center gap-3">
          {/* Shift indicator */}
          <button
            onClick={() => setIsShiftOpen(true)}
            className={`py-1.5 px-3 rounded-xl border text-xs font-semibold flex items-center gap-1.5 active:scale-95 transition-all ${
              activeShift
                ? "bg-brand-teal/10 border-brand-teal/30 text-brand-teal"
                : "bg-red-950/20 border-red-900/30 text-red-400"
            }`}
          >
            <Calendar size={14} />
            <span>{activeShift ? "الوردية مفتوحة" : "الوردية مغلقة"}</span>
          </button>

          {/* User menu: name, role and logout live in one compact button */}
          <div className="relative">
            <button
              onClick={() => setIsUserMenuOpen((v) => !v)}
              aria-label="قائمة المستخدم"
              aria-expanded={isUserMenuOpen}
              title={currentUser.display_name}
              className="flex items-center gap-1.5 bg-brand-card/80 py-1.5 px-2 rounded-xl border border-brand-border/40 hover:border-brand-red/40 active:scale-95 transition-all"
            >
              <div className="h-6 w-6 rounded-full bg-brand-red/20 text-brand-red flex items-center justify-center">
                <User size={14} />
              </div>
              <ChevronDown size={12} className="text-gray-400" />
            </button>
            {isUserMenuOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setIsUserMenuOpen(false)} />
                <div className="absolute left-0 top-full mt-2 z-40 w-52 bg-brand-surface border border-brand-border/60 rounded-2xl shadow-2xl p-3 space-y-2" dir="rtl">
                  <div className="text-right px-1">
                    <span className="text-sm font-bold text-white block leading-tight">{currentUser.display_name}</span>
                    <span className="text-[11px] text-gray-400 block mt-0.5">
                      {currentUser.role === "admin" ? "مدير النظام" : currentUser.role === "manager" ? "مدير المطعم" : "كاشير الصندوق"}
                    </span>
                  </div>
                  <button
                    onClick={() => { setIsUserMenuOpen(false); handleLogout(); }}
                    className="w-full flex items-center justify-center gap-2 py-2 bg-brand-card/80 hover:bg-red-950/20 text-gray-300 hover:text-red-400 border border-brand-border/40 hover:border-red-900/40 rounded-xl text-sm font-bold active:scale-95 transition-all"
                  >
                    <LogOut size={14} />
                    تسجيل الخروج
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

      </header>

      {/* Main View Display — POSView always mounted to preserve state */}
      <main className="flex-1 overflow-hidden">
        <div className={activeTab === "pos" ? "flex flex-col h-full" : "hidden"}>
          <POSView
            currentUser={currentUser}
            handoverOrder={handoverOrder}
            onHandoverConsumed={() => setHandoverOrder(null)}
            isActive={activeTab === "pos"}
          />
        </div>
        {activeTab === "delivery" && <DeliveryView currentUser={currentUser} />}
        {activeTab === "tracking" && (
          <TrackingView
            currentUser={currentUser}
            onResumeOrder={(_order) => setActiveTab("pos")}
            // CHANGED: handover a pickup order — load it, switch to POS, open payment.
            onHandoverOrder={async (order) => {
              await bridge.call("load_order", { order_id: order.id });
              setActiveTab("pos");
              setHandoverOrder(order);
            }}
          />
        )}
        {activeTab === "reports"    && isManagerOrAbove && <ReportsView key={activeShift?.id ?? "closed"} currentUser={currentUser} />}
        {activeTab === "products"   && isManagerOrAbove && <ProductsView currentUser={currentUser} />}
        {activeTab === "settlement" && <DriverSettlementView currentUser={currentUser} />}
        {activeTab === "sessions"   && isManagerOrAbove && <SessionsView currentUser={currentUser} />}
        {activeTab === "audit"      && isManagerOrAbove && <AuditLogView currentUser={currentUser} />}
        {activeTab === "users"      && isAdmin           && <UsersView currentUser={currentUser} />}
      </main>

      {/* Global Dialogs */}
      <ShiftDialog
        isOpen={isShiftOpen}
        onClose={() => setIsShiftOpen(false)}
        currentUser={currentUser}
        onShiftStatusChange={handleShiftChange}
      />
      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        message={confirmDialog.message}
        onConfirm={() => {
          confirmDialog.resolve?.(true);
          setConfirmDialog({ isOpen: false, message: "", resolve: null });
        }}
        onCancel={() => {
          confirmDialog.resolve?.(false);
          setConfirmDialog({ isOpen: false, message: "", resolve: null });
        }}
      />

    </div>
  );
}

export default App;
