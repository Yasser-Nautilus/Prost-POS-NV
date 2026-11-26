import React, { useState, useEffect } from "react";
import { Users, Plus, Edit3, UserX, RefreshCw, Loader2, X, Check, Shield } from "lucide-react";
import { bridge } from "../bridge";
import { useConfirm } from "../components/ConfirmDialog";
import { INVALID_PHONE_MSG, normalizeEgyptianMobile } from "../phone";

interface UsersViewProps {
  currentUser: any;
}

const ROLE_OPTIONS = [
  { value: "cashier",  label: "كاشير صندوق",          color: "text-brand-teal" },
  { value: "driver",   label: "طيار (مندوب توصيل)",   color: "text-purple-400" },
  { value: "manager",  label: "مدير المطعم",          color: "text-brand-red" },
  { value: "admin",    label: "مدير النظام",           color: "text-red-400" },
];

const ROLE_LABELS: Record<string, string> = {
  cashier: "كاشير",
  manager: "مدير المطعم",
  admin:   "مدير النظام",
  driver:  "طيار",
};

const ROLE_COLORS: Record<string, string> = {
  cashier: "text-brand-teal bg-brand-teal/10 border-brand-teal/30",
  manager: "text-brand-red bg-brand-red/10 border-brand-red/30",
  admin:   "text-red-400 bg-red-900/20 border-red-800/30",
  driver:  "text-purple-400 bg-purple-900/20 border-purple-800/30",
};

