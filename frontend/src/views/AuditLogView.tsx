/**
 * AuditLogView — Immutable audit trail viewer for managers.
 *
 * Features:
 * - Date/event-type/entity filters
 * - Color-coded event types
 * - Before/after data diff display
 * - Order link to open order status history inline
 * - Export-ready (read-only, no edits possible)
 */

import { useState, useEffect, useCallback } from "react";
import {
  Shield, Search, Filter, RefreshCcw, Loader2, ChevronDown,
  ChevronUp, Clock, User, Package, Truck,
  XCircle, Tag, DollarSign, FileText
} from "lucide-react";
import { bridge } from "../bridge";

interface AuditLogViewProps {
  currentUser: any;
}

const EVENT_TYPE_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  order_created:                { label: "إنشاء طلب",       color: "text-green-400 bg-green-900/20 border-green-700/30",  icon: Package },
  order_amended:                { label: "تعديل طلب",        color: "text-blue-400 bg-blue-900/20 border-blue-700/30",    icon: Package },
  order_cancelled:              { label: "إلغاء طلب",       color: "text-red-400 bg-red-900/20 border-red-700/30",       icon: XCircle },
  discount_applied:             { label: "تطبيق خصم",        color: "text-amber-400 bg-amber-900/20 border-amber-700/30", icon: Tag },
  item_removed:                 { label: "حذف عنصر",         color: "text-orange-400 bg-orange-900/20 border-orange-700/30", icon: Package },
  driver_assigned:              { label: "تعيين سائق",       color: "text-blue-300 bg-blue-900/10 border-blue-700/20",   icon: Truck },
  trip_created:                 { label: "إنشاء رحلة",       color: "text-blue-400 bg-blue-900/20 border-blue-700/30",   icon: Truck },
  trip_dispatched:              { label: "إرسال رحلة",       color: "text-teal-400 bg-teal-900/20 border-teal-700/30",   icon: Truck },
  trip_returned:                { label: "عودة رحلة",        color: "text-cyan-400 bg-cyan-900/20 border-cyan-700/30",   icon: Truck },
  trip_settled:                 { label: "تسوية رحلة",       color: "text-green-400 bg-green-900/20 border-green-700/30",icon: DollarSign },
  driver_settlement_completed:  { label: "تسوية سائق",       color: "text-brand-gold bg-brand-gold/10 border-brand-gold/20", icon: DollarSign },
  customer_created:             { label: "عميل جديد",        color: "text-purple-400 bg-purple-900/20 border-purple-700/30", icon: User },
  customer_updated:             { label: "تعديل عميل",       color: "text-purple-300 bg-purple-900/10 border-purple-700/20", icon: User },
  shift_opened:                 { label: "فتح وردية",        color: "text-green-400 bg-green-900/20 border-green-700/30",icon: Clock },
  shift_closed:                 { label: "إغلاق وردية",      color: "text-gray-400 bg-gray-900/20 border-gray-700/30",   icon: Clock },
  shift_transferred:            { label: "نقل وردية",        color: "text-indigo-400 bg-indigo-900/20 border-indigo-700/30", icon: Clock },
  user_created:                 { label: "مستخدم جديد",      color: "text-purple-400 bg-purple-900/20 border-purple-700/30", icon: User },
  user_updated:                 { label: "تعديل مستخدم",     color: "text-purple-300 bg-purple-900/10 border-purple-700/20", icon: User },
};

const ALL_EVENT_TYPES = Object.keys(EVENT_TYPE_CONFIG);

const fmtDateTime = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("ar-EG", {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      })
    : "—";

