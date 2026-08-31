import React, { useState, useEffect } from "react";
import { X, Search, Plus, UserPlus, MapPin, Check } from "lucide-react";
import { bridge } from "../bridge";

interface CustomerLookupProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (customer: any, selectedAddress: any) => void;
}

export const CustomerLookup: React.FC<CustomerLookupProps> = ({
  isOpen,
  onClose,
  onSelect
}) => {
  const [phone, setPhone] = useState("");
  const [customer, setCustomer] = useState<any>(null);
  const [searched, setSearched] = useState(false);

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

  if (!isOpen) return null;

  const handleSearch = async () => {
    if (!phone) return;
    try {
      const res = await bridge.call("find_customer_by_phone", { phone });
      setCustomer(res || null);
      setSearched(true);
      setIsRegistering(false);
      setIsAddingAddress(false);
    } catch (e) {
      console.error(e);
      setCustomer(null);
      setSearched(true);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regName || !phone) return;
    try {
      // create_customer only takes name + phone (no notes field in Customer model)
      const res = await bridge.call("create_customer", {
        name: regName,
        phone: phone,
      });
      setCustomer(res);
      setIsRegistering(false);
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
      <div className="w-full max-w-2xl mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
        
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-brand-border/60 bg-brand-card">
          <h3 className="font-bold text-lg text-brand-gold">البحث عن عميل الدليفري</h3>
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
                type="text"
                placeholder="أدخل رقم الموبايل..."
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="w-full bg-brand-card border border-brand-border/60 rounded-xl py-3 px-4 text-white placeholder-gray-500 focus:outline-none focus:border-brand-gold text-left font-mono text-lg"
              />
              <Search className="absolute left-3 top-3.5 text-gray-500" size={20} />
            </div>
            <button
              onClick={handleSearch}
              className="py-3 px-6 bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold rounded-xl active:translate-y-0.5 btn-hover-active"
            >
              بحث
            </button>
          </div>

          {/* Search Results */}
          {searched && (
            <div className="space-y-4">
              {customer ? (
                <div className="bg-brand-card/40 border border-brand-border/40 rounded-2xl p-5 space-y-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="text-xl font-bold text-white">{customer.name}</h4>
                      <p className="text-gray-400 font-mono text-sm mt-1">{customer.phone}</p>
                      {customer.notes && (
                        <p className="text-yellow-600/90 text-sm mt-1">ملاحظات: {customer.notes}</p>
                      )}
                    </div>
                    
                    {!isAddingAddress && (
                      <button
                        onClick={() => setIsAddingAddress(true)}
                        className="py-2 px-3 bg-brand-border/30 hover:bg-brand-border/60 text-brand-gold rounded-lg font-semibold text-xs flex items-center gap-1 active:translate-y-0.5 btn-hover-active"
                      >
                        <Plus size={14} />
                        إضافة عنوان جديد
                      </button>
                    )}
                  </div>

                  {/* Add Address Form */}
                  {isAddingAddress && (
                    <form onSubmit={handleAddAddress} className="bg-brand-card/80 p-4 rounded-xl border border-brand-border/65 space-y-4 animate-in slide-in-from-top-2 duration-150">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-gray-400 text-xs block mb-1">المنطقة (لتحديد خدمة التوصيل)</label>
                          <select
                            value={selectedZoneId}
                            onChange={(e) => setSelectedZoneId(e.target.value)}
                            className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-gold"
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
                            className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-gold"
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
                          className="py-1.5 px-4 bg-brand-gold text-brand-dark hover:bg-opacity-90 rounded-lg font-bold text-sm"
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
                              <span className="text-xs text-brand-gold mt-1 inline-block">
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
                </div>
              ) : (
                <div className="text-center py-6 bg-brand-card/20 rounded-2xl border border-brand-border/30">
                  <p className="text-gray-400 mb-4">هذا الرقم غير مسجل في النظام.</p>
                  {!isRegistering ? (
                    <button
                      onClick={() => setIsRegistering(true)}
                      className="py-2.5 px-5 bg-brand-gold text-brand-dark hover:bg-opacity-90 font-bold rounded-xl flex items-center gap-2 mx-auto active:translate-y-0.5 btn-hover-active"
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
                          className="w-full bg-brand-surface border border-brand-border/50 rounded-lg p-2.5 text-white focus:outline-none focus:border-brand-gold"
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
                          className="py-1.5 px-4 bg-brand-gold text-brand-dark hover:bg-opacity-90 rounded-lg font-bold text-sm"
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