export const UsersView: React.FC<UsersViewProps> = ({ currentUser }) => {

  // Helper: detect driver (cashier role + no cashier_slot)
  const getRoleLabel = (user: any): string => {
    if (user.role === "cashier" && user.cashier_slot == null) return ROLE_LABELS.driver;
    return ROLE_LABELS[user.role] || user.role;
  };
  const getRoleColor = (user: any): string => {
    if (user.role === "cashier" && user.cashier_slot == null) return ROLE_COLORS.driver;
    return ROLE_COLORS[user.role] || ROLE_COLORS.cashier;
  };
  const { confirm: showConfirm, ConfirmUI } = useConfirm();

  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState<any | null>(null);

  // Form state
  const [formUsername, setFormUsername] = useState("");
  const [formDisplayName, setFormDisplayName] = useState("");
  const [formRole, setFormRole] = useState("cashier");
  const [formPin, setFormPin] = useState("");
  const [formSlot, setFormSlot] = useState<string>("");
  const [formPhone, setFormPhone] = useState("");
  const [phoneError, setPhoneError] = useState("");

  const isAdmin = currentUser?.role === "admin";

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await bridge.call("get_users_management");
      setUsers(res || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const openNewUser = () => {
    setEditingUser(null);
    setFormUsername("");
    setFormDisplayName("");
    setFormRole("cashier");
    setFormPin("");
    setFormSlot("");
    setFormPhone("");
    setPhoneError("");
    setShowForm(true);
  };

  const openEditUser = (user: any) => {
    setEditingUser(user);
    setFormUsername(user.username || "");
    setFormDisplayName(user.display_name || "");
    // Detect driver: backend stores as role=cashier + cashier_slot=null
    const isDriver = user.role === "cashier" && user.cashier_slot == null;
    setFormRole(isDriver ? "driver" : (user.role || "cashier"));
    setFormPin(""); // don't pre-fill PIN
    setFormSlot(user.cashier_slot != null ? user.cashier_slot.toString() : "");
    setFormPhone(user.phone || "");
    setPhoneError("");
    setShowForm(true);
  };

  const handleSaveUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // 'driver' is a UI-only concept: backend stores as role=cashier + cashier_slot=null
      const isDriver = formRole === "driver";
      const backendRole = isDriver ? "cashier" : formRole;

      // Drivers are not login users, but they must have a phone number.
      if (isDriver && !formPhone.trim()) {
        setPhoneError("رقم التليفون مطلوب للطيار");
        return;
      }
      let phoneToSave: string | undefined = undefined;
      if (formPhone.trim()) {
        const norm = normalizeEgyptianMobile(formPhone);
        if (!norm) {
          setPhoneError(INVALID_PHONE_MSG);
          return;
        }
        phoneToSave = norm;
      }

      if (editingUser) {
        await bridge.call("update_user", {
          user_id: editingUser.id,
          username: formUsername || undefined,
          display_name: formDisplayName || undefined,
          role: backendRole,
          pin: formPin || undefined,
          cashier_slot: isDriver ? null : (formSlot !== "" ? parseInt(formSlot) : -1),
          phone: phoneToSave,
        });
      } else {
        if (!formPin) {
          alert("رمز PIN مطلوب للمستخدم الجديد");
          return;
        }
        await bridge.call("create_user", {
          username: formUsername,
          display_name: formDisplayName,
          role: backendRole,
          pin: formPin,
          cashier_slot: isDriver ? null : (formSlot !== "" ? parseInt(formSlot) : null),
          phone: phoneToSave,
        });
      }
      setShowForm(false);
      fetchUsers();
    } catch (err: any) {
      alert("فشل حفظ المستخدم: " + err.message);
    }
  };

  const handleDeactivate = async (userId: number, userName: string) => {
    if (userId === currentUser?.id) {
      alert("لا يمكنك إلغاء تفعيل حسابك الخاص");
      return;
    }
    if (!(await showConfirm(`هل تريد إلغاء تفعيل المستخدم "${userName}"؟`))) return;
    try {
      await bridge.call("deactivate_user", { user_id: userId });
      fetchUsers();
    } catch (err: any) {
      alert("فشل إلغاء التفعيل: " + err.message);
    }
  };

  if (loading && users.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)] bg-brand-dark">
        <Loader2 className="animate-spin text-brand-red" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل المستخدمين...</p>
      </div>
    );
  }

  return (
    <>
    <div className="flex-1 overflow-y-auto p-6 space-y-6 h-[calc(100vh-64px)] bg-brand-dark">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-brand-red/10 text-brand-red flex items-center justify-center">
            <Users size={20} />
          </div>
          <div>
            <h2 className="text-xl font-black text-white">إدارة المستخدمين</h2>
            <p className="text-xs text-gray-400">
              {users.filter((u) => u.is_active).length} مستخدم نشط / {users.length} إجمالي
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <button
              onClick={openNewUser}
              className="py-2 px-4 bg-brand-red text-brand-dark hover:bg-opacity-90 rounded-xl text-sm font-bold flex items-center gap-1.5 transition-all"
            >
              <Plus size={16} />
              مستخدم جديد
            </button>
          )}
          <button
            onClick={fetchUsers}
            className="p-2 bg-brand-card border border-brand-border/40 hover:border-brand-red text-gray-400 hover:text-brand-red rounded-xl transition-all"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Users grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {users.map((user) => (
          <div
            key={user.id}
            className={`p-5 bg-brand-card border border-brand-border/40 rounded-2xl space-y-3 transition-all hover:border-brand-border/70 ${
              !user.is_active ? "opacity-50" : ""
            }`}
          >
            {/* Avatar / Role badge */}
            <div className="flex justify-between items-start">
              <div className="h-12 w-12 rounded-2xl bg-brand-surface flex items-center justify-center text-2xl font-black text-brand-red">
                {(user.display_name || user.username || "?")[0]?.toUpperCase()}
              </div>
              <span
                className={`py-1 px-2.5 rounded-lg border text-[10px] font-bold flex items-center gap-1 ${
                  getRoleColor(user)
                }`}
              >
                <Shield size={10} />
                {getRoleLabel(user)}
              </span>
            </div>

            {/* Name & username */}
            <div>
              <span className="text-white font-bold block">{user.display_name}</span>
              <span className="text-xs text-gray-400 font-mono block mt-0.5">
                @{user.username}
              </span>
              {user.phone && user.cashier_slot == null && (
                <span className="text-xs text-gray-400 font-mono block mt-0.5" dir="ltr">
                  {user.phone}
                </span>
              )}
              {user.cashier_slot != null && (
                <span className="text-xs text-gray-500 block mt-0.5">
                  كاشير صندوق #{user.cashier_slot}
                </span>
              )}
              {!user.is_active && (
                <span className="text-xs text-red-400 font-bold block mt-1">
                  غير نشط
                </span>
              )}
              {user.id === currentUser?.id && (
                <span className="text-xs text-brand-teal font-bold block mt-1">
                  (أنت)
                </span>
              )}
            </div>

            {/* Actions */}
            {isAdmin && user.id !== currentUser?.id && (
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => openEditUser(user)}
                  className="flex-1 py-1.5 text-xs font-bold text-brand-red border border-brand-red/30 bg-brand-red/5 hover:bg-brand-red/10 rounded-lg flex items-center justify-center gap-1.5 transition-all"
                >
                  <Edit3 size={12} />
                  تعديل
                </button>
                {user.is_active && (
                  <button
                    onClick={() => handleDeactivate(user.id, user.display_name)}
                    aria-label="تعطيل الحساب"
                    title="تعطيل الحساب"
                    className="py-1.5 px-3 text-xs font-bold text-red-400 border border-red-900/30 bg-red-950/20 hover:bg-red-950/40 rounded-lg flex items-center justify-center transition-all"
                  >
                    <UserX size={12} />
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* User Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}>
          <div className="w-full max-w-md mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="p-5 border-b border-brand-border/40 flex items-center justify-between">
              <h3 className="font-bold text-lg text-brand-red">
                {editingUser ? "تعديل المستخدم" : "مستخدم جديد"}
              </h3>
              <button
                onClick={() => setShowForm(false)}
                aria-label="إغلاق النموذج"
                title="إغلاق"
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSaveUser} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-gray-400 text-xs block mb-1">اسم المستخدم (username) *</label>
                  <input
                    type="text"
                    required={!editingUser}
                    value={formUsername}
                    onChange={(e) => setFormUsername(e.target.value)}
                    placeholder="cashier01"
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-brand-red font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="text-gray-400 text-xs block mb-1">الاسم الظاهر *</label>
                  <input
                    type="text"
                    required={!editingUser}
                    value={formDisplayName}
                    onChange={(e) => setFormDisplayName(e.target.value)}
                    placeholder="أحمد محمد"
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-brand-red text-right"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-gray-400 text-xs block mb-1">الصلاحية</label>
                  <select
                    value={formRole}
                    onChange={(e) => setFormRole(e.target.value)}
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-2.5 text-white focus:outline-none focus:border-brand-red"
                  >
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-gray-400 text-xs block mb-1">
                    رمز PIN {editingUser ? "(اتركه فارغاً للإبقاء)" : "*"}
                  </label>
                  <input
                    type="password"
                    required={!editingUser}
                    value={formPin}
                    onChange={(e) => setFormPin(e.target.value)}
                    placeholder="أرقام 0-9 فقط"
                    minLength={4}
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-brand-red font-mono text-center text-xl tracking-widest"
                  />
                  <p className="text-xs text-gray-400 mt-1">4 أرقام إنجليزية (0-9) على الأقل للرمز الجديد</p>
                </div>
              </div>

              {formRole !== "driver" && (
                <div>
                  <label className="text-gray-400 text-xs block mb-1">رقم الصندوق (cashier slot)</label>
                  <select
                    aria-label="رقم الصندوق"
                    value={formSlot}
                    onChange={(e) => setFormSlot(e.target.value)}
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-2.5 text-white focus:outline-none focus:border-brand-red text-center font-mono"
                  >
                    <option value="">بدون صندوق</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                  </select>
                </div>
              )}
              {formRole === "driver" && (
                <div>
                  <label className="text-gray-400 text-xs block mb-1">رقم التليفون *</label>
                  <input
                    type="tel"
                    required
                    inputMode="tel"
                    value={formPhone}
                    onChange={(e) => { setFormPhone(e.target.value.replace(/[^0-9+\s\-]/g, "")); setPhoneError(""); }}
                    placeholder="01xxxxxxxxx"
                    aria-label="رقم تليفون الطيار"
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-brand-red text-center font-mono"
                  />
                  {phoneError && <p className="text-red-400 text-xs mt-1" role="alert">{phoneError}</p>}
                </div>
              )}
              {formRole === "driver" && (
                <div className="py-2 px-3 bg-purple-900/20 border border-purple-800/30 rounded-xl text-purple-400 text-xs text-center">
                  الطيارون لا يملكون رقم صندوق — يُضافون تلقائياً لقائمة الطيارين
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="flex-1 py-3 bg-brand-card border border-brand-border/40 text-gray-300 rounded-xl font-bold"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="flex-1 py-3 bg-brand-red text-brand-dark hover:bg-opacity-90 rounded-xl font-bold flex items-center justify-center gap-2"
                >
                  <Check size={18} />
                  حفظ
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
    {ConfirmUI}
    </>
  );
};
