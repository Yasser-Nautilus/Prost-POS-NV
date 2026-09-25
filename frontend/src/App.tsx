import { useState, useEffect } from "react";
import { 
  ShoppingBag, Truck, BarChart3, LogOut, User, Calendar, 
  Loader2, Eye, Package, Users
} from "lucide-react";
import { LoginView } from "./views/LoginView";
import { POSView } from "./views/POSView";
import { DeliveryView } from "./views/DeliveryView";
import { ReportsView } from "./views/ReportsView";
import { TrackingView } from "./views/TrackingView";
import { ProductsView } from "./views/ProductsView";
import { UsersView } from "./views/UsersView";
import { ShiftDialog } from "./components/ShiftDialog";
import { bridge } from "./bridge";

type Tab = "pos" | "delivery" | "tracking" | "reports" | "products" | "users";

function App() {
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<Tab>("pos");
  const [isShiftOpen, setIsShiftOpen] = useState(false);
  const [activeShift, setActiveShift] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = async () => {
    try {
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
    if (!window.confirm("هل أنت متأكد من تسجيل الخروج؟")) return;
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
        <Loader2 className="animate-spin text-brand-gold" size={48} />
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
    { id: "pos",      label: "شاشة البيع (POS)",    icon: ShoppingBag, visible: true },
    { id: "delivery", label: "توصيل الطلبات",       icon: Truck,       visible: true },
    { id: "tracking", label: "متابعة الطلبات",      icon: Eye,         visible: true },
    { id: "reports",  label: "التقارير المالية",    icon: BarChart3,   visible: isManagerOrAbove },
    { id: "products", label: "إدارة المنتجات",      icon: Package,     visible: isManagerOrAbove },
    { id: "users",    label: "إدارة المستخدمين",    icon: Users,       visible: isAdmin },
  ];

  return (
    <div className="min-h-screen bg-brand-dark flex flex-col overflow-hidden text-white font-cairo">
      
      {/* Top Premium Navbar Header */}
      <header className="h-16 bg-brand-surface border-b border-brand-border/60 flex items-center justify-between px-6 z-20">
        
        {/* Right side: Logo & Navigation */}
        <div className="flex items-center gap-6">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-brand-gold to-yellow-500 flex items-center justify-center text-brand-dark font-black text-lg shadow-lg">
              ب
            </div>
            <span className="font-extrabold text-lg text-white">
              بروستد <span className="gold-gradient-text">البروست</span>
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
                        ? "bg-brand-gold/10 text-brand-gold border border-brand-gold/30"
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
            <div className="h-6 w-6 rounded-full bg-brand-gold/20 text-brand-gold flex items-center justify-center">
              <User size={14} />
            </div>
            <div className="text-right">
              <span className="text-xs font-bold text-white block leading-none">{currentUser.display_name}</span>
              <span className="text-[9px] text-gray-400 block mt-0.5 leading-none">
                {currentUser.role === "admin" ? "مدير عام" : currentUser.role === "manager" ? "مدير الوردية" : "كاشير الصندوق"}
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

      {/* Main View Display */}
      <main className="flex-1 overflow-hidden">
        {activeTab === "pos"      && <POSView currentUser={currentUser} />}
        {activeTab === "delivery" && <DeliveryView currentUser={currentUser} />}
        {activeTab === "tracking" && <TrackingView currentUser={currentUser} />}
        {activeTab === "reports"  && isManagerOrAbove && <ReportsView currentUser={currentUser} />}
        {activeTab === "products" && isManagerOrAbove && <ProductsView currentUser={currentUser} />}
        {activeTab === "users"    && isAdmin           && <UsersView currentUser={currentUser} />}
      </main>

      {/* Global Dialogs */}
      <ShiftDialog
        isOpen={isShiftOpen}
        onClose={() => setIsShiftOpen(false)}
        currentUser={currentUser}
        onShiftStatusChange={handleShiftChange}
      />

    </div>
  );
}

export default App;