export function AuditLogView({ currentUser: _currentUser }: AuditLogViewProps) {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedLog, setExpandedLog] = useState<number | null>(null);

  // Filters
  const [filterDate, setFilterDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [filterEventType, setFilterEventType] = useState("");
  const [filterOrderId, setFilterOrderId] = useState("");
  const [filterEntityType, setFilterEntityType] = useState("");

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const payload: any = { limit: 150 };
      if (filterDate) payload.date = filterDate;
      if (filterEventType) payload.event_type = filterEventType;
      if (filterOrderId) payload.order_id = parseInt(filterOrderId, 10);
      if (filterEntityType) payload.entity_type = filterEntityType;

      const data = await bridge.call("get_audit_logs", payload);
      setLogs(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterDate, filterEventType, filterOrderId, filterEntityType]);

  useEffect(() => { loadLogs(); }, [loadLogs]);

  const getEventConfig = (eventType: string) =>
    EVENT_TYPE_CONFIG[eventType] || {
      label: eventType,
      color: "text-gray-400 bg-gray-900/20 border-gray-700/30",
      icon: FileText,
    };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-brand-border bg-brand-surface">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
            <Shield className="text-purple-400" size={18} />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">سجل التدقيق</h1>
            <p className="text-xs text-gray-400">جميع الأحداث القابلة للمراجعة — للقراءة فقط</p>
          </div>
        </div>
        <button
          onClick={loadLogs}
          className="p-2 hover:bg-brand-card rounded-xl transition-all text-gray-400 hover:text-white"
          title="تحديث"
        >
          <RefreshCcw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 px-6 py-3 bg-brand-surface/50 border-b border-brand-border/50">
        <Filter size={14} className="text-gray-400" />

        {/* Date filter */}
        <input
          type="date"
          value={filterDate}
          onChange={(e) => setFilterDate(e.target.value)}
          className="bg-brand-card border border-brand-border rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-gold/50 transition-all"
        />

        {/* Event type */}
        <select
          value={filterEventType}
          onChange={(e) => setFilterEventType(e.target.value)}
          className="bg-brand-card border border-brand-border rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-gold/50 transition-all"
        >
          <option value="">جميع الأحداث</option>
          {ALL_EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{EVENT_TYPE_CONFIG[t]?.label || t}</option>
          ))}
        </select>

        {/* Entity type */}
        <select
          value={filterEntityType}
          onChange={(e) => setFilterEntityType(e.target.value)}
          className="bg-brand-card border border-brand-border rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-gold/50 transition-all"
        >
          <option value="">جميع الكيانات</option>
          <option value="order">طلبات</option>
          <option value="trip">رحلات</option>
          <option value="driver">سائقون</option>
          <option value="customer">عملاء</option>
          <option value="user">مستخدمون</option>
          <option value="shift">ورديات</option>
        </select>

        {/* Order ID search */}
        <div className="relative flex items-center">
          <Search size={13} className="absolute right-2.5 text-gray-500" />
          <input
            type="number"
            value={filterOrderId}
            onChange={(e) => setFilterOrderId(e.target.value)}
            placeholder="رقم الطلب..."
            className="bg-brand-card border border-brand-border rounded-lg pr-8 pl-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-gold/50 transition-all w-28"
            dir="ltr"
          />
        </div>

        {/* Result count */}
        <span className="text-xs text-gray-500 mr-auto">
          {logs.length} سجل
        </span>
      </div>

      {/* Log list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="animate-spin text-brand-gold" size={32} />
          </div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-center p-8">
            <Shield className="text-gray-600" size={36} />
            <p className="text-gray-400">لا توجد سجلات بهذه المعايير</p>
          </div>
        ) : (
          <div className="divide-y divide-brand-border/30">
            {logs.map((log) => {
              const cfg = getEventConfig(log.event_type);
              const EventIcon = cfg.icon;
              const isExpanded = expandedLog === log.id;

              return (
                <div key={log.id} className="hover:bg-brand-card/20 transition-colors">
                  <button
                    onClick={() => setExpandedLog(isExpanded ? null : log.id)}
                    className="w-full flex items-start gap-4 px-6 py-3 text-right"
                  >
                    {/* Event badge */}
                    <div className={`flex-shrink-0 mt-0.5 flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold whitespace-nowrap ${cfg.color}`}>
                      <EventIcon size={12} />
                      {cfg.label}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0 text-right">
                      <div className="flex items-baseline gap-2">
                        <span className="text-white font-semibold text-sm">
                          {log.action || cfg.label}
                        </span>
                        {log.order_id && (
                          <span className="text-xs text-gray-500">
                            طلب #{log.order_id}
                          </span>
                        )}
                        {log.entity_type && log.entity_id && !log.order_id && (
                          <span className="text-xs text-gray-500">
                            {log.entity_type} #{log.entity_id}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="text-xs text-gray-400 flex items-center gap-1">
                          <User size={10} />
                          {log.user_name}
                        </span>
                        {log.reason && (
                          <span className="text-xs text-amber-400/80 truncate max-w-[200px]">
                            السبب: {log.reason}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Time + expand */}
                    <div className="flex-shrink-0 flex items-center gap-2">
                      <span className="text-xs text-gray-500 whitespace-nowrap">
                        {fmtDateTime(log.timestamp)}
                      </span>
                      {isExpanded ? (
                        <ChevronUp size={14} className="text-gray-500" />
                      ) : (
                        <ChevronDown size={14} className="text-gray-500" />
                      )}
                    </div>
                  </button>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="px-6 pb-4 space-y-3 bg-brand-surface/30">
                      <div className="grid grid-cols-2 gap-3">
                        {/* Before/after */}
                        {(log.before_data || log.after_data) && (
                          <>
                            {log.before_data && (
                              <DataBlock title="قبل التغيير" data={log.before_data} color="red" />
                            )}
                            {log.after_data && (
                              <DataBlock title="بعد التغيير" data={log.after_data} color="green" />
                            )}
                          </>
                        )}

                        {/* Legacy details */}
                        {log.details && !log.before_data && !log.after_data && (
                          <div className="col-span-2">
                            <DataBlock title="التفاصيل" data={log.details} color="blue" />
                          </div>
                        )}
                      </div>

                      {/* Metadata row */}
                      <div className="flex flex-wrap gap-3 pt-1 text-xs text-gray-500">
                        <span>المستخدم: {log.user_name} (#{log.user_id})</span>
                        {log.entity_type && <span>النوع: {log.entity_type}</span>}
                        {log.entity_id && <span>المعرّف: #{log.entity_id}</span>}
                        <span className="mr-auto">وقت التسجيل: {fmtDateTime(log.timestamp)}</span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Data block for before/after display ──────────────────────────────────────
function DataBlock({ title, data, color }: { title: string; data: any; color: "red" | "green" | "blue" }) {
  const colorMap = {
    red:   "border-red-700/30 bg-red-900/10 text-red-300",
    green: "border-green-700/30 bg-green-900/10 text-green-300",
    blue:  "border-blue-700/30 bg-blue-900/10 text-blue-300",
  };
  return (
    <div className={`rounded-lg border p-3 ${colorMap[color]}`}>
      <p className="text-xs font-semibold mb-2 opacity-70">{title}</p>
      <div className="space-y-1">
        {Object.entries(data).map(([key, val]) => (
          <div key={key} className="flex justify-between gap-2 text-xs">
            <span className="text-gray-400 shrink-0">{key}:</span>
            <span className="font-mono text-white text-right break-all">{JSON.stringify(val)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
