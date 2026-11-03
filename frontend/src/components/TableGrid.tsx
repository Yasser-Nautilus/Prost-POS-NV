import React from "react";

interface TableGridProps {
  isOpen: boolean;
  selectedTable: number | null;
  onSelect: (tableNo: number) => void;
  onClose: () => void;
  tableCount?: number;
  /** Map of table_no (number) → invoice label (e.g. "#42") for occupied tables */
  occupiedTables?: Record<number, string>;
}

export const TableGrid: React.FC<TableGridProps> = ({
  isOpen,
  selectedTable,
  onSelect,
  onClose,
  tableCount = 12,
  occupiedTables = {},
}) => {
  if (!isOpen) return null;

  const tables = Array.from({ length: tableCount }, (_, i) => i + 1);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
      <div className="w-full max-w-lg mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
        {/* Header */}
        <div className="p-5 border-b border-brand-border/40 flex items-center justify-between">
          <h3 className="font-bold text-xl text-brand-gold">اختيار رقم الطاولة</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
          >
            ✕
          </button>
        </div>

        {/* Legend */}
        <div className="px-6 pt-4 flex items-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-brand-card border border-brand-border/40 inline-block" />
            فارغة
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-red-500 inline-block animate-pulse" />
            مشغولة
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-brand-gold inline-block" />
            مختارة
          </span>
        </div>

        {/* Table Grid */}
        <div className="p-6">
          <div className="grid grid-cols-4 gap-3">
            {tables.map((tableNo) => {
              const isSelected = selectedTable === tableNo;
              const isOccupied = tableNo in occupiedTables;
              const invoiceLabel = occupiedTables[tableNo];

              return (
                <button
                  key={tableNo}
                  type="button"
                  onClick={() => onSelect(tableNo)}
                  className={`
                    relative h-20 rounded-2xl border-2 font-bold text-lg
                    flex flex-col items-center justify-center gap-0.5
                    transition-all duration-200 active:scale-95
                    ${
                      isSelected
                        ? "bg-brand-gold/15 border-brand-gold text-brand-gold shadow-lg shadow-brand-gold/20"
                        : isOccupied
                        ? "bg-red-950/40 border-red-700/70 text-red-400 shadow-md shadow-red-900/20"
                        : "bg-brand-card border-brand-border/40 text-gray-300 hover:text-white hover:border-brand-border hover:bg-brand-card/80"
                    }
                  `}
                >
                  <span className="text-[9px] text-gray-500 uppercase tracking-wider">طاولة</span>
                  <span className={`text-2xl font-black font-mono ${isSelected ? "text-brand-gold" : isOccupied ? "text-red-400" : ""}`}>
                    {tableNo}
                  </span>

                  {/* Occupied badge */}
                  {isOccupied && !isSelected && (
                    <span className="text-[8px] text-red-500 font-bold leading-none">
                      {invoiceLabel || "مشغولة"}
                    </span>
                  )}

                  {/* Selected indicator */}
                  {isSelected && (
                    <div className="absolute top-1.5 left-1.5 h-3 w-3 rounded-full bg-brand-gold animate-pulse" />
                  )}

                  {/* Occupied indicator */}
                  {isOccupied && !isSelected && (
                    <div className="absolute top-1.5 left-1.5 h-2.5 w-2.5 rounded-full bg-red-500 animate-pulse" />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="p-5 border-t border-brand-border/40 flex items-center justify-between">
          <span className="text-sm text-gray-400">
            {selectedTable
              ? `تم اختيار الطاولة رقم ${selectedTable}`
              : "اضغط على طاولة لاختيارها"}
          </span>
          <button
            onClick={onClose}
            disabled={!selectedTable}
            className="py-2.5 px-6 rounded-xl font-bold text-sm bg-brand-gold text-brand-dark hover:bg-opacity-90 disabled:opacity-40 disabled:cursor-not-allowed active:translate-y-0.5 transition-all"
          >
            تأكيد الطاولة
          </button>
        </div>
      </div>
    </div>
  );
};
