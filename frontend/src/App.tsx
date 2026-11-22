 import { useState, useEffect } from "react";
import { 
  ShoppingBag, Truck, BarChart3, LogOut, User, Calendar, 
  Loader2, Eye, Package, Users, Wallet, Shield
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
import { ShiftDialog } from "./components/ShiftDialog";
import { bridge } from "./bridge";
import prostshP from "./assets/prostsh-p.png";

type Tab = "pos" | "delivery" | "tracking" | "reports" | "products" | "users" | "settlement" | "audit";

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
  const [activeShift, setActiveShift] = useState<any>(null);
  const [loading, setLoading] = useState(true);
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

  if (!currentUser) {
    return <LoginView onLoginSuccess={handleLoginSuccess} />;
  }

  const isManagerOrAbove =
    currentUser.role === "manager" || currentUser.role === "admin";
  const isAdmin = currentUser.role === "admin";

  // Navigation items — visible tabs depend on role
  const navItems: { id: Tab; label: string; icon: any; visible: boolean }[] = [
    { id: "pos",        label: "شاشة البيع (POS)",    icon: ShoppingBag, visible: true },
    { id: "delivery",  label: "توصيل الطلبات",       icon: Truck,       visible: true },
    { id: "tracking",  label: "متابعة الطلبات",      icon: Eye,         visible: true },
    { id: "settlement",label: "تسوية السائقين",      icon: Wallet,      visible: isManagerOrAbove },
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
          <nav className="hidden md:flex items-center gap-1.5">
            {navItems
              .filter((n) => n.visible)
              .map((n) => {
                const Icon = n.icon;
                return (
                  <button
                    key={n.id}
                    onClick={() => setActiveTab(n.id)}
                    className={`flex items-center gap-2 py-2 px-4 rounded-xl text-sm font-bold transition-all ${
                      activeTab === n.id
                        ? "bg-brand-red/10 text-brand-red border border-brand-red/30"
                        : "text-gray-400 hover:text-white hover:bg-brand-card/40 border border-transparent"
                    }`}
                  >
                    <Icon size={16} />
                    {n.label}
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

          {/* User profile */}
          <div className="flex items-center gap-2 bg-brand-card/80 py-1.5 px-3 rounded-xl border border-brand-border/40">
            <div className="h-6 w-6 rounded-full bg-brand-red/20 text-brand-red flex items-center justify-center">
              <User size={14} />
            </div>
            <div className="text-right">
              <span className="text-xs font-bold text-white block leading-none">{currentUser.display_name}</span>
              <span className="text-[9px] text-gray-400 block mt-0.5 leading-none">
                {currentUser.role === "admin" ? "مدير النظام" : currentUser.role === "manager" ? "مدير المطعم" : "كاشير الصندوق"}
              </span>
            </div>
          </div>

          {/* Logout */}
          <button
            onClick={handleLogout}
            className="p-2 bg-brand-card/80 hover:bg-red-950/20 text-gray-400 hover:text-red-400 border border-brand-border/40 hover:border-red-900/40 rounded-xl active:scale-95 transition-all"
            title="تسجيل الخروج"
          >
            <LogOut size={16} />
          </button>
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
        {activeTab === "settlement" && isManagerOrAbove && <DriverSettlementView currentUser={currentUser} />}
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
