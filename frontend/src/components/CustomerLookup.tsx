import React, { useState, useEffect, useRef } from "react";
import { X, Search, Plus, UserPlus, MapPin, Check, Pencil } from "lucide-react";
import { bridge } from "../bridge";
import { INVALID_PHONE_MSG, looksLikePhone, normalizeEgyptianMobile } from "../phone";

interface CustomerLookupProps {
  isOpen: boolean;
  orderType?: string;
  onClose: () => void;
  onSelect: (customer: any, selectedAddress: any) => void;
}

export const CustomerLookup: React.FC<CustomerLookupProps> = ({
  isOpen,
  orderType,
  onClose,
  onSelect
}) => {
  const isPickup = orderType === "pickup";
  const [phone, setPhone] = useState("");
  const [customer, setCustomer] = useState<any>(null);
  const [searched, setSearched] = useState(false);
  const [phoneError, setPhoneError] = useState("");
  const [matches, setMatches] = useState<any[]>([]);
  const phoneInputRef = useRef<HTMLInputElement>(null);
  const lastLookupRef = useRef("");
  const [recentOrders, setRecentOrders] = useState<any[]>([]);

  // Manager-only customer editing
  const [canEdit, setCanEdit] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editError, setEditError] = useState("");

  // Registration states
  const [isRegistering, setIsRegistering] = useState(false);
  const [regName, setRegName] = useState("");

  // Address states
  const [isAddingAddress, setIsAddingAddress] = useState(false);
  const [street, setStreet] = useState("");
  const [zones, setZones] = useState<any[]>([]);
  const [selectedZoneId, setSelectedZoneId] = useState<string>("");

  useEffect(() => {
    if (isOpen) {
      // CHANGED: reset the lookup every time the dialog opens, so a previous
      // order's phone/customer/forms don't linger when it's reopened.
      setPhone("");
      setPhoneError("");
      setMatches([]);
      setIsEditing(false);
      setEditError("");
      setCustomer(null);
      setSearched(false);
      // Focus the phone field so the cashier can type immediately
      setTimeout(() => phoneInputRef.current?.focus(), 50);
      bridge.call("get_current_user")
        .then((u: any) => setCanEdit(!!u && (u.role === "manager" || u.role === "admin")))
        .catch(() => setCanEdit(false));
      setIsRegistering(false);
      setRegName("");
      setIsAddingAddress(false);
      setStreet("");

      // Load active delivery zones
      bridge.call("get_active_zones")
        .then((res) => {
          setZones(res || []);
          if (res && res.length > 0) {
            setSelectedZoneId(res[0].id.toString());
          }
        })
        .catch(console.error);
    }
  }, [isOpen]);

  // Repeat customers: a complete valid phone number is looked up on its own,
  // no need to press the search button.
  useEffect(() => {
    if (!isOpen) { lastLookupRef.current = ""; return; }
    const normalized = looksLikePhone(phone.trim()) ? normalizeEgyptianMobile(phone.trim()) : null;
    if (!normalized || lastLookupRef.current === normalized) return;
    const timer = setTimeout(() => {
      lastLookupRef.current = normalized;
      handleSearch();
    }, 250);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phone, isOpen]);

  // Last 3 orders of the customer on screen
  useEffect(() => {
    setRecentOrders([]);
    if (!isOpen || !customer?.id) return;
    let cancelled = false;
    bridge.call("get_customer_history", { customer_id: customer.id, limit: 3 })
      .then((rows: any[]) => { if (!cancelled) setRecentOrders(rows || []); })
      .catch(() => { if (!cancelled) setRecentOrders([]); });
    return () => { cancelled = true; };
  }, [isOpen, customer?.id]);

  if (!isOpen) return null;

  const handleSearch = async () => {
    const text = phone.trim();
    if (!text) return;
    setPhoneError("");
    setMatches([]);
    setIsEditing(false);
    // Letters in the box mean the cashier is searching by name
    if (!looksLikePhone(text)) {
      try {
        const res = await bridge.call("search_customers", { query: text });
        setCustomer(null);
        setMatches(res || []);
        setSearched(false);
        if (!res || res.length === 0) setPhoneError("لا يوجد عميل بهذا الاسم. للبحث برقم الهاتف اكتب الأرقام فقط.");
      } catch (e: any) {
        setPhoneError(e?.message || "تعذر البحث");
      }
      return;
    }
    const normalized = normalizeEgyptianMobile(text);
    if (!normalized) {
      setCustomer(null);
      setSearched(false);
      setPhoneError(INVALID_PHONE_MSG);
      return;
    }
    setPhone(normalized);
    try {
      const res = await bridge.call("find_customer_by_phone", { phone: normalized });
      setCustomer(res || null);
      setSearched(true);
      setIsRegistering(false);
      setIsAddingAddress(false);
    } catch (e: any) {
      console.error(e);
      setCustomer(null);
      setSearched(false);
      setPhoneError(e?.message || INVALID_PHONE_MSG);
    }
  };

  const pickMatch = (c: any) => {
    setMatches([]);
    setPhone(c.phone);
    setCustomer(c);
    setSearched(true);
    setIsRegistering(false);
    setIsAddingAddress(false);
  };

  const startEdit = () => {
    setEditName(customer?.name || "");
    setEditPhone(customer?.phone || "");
    setEditError("");
    setIsEditing(true);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customer) return;
    if (!editName.trim()) { setEditError("اسم العميل مطلوب"); return; }
    const normalized = normalizeEgyptianMobile(editPhone);
    if (!normalized) { setEditError(INVALID_PHONE_MSG); return; }
    try {
      const res = await bridge.call("update_customer", {
        customer_id: customer.id,
        name: editName.trim(),
        phone: normalized,
      });
      setCustomer(res);
      setPhone(res.phone);
      setIsEditing(false);
    } catch (err: any) {
      setEditError(err?.message || "فشل حفظ التعديل");
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regName || !phone) return;
    const normalizedPhone = normalizeEgyptianMobile(phone);
    if (!normalizedPhone) { setPhoneError(INVALID_PHONE_MSG); return; }
    try {
      // create_customer only takes name + phone (no notes field in Customer model)
      const res = await bridge.call("create_customer", {
        name: regName,
        phone: normalizedPhone,
      });
      setCustomer(res);
      setIsRegistering(false);
      if (isPickup) {
        onSelect(res, {
          street_name: "استلام محل",
          zone_name: "",
          delivery_fee: 0,
        });
        return;
      }
      // Auto open add address
      setIsAddingAddress(true);
    } catch (err: any) {
      alert("فشل التسجيل: " + err.message);
    }
  };

  const handleAddAddress = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!street || !selectedZoneId || !customer) return;
    try {
      const res = await bridge.call("add_customer_address", {
        customer_id: customer.id,
        street_name: street,
        zone_id: parseInt(selectedZoneId)
      });
      
      // Update local customer addresses
      const updatedCustomer = { ...customer };
      updatedCustomer.addresses = [...(updatedCustomer.addresses || []), res];
      setCustomer(updatedCustomer);
      
      setStreet("");
      setIsAddingAddress(false);
    } catch (err: any) {
      alert("فشل إضافة العنوان: " + err.message);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md"
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-2xl mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
        
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-brand-border/60 bg-brand-card">
          <h3 className="font-bold text-lg text-brand-red">{isPickup ? "البحث عن عميل (استلام محل)" : "البحث عن عميل الدليفري"}</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          
          {/* Search bar */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                ref={phoneInputRef}
                autoFocus
                type="text"
                inputMode="tel"
                placeholder="أدخل رقم الموبايل..."
                value={phone}
                onChange={(e) => { setPhone(e.target.value); setPhoneError(""); }}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="w-full bg-brand-card border border-brand-border/60 rounded-xl py-3 pl-11 pr-4 text-white placeholder-gray-500 focus:outline-none focus:border-brand-red text-left font-mono text-lg"
              />
              <Search className="absolute left-3 top-3.5 text-gray-500 pointer-events-none" size={20} />
            </div>
            <button
              onClick={handleSearch}
              className="py-3 px-6 bg-brand-red text-brand-dark hover:bg-opacity-90 font-bold rounded-xl active:translate-y-0.5 btn-hover-active"
            >
              بحث
            </button>
          </div>

          {phoneError && (
            <p className="text-red-400 text-sm -mt-3" role="alert">{phoneError}</p>
          )}

          {matches.length > 0 && (
            <div className="grid grid-cols-1 gap-2">
              {matches.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => pickMatch(m)}
                  className="p-3 bg-brand-card hover:bg-brand-border/20 border border-brand-border/40 rounded-xl flex justify-between items-center text-right"
                >
                  <span className="text-white font-medium">{m.name}</span>
                  <span className="text-gray-400 font-mono text-sm">{m.phone}</span>
                </button>
              ))}
            </div>
          )}

          {/* Search Results */}
          {searched && (
            <div className="space-y-4">
              {customer ? (
                <div className="bg-brand-card/40 border border-brand-border/40 rounded-2xl p-5 space-y-4">
                  <div className="flex justify-between items-start gap-4">
                    <div>
                      <h4 className="text-xl font-bold text-white">{customer.name}</h4>
                      <p className="text-gray-400 font-mono text-sm mt-1">{customer.phone}</p>
                      {customer.notes && (
                        <p className="text-yellow-600/90 text-sm mt-1">ملاحظات: {customer.notes}</p>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      {isPickup && (
                        <button
                          onClick={() => onSelect(customer, {
                            street_name: "استلام محل",
                            zone_name: "",
                            delivery_fee: 0,
                          })}
                          className="py-2 px-4 bg-brand-red text-brand-dark hover:bg-opacity-90 rounded-xl font-bold text-sm flex items-center gap-1.5 active:translate-y-0.5 btn-hover-active shadow-md"
                        >
                          <Check size={16} />
                          اختيار لاستلام المحل
                        </button>
                      )}
                      {canEdit && !isEditing && (
                        <button
                          onClick={startEdit}
                          className="py-2 px-3 bg-brand-border/30 hover:bg-brand-border/60 text-gray-300 rounded-lg font-semibold text-xs flex items-center gap-1 active:translate-y-0.5"
                        >
                          <Pencil size={14} />
                          تعديل
                        </button>
                      )}
                      {!isAddingAddress && (
                      <button
                        onClick={() => setIsAddingAddress(true)}
                        className="py-2 px-3 bg-brand-border/30 hover:bg-brand-border/60 text-brand-red rounded-lg font-semibold text-xs flex items-center gap-1 active:translate-y-0.5 btn-hover-active"
                      >
                        <Plus size={14} />
                        إضافة عنوان جديد
                      </button>
                    )}
                    </div>
                  </div>

                  {isEditing && (
                    <form onSubmit={handleSaveEdit} className="bg-brand-card/80 p-4 rounded-xl border border-brand-border/65 space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-gray-400 text-xs block mb-1">اسم العميل</label>
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => { setEditName(e.target.value); setEditError(""); }}
                            className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-red"
                          />
                        </div>
                        <div>
                          <label className="text-gray-400 text-xs block mb-1">رقم الموبايل</label>
                          <input
                            type="text"
                            inputMode="tel"
                            value={editPhone}
                            onChange={(e) => { setEditPhone(e.target.value); setEditError(""); }}
                            className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white text-left font-mono focus:outline-none focus:border-brand-red"
                          />
                        </div>
                      </div>
                      {editError && <p className="text-red-400 text-sm" role="alert">{editError}</p>}
                      <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => setIsEditing(false)} className="py-1.5 px-4 text-gray-400 hover:text-white rounded-lg font-bold text-sm">إلغاء</button>
                        <button type="submit" className="py-1.5 px-4 bg-brand-red text-brand-dark rounded-lg font-bold text-sm">حفظ التعديل</button>
                      </div>
                    </form>
                  )}

                  {/* Add Address Form */}
                  {isAddingAddress && (
                    <form onSubmit={handleAddAddress} className="bg-brand-card/80 p-4 rounded-xl border border-brand-border/65 space-y-4 animate-in slide-in-from-top-2 duration-150">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-gray-400 text-xs block mb-1">المنطقة (لتحديد خدمة التوصيل)</label>
                          <select
                            value={selectedZoneId}
                            onChange={(e) => setSelectedZoneId(e.target.value)}
                            className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-red"
                          >
                            {zones.map((z) => (
                              <option key={z.id} value={z.id}>
                                {z.name} ({z.delivery_fee} ج.م)
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="text-gray-400 text-xs block mb-1">الشارع والوصف التفصيلي</label>
                          <input
                            type="text"
                            required
                            placeholder="اسم الشارع، العمارة، الشقة..."
                            value={street}
                            onChange={(e) => setStreet(e.target.value)}
                            className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-red"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setIsAddingAddress(false)}
                          className="py-1.5 px-4 bg-transparent text-gray-400 hover:text-white rounded-lg font-bold text-sm"
                        >
                          إلغاء
                        </button>
                        <button
                          type="submit"
                          className="py-1.5 px-4 bg-brand-red text-brand-dark hover:bg-opacity-90 rounded-lg font-bold text-sm"
                        >
                          حفظ العنوان
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Addresses List */}
                  <div>
                    <h5 className="text-sm font-semibold text-gray-400 mb-2 flex items-center gap-1.5">
                      <MapPin size={14} />
                      العناوين المسجلة:
                    </h5>
                    {customer.addresses && customer.addresses.length > 0 ? (
                      <div className="grid grid-cols-1 gap-2">
                        {customer.addresses.map((addr: any) => (
                          <div
                            key={addr.id}
                            onClick={() => onSelect(customer, addr)}
                            className="p-3 bg-brand-card hover:bg-brand-border/20 border border-brand-border/40 rounded-xl cursor-pointer flex justify-between items-center transition-all group"
                          >
                            <div>
                              <span className="text-white font-medium block">{addr.street_name}</span>
                              <span className="text-xs text-brand-red mt-1 inline-block">
                                منطقة: {addr.zone_name} | خدمة التوصيل: {addr.delivery_fee} ج.م
                              </span>
                            </div>
                            <button className="h-8 w-8 rounded-full bg-brand-teal/10 text-brand-teal flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                              <Check size={16} />
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-gray-500 text-sm italic">لا توجد عناوين مسجلة للعميل. يرجى إضافة عنوان.</p>
                    )}
                  </div>

                  {/* Last orders */}
                  <div>
                    <h5 className="text-sm font-semibold text-gray-400 mb-2">آخر الطلبات:</h5>
                    {recentOrders.length > 0 ? (
                      <div className="grid grid-cols-1 gap-2" data-testid="recent-orders">
                        {recentOrders.map((o: any) => (
                          <div key={o.id} className="p-3 bg-brand-card/60 border border-brand-border/30 rounded-xl flex justify-between items-center text-sm">
                            <span className="text-white font-bold">{Number(o.total || 0).toFixed(2)} ج.م</span>
                            <span className="text-gray-400 text-xs">{o.status === "cancelled" ? "ملغي" : o.is_paid ? "مدفوع" : "غير مدفوع"}</span>
                            <span className="text-gray-400 font-mono text-xs">{String(o.created_at || "").slice(0, 16).replace("T", " ")}</span>
                            <span className="text-brand-red font-mono">#{o.invoice_no}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-gray-500 text-sm italic">لا توجد طلبات سابقة.</p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center py-6 bg-brand-card/20 rounded-2xl border border-brand-border/30">
                  <p className="text-gray-400 mb-4">هذا الرقم غير مسجل في النظام.</p>
                  {!isRegistering ? (
                    <button
                      onClick={() => setIsRegistering(true)}
                      className="py-2.5 px-5 bg-brand-red text-brand-dark hover:bg-opacity-90 font-bold rounded-xl flex items-center gap-2 mx-auto active:translate-y-0.5 btn-hover-active"
                    >
                      <UserPlus size={18} />
                      تسجيل عميل جديد بالرقم {phone}
                    </button>
                  ) : (
                    <form onSubmit={handleRegister} className="max-w-md mx-auto p-4 bg-brand-card rounded-xl border border-brand-border/60 text-right space-y-4 animate-in slide-in-from-top-2 duration-150">
                      <div>
                        <label className="text-gray-400 text-xs block mb-1">اسم العميل</label>
                        <input
                          type="text"
                          required
                          placeholder="الاسم الكامل للعميل..."
                          value={regName}
                          onChange={(e) => setRegName(e.target.value)}
                          className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-red"
                        />
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setIsRegistering(false)}
                          className="py-1.5 px-4 bg-transparent text-gray-400 hover:text-white rounded-lg font-bold text-sm"
                        >
                          إلغاء
                        </button>
                        <button
                          type="submit"
                          className="py-1.5 px-4 bg-brand-red text-brand-dark hover:bg-opacity-90 rounded-lg font-bold text-sm"
                        >
                          حفظ وتسجيل العميل
                        </button>
                      </div>
                    </form>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
};
