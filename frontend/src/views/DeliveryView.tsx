import React, { useState, useEffect } from "react";
import { Truck, Users, UserCheck, UserMinus, Plus, MapPin, CheckCircle, Clock, Loader2 } from "lucide-react";
import { bridge } from "../bridge";

interface DeliveryViewProps {
  currentUser: any;
}

export const DeliveryView: React.FC<DeliveryViewProps> = ({ currentUser: _currentUser }) => {
  const [drivers, setDrivers] = useState<any[]>([]);
  const [trips, setTrips] = useState<any[]>([]);
  const [unassignedOrders, setUnassignedOrders] = useState<any[]>([]);
  const [selectedOrders, setSelectedOrders] = useState<number[]>([]);
  const [selectedDriverId, setSelectedDriverId] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const fetchDeliveryData = async () => {
    setLoading(true);
    try {
      const drvs = await bridge.call("get_available_drivers");
      setDrivers(drvs || []);
      
      const trps = await bridge.call("get_active_trips");
      setTrips(trps || []);

      // Simulating loading unassigned orders from active pending orders in system
      // In python backend, any delivery order confirmed but not dispatched yet.
      const orders = await bridge.call("get_active_orders");
      const unassigned = (orders || []).filter(
        (o: any) => o.order_type === "delivery" && o.status === "new"
      );
      setUnassignedOrders(unassigned);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDeliveryData();
  }, []);

  const handleToggleDriverStatus = async (drvId: number, isCheckedIn: boolean) => {
    try {
      if (isCheckedIn) {
        await bridge.call("check_out_driver", { driver_id: drvId });
      } else {
        await bridge.call("check_in_driver", { driver_id: drvId });
      }
      fetchDeliveryData();
    } catch (err: any) {
      alert("فشل تغيير حالة الطيار: " + err.message);
    }
  };

  const handleToggleOrderSelection = (orderId: number) => {
    setSelectedOrders((prev) =>
      prev.includes(orderId) ? prev.filter((id) => id !== orderId) : [...prev, orderId]
    );
  };

  const handleCreateTrip = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDriverId || selectedOrders.length === 0) return;
    try {
      // Per backend: first create_trip to get trip_id, then dispatch_trip with that trip_id
      const tripResult = await bridge.call("create_trip", {
        driver_id: parseInt(selectedDriverId),
        order_ids: selectedOrders
      });
      
      if (tripResult?.trip_id) {
        await bridge.call("dispatch_trip", { trip_id: tripResult.trip_id });
      }
      
      setSelectedOrders([]);
      fetchDeliveryData();
      alert("تم إرسال الطيار بالرحلة بنجاح!");
    } catch (err: any) {
      alert("فشل إنشاء الرحلة: " + err.message);
    }
  };

  const handleSettleTrip = async (tripId: number) => {
    if (!window.confirm("هل تأكدت من تحصيل مبالغ الفواتير وإغلاق الرحلة؟")) return;
    try {
      await bridge.call("settle_trip", { trip_id: tripId });
      fetchDeliveryData();
      alert("تمت تسوية حساب الرحلة وإغلاقها بنجاح!");
    } catch (err: any) {
      alert("فشل تسوية الرحلة: " + err.message);
    }
  };

  if (loading && drivers.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)] bg-brand-dark">
        <Loader2 className="animate-spin text-brand-gold" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل الرحلات والطيارين...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden p-6 space-y-6 h-[calc(100vh-64px)] flex flex-col md:flex-row gap-6">
      
      {/* Right Column: Dispatcher form & Unassigned (3 cols equivalent) */}
      <div className="flex-1 space-y-6 overflow-y-auto">
        <div className="bg-brand-card p-5 rounded-2xl border border-brand-border/40">
          <h3 className="font-bold text-lg text-brand-gold flex items-center gap-2 mb-4">
            <Truck size={20} />
            توزيع وتجهيز رحلات الدليفري
          </h3>
          
          <form onSubmit={handleCreateTrip} className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
            <div className="sm:col-span-2">
              <label className="text-gray-400 text-xs block mb-1">اختر الطيار لتسليمه الطلبات</label>
              <select
                value={selectedDriverId}
                onChange={(e) => setSelectedDriverId(e.target.value)}
                className="w-full bg-brand-surface border border-brand-border/50 rounded-xl p-3 text-white focus:outline-none focus:border-brand-gold"
              >
                <option value="">-- اختر طياراً نشطاً --</option>
                {drivers.map((drv) => (
                  <option key={drv.id} value={drv.id}>
                    {drv.display_name} ({drv.role === "cashier" ? "متاح" : "خارج في رحلة"})
                  </option>
                ))}
              </select>
            </div>
            
            <button
              type="submit"
              disabled={!selectedDriverId || selectedOrders.length === 0}
              className="py-3 bg-brand-gold text-brand-dark disabled:opacity-50 hover:bg-opacity-95 font-bold rounded-xl active:translate-y-0.5 btn-hover-active flex items-center justify-center gap-1.5"
            >
              <Plus size={18} />
              إرسال طيار بالرحلة ({selectedOrders.length})
            </button>
          </form>
        </div>

        {/* Unassigned Deliveries List */}
        <div className="space-y-3">
          <h4 className="text-sm font-bold text-gray-400">طلبات دليفري معلقة تنتظر الإرسال:</h4>
          
          {unassignedOrders.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {unassignedOrders.map((o) => {
                const isSelected = selectedOrders.includes(o.id);
                return (
                  <div
                    key={o.id}
                    onClick={() => handleToggleOrderSelection(o.id)}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? "bg-brand-gold/10 border-brand-gold"
                        : "bg-brand-card/40 border-brand-border/30 hover:border-brand-border/60"
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <span className="text-white font-bold block text-sm">فاتورة #{o.invoice_no || o.id}</span>
                        <span className="text-xs text-gray-400 mt-1 inline-block">العميل: {o.customer_name}</span>
                      </div>
                      <span className="font-extrabold text-brand-gold text-sm">{o.total} ج.م</span>
                    </div>
                    <div className="flex items-center gap-1 text-[11px] text-gray-500 mt-2">
                      <MapPin size={12} />
                      <span>{o.customer_address} ({o.customer_zone})</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="py-12 bg-brand-card/10 rounded-2xl border border-brand-border/20 text-center text-gray-500">
              لا توجد طلبات دليفري جاهزة للتحميل حالياً.
            </div>
          )}
        </div>
      </div>

      {/* Left Column: Active Trips & Active Drivers list (2 cols equivalent) */}
      <div className="w-full md:w-96 space-y-6 overflow-y-auto pr-0 md:pr-4 border-r md:border-r border-brand-border/40">
        
        {/* Active Driver Attendance List */}
        <div className="bg-brand-card/40 p-4 rounded-2xl border border-brand-border/30 space-y-3">
          <h4 className="text-sm font-bold text-brand-gold flex items-center gap-1.5">
            <Users size={16} />
            حضور وانصراف الطيارين
          </h4>
          <div className="space-y-2">
            {drivers.map((drv) => {
              // Backend marks drivers as checked-in via is_checked_in; fall back to is_active
              const isCheckedIn = drv.is_checked_in !== undefined ? drv.is_checked_in : drv.is_active;
              return (
                <div key={drv.id} className="p-2 bg-brand-card/50 rounded-lg flex justify-between items-center text-xs border border-brand-border/20">
                  <div>
                    <span className="text-white font-bold block">{drv.display_name}</span>
                    <span className="text-[10px] text-gray-500">الحالة: {isCheckedIn ? "نشط ومتاح" : "خارج الخدمة"}</span>
                  </div>
                  <button
                    onClick={() => handleToggleDriverStatus(drv.id, isCheckedIn)}
                    className={`py-1 px-3 rounded-md font-bold transition-all ${
                      isCheckedIn 
                        ? "bg-red-950/40 text-red-400 border border-red-900/30" 
                        : "bg-brand-teal/10 text-brand-teal border border-brand-teal/20"
                    }`}
                  >
                    {isCheckedIn ? <UserMinus size={14} /> : <UserCheck size={14} />}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Out of Delivery / Active Trips list */}
        <div className="space-y-3">
          <h4 className="text-sm font-bold text-gray-400 flex items-center gap-1.5">
            <Clock size={16} />
            رحلات نشطة في الطريق
          </h4>
          
          {trips.length > 0 ? (
            <div className="space-y-3">
              {trips.map((t) => (
                <div key={t.id} className="p-4 bg-brand-card border border-brand-border/50 rounded-xl space-y-3 animate-in fade-in duration-150">
                  <div className="flex justify-between items-start">
                    <div>
                      <span className="text-white font-bold block text-sm">{t.driver_name}</span>
                      <span className="text-xs text-brand-gold mt-1 inline-block">
                        حملت {t.order_ids?.length || 0} طلبات
                      </span>
                    </div>
                    <span className="py-1 px-2.5 bg-yellow-600/10 text-yellow-500 rounded-md font-bold text-[10px]">
                      بالطريق
                    </span>
                  </div>
                  <button
                    onClick={() => handleSettleTrip(t.id)}
                    className="w-full py-2 bg-brand-teal text-white hover:bg-opacity-90 font-bold rounded-lg text-xs flex items-center justify-center gap-1 btn-hover-active"
                  >
                    <CheckCircle size={14} />
                    تسوية وإغلاق الرحلة
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-10 bg-brand-card/10 rounded-2xl border border-brand-border/20 text-center text-xs text-gray-500 italic">
              لا توجد رحلات خارج الدكان حالياً.
            </div>
          )}
        </div>

      </div>

    </div>
  );
};
