import React, { useState, useEffect } from "react";
import { Package, Plus, Edit3, EyeOff, RefreshCw, Loader2, AlertCircle, X, Check } from "lucide-react";
import { bridge } from "../bridge";

interface ProductsViewProps {
  currentUser: any;
}

export const ProductsView: React.FC<ProductsViewProps> = ({ currentUser }) => {
  const [categories, setCategories] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [selectedCatId, setSelectedCatId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  // Product form state
  const [showProductForm, setShowProductForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState<any | null>(null);
  const [formName, setFormName] = useState("");
  const [formPrice, setFormPrice] = useState("");
  const [formCatId, setFormCatId] = useState<number | null>(null);
  const [formSortOrder, setFormSortOrder] = useState("0");

  // Category form state
  const [showCatForm, setShowCatForm] = useState(false);
  const [editingCat, setEditingCat] = useState<any | null>(null);
  const [catFormName, setCatFormName] = useState("");
  const [catFormSortOrder, setCatFormSortOrder] = useState("0");

  const isManagerOrAbove =
    currentUser?.role === "manager" || currentUser?.role === "admin";

  const fetchAll = async () => {
    setLoading(true);
    try {
      const cats = await bridge.call("get_all_categories");
      setCategories(cats || []);
      if (!selectedCatId && cats && cats.length > 0) {
        setSelectedCatId(cats[0].id);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async (catId: number) => {
    try {
      const prods = await bridge.call("get_products_by_category", { category_id: catId });
      setProducts(prods || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  useEffect(() => {
    if (selectedCatId !== null) {
      fetchProducts(selectedCatId);
    }
  }, [selectedCatId]);

  // ── Product form handlers ──────────────────────────────────────────────────

  const openNewProduct = () => {
    setEditingProduct(null);
    setFormName("");
    setFormPrice("");
    setFormCatId(selectedCatId);
    setFormSortOrder("0");
    setShowProductForm(true);
  };

  const openEditProduct = (prod: any) => {
    setEditingProduct(prod);
    setFormName(prod.name);
    setFormPrice(prod.price.toString());
    setFormCatId(prod.category_id);
    setFormSortOrder((prod.sort_order || 0).toString());
    setShowProductForm(true);
  };

  const handleSaveProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    const price = parseFloat(formPrice);
    if (!formName || isNaN(price) || !formCatId) {
      alert("يرجى ملء جميع الحقول المطلوبة");
      return;
    }
    try {
      if (editingProduct) {
        await bridge.call("update_product", {
          product_id: editingProduct.id,
          name: formName,
          price,
          category_id: formCatId,
          sort_order: parseInt(formSortOrder) || 0,
        });
      } else {
        await bridge.call("create_product", {
          name: formName,
          price,
          category_id: formCatId,
          sort_order: parseInt(formSortOrder) || 0,
        });
      }
      setShowProductForm(false);
      if (selectedCatId !== null) fetchProducts(selectedCatId);
    } catch (err: any) {
      alert("فشل حفظ المنتج: " + err.message);
    }
  };

  const handleDeactivateProduct = async (prodId: number, prodName: string) => {
    if (!window.confirm(`هل تريد إلغاء تفعيل المنتج "${prodName}"؟`)) return;
    try {
      await bridge.call("deactivate_product", { product_id: prodId });
      if (selectedCatId !== null) fetchProducts(selectedCatId);
    } catch (err: any) {
      alert("فشل الإلغاء: " + err.message);
    }
  };

  // ── Category form handlers ────────────────────────────────────────────────

  const openNewCategory = () => {
    setEditingCat(null);
    setCatFormName("");
    setCatFormSortOrder("0");
    setShowCatForm(true);
  };

  const openEditCategory = (cat: any) => {
    setEditingCat(cat);
    setCatFormName(cat.name);
    setCatFormSortOrder((cat.sort_order || 0).toString());
    setShowCatForm(true);
  };

  const handleSaveCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!catFormName) {
      alert("اسم الفئة مطلوب");
      return;
    }
    try {
      if (editingCat) {
        await bridge.call("update_category", {
          category_id: editingCat.id,
          name: catFormName,
          sort_order: parseInt(catFormSortOrder) || 0,
        });
      } else {
        await bridge.call("create_category", {
          name: catFormName,
          sort_order: parseInt(catFormSortOrder) || 0,
        });
      }
      setShowCatForm(false);
      fetchAll();
    } catch (err: any) {
      alert("فشل حفظ الفئة: " + err.message);
    }
  };

  if (loading && categories.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-white space-y-2 h-[calc(100vh-64px)] bg-brand-dark">
        <Loader2 className="animate-spin text-brand-gold" size={32} />
        <p className="text-gray-400 text-xs">جاري تحميل المنتجات...</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden h-[calc(100vh-64px)] bg-brand-dark flex flex-col">
      {/* Header */}
      <div className="p-6 pb-0 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-brand-gold/10 text-brand-gold flex items-center justify-center">
            <Package size={20} />
          </div>
          <div>
            <h2 className="text-xl font-black text-white">إدارة المنتجات</h2>
            <p className="text-xs text-gray-400">
              {products.length} منتج في الفئة المحددة
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={openNewCategory}
            className="py-2 px-3 bg-brand-card border border-brand-border/40 hover:border-brand-gold text-gray-300 hover:text-brand-gold rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all"
          >
            <Plus size={14} />
            فئة جديدة
          </button>
          {isManagerOrAbove && (
            <button
              onClick={openNewProduct}
              className="py-2 px-4 bg-brand-gold text-brand-dark hover:bg-opacity-90 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all"
            >
              <Plus size={14} />
              منتج جديد
            </button>
          )}
          <button
            onClick={fetchAll}
            className="p-2 bg-brand-card border border-brand-border/40 hover:border-brand-gold text-gray-400 hover:text-brand-gold rounded-xl transition-all"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden p-6 gap-6">
        {/* Category sidebar */}
        <div className="w-48 flex-shrink-0 space-y-2 overflow-y-auto">
          <h4 className="text-xs font-bold text-gray-500 mb-3">الفئات</h4>
          {categories.map((cat) => (
            <div
              key={cat.id}
              className={`flex justify-between items-center p-3 rounded-xl border cursor-pointer transition-all group ${
                selectedCatId === cat.id
                  ? "bg-brand-gold/10 border-brand-gold text-brand-gold"
                  : "bg-brand-card/40 border-brand-border/30 text-gray-300 hover:border-brand-border"
              } ${!cat.is_active ? "opacity-50" : ""}`}
              onClick={() => setSelectedCatId(cat.id)}
            >
              <span className="text-sm font-bold truncate">{cat.name}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  openEditCategory(cat);
                }}
                className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-brand-gold transition-all"
              >
                <Edit3 size={12} />
              </button>
            </div>
          ))}
        </div>

        {/* Products grid */}
        <div className="flex-1 overflow-y-auto">
          {products.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
              {products.map((prod) => (
                <div
                  key={prod.id}
                  className={`p-4 bg-brand-card border border-brand-border/40 rounded-2xl flex flex-col justify-between h-36 transition-all group ${
                    !prod.is_active ? "opacity-50" : "hover:border-brand-border"
                  }`}
                >
                  <div>
                    <h4 className="text-white font-bold text-sm leading-snug group-hover:text-brand-gold transition-colors">
                      {prod.name}
                    </h4>
                    {!prod.is_active && (
                      <span className="text-[10px] text-red-400 font-bold block mt-0.5">
                        غير نشط
                      </span>
                    )}
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-brand-gold font-extrabold text-base">
                      {prod.price}{" "}
                      <span className="text-[10px] font-semibold">ج.م</span>
                    </span>
                    {isManagerOrAbove && (
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => openEditProduct(prod)}
                          className="h-7 w-7 rounded-lg bg-brand-gold/10 text-brand-gold flex items-center justify-center hover:bg-brand-gold/20 transition-all"
                        >
                          <Edit3 size={12} />
                        </button>
                        {prod.is_active && (
                          <button
                            onClick={() => handleDeactivateProduct(prod.id, prod.name)}
                            className="h-7 w-7 rounded-lg bg-red-950/30 text-red-400 flex items-center justify-center hover:bg-red-950/60 transition-all"
                          >
                            <EyeOff size={12} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-gray-500">
              <AlertCircle size={48} className="text-brand-border/50 mb-2" />
              <p className="text-sm">لا توجد منتجات في هذه الفئة</p>
            </div>
          )}
        </div>
      </div>

      {/* Product Form Modal */}
      {showProductForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
          <div className="w-full max-w-md mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="p-5 border-b border-brand-border/40 flex items-center justify-between">
              <h3 className="font-bold text-lg text-brand-gold">
                {editingProduct ? "تعديل المنتج" : "إضافة منتج جديد"}
              </h3>
              <button
                onClick={() => setShowProductForm(false)}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
              >
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleSaveProduct} className="p-6 space-y-4">
              <div>
                <label className="text-gray-400 text-xs block mb-1">اسم المنتج *</label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="مثال: دجاج مشوي كامل..."
                  className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white placeholder-gray-600 focus:outline-none focus:border-brand-gold text-right"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-gray-400 text-xs block mb-1">السعر (ج.م) *</label>
                  <input
                    type="number"
                    required
                    min="0"
                    step="0.5"
                    value={formPrice}
                    onChange={(e) => setFormPrice(e.target.value)}
                    placeholder="0.00"
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white focus:outline-none focus:border-brand-gold text-center font-mono font-bold"
                  />
                </div>
                <div>
                  <label className="text-gray-400 text-xs block mb-1">الترتيب</label>
                  <input
                    type="number"
                    min="0"
                    value={formSortOrder}
                    onChange={(e) => setFormSortOrder(e.target.value)}
                    className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white focus:outline-none focus:border-brand-gold text-center font-mono"
                  />
                </div>
              </div>
              <div>
                <label className="text-gray-400 text-xs block mb-1">الفئة *</label>
                <select
                  required
                  value={formCatId || ""}
                  onChange={(e) => setFormCatId(parseInt(e.target.value))}
                  className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white focus:outline-none focus:border-brand-gold"
                >
                  <option value="">-- اختر الفئة --</option>
                  {categories
                    .filter((c) => c.is_active)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                </select>
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowProductForm(false)}
                  className="flex-1 py-3 bg-brand-card border border-brand-border/40 text-gray-300 rounded-xl font-bold"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="flex-1 py-3 bg-brand-gold text-brand-dark hover:bg-opacity-90 rounded-xl font-bold flex items-center justify-center gap-2"
                >
                  <Check size={18} />
                  حفظ المنتج
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Category Form Modal */}
      {showCatForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md">
          <div className="w-full max-w-sm mx-4 bg-brand-surface border border-brand-border rounded-3xl overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="p-5 border-b border-brand-border/40 flex items-center justify-between">
              <h3 className="font-bold text-lg text-brand-gold">
                {editingCat ? "تعديل الفئة" : "فئة جديدة"}
              </h3>
              <button
                onClick={() => setShowCatForm(false)}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-brand-border/30"
              >
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleSaveCategory} className="p-6 space-y-4">
              <div>
                <label className="text-gray-400 text-xs block mb-1">اسم الفئة *</label>
                <input
                  type="text"
                  required
                  value={catFormName}
                  onChange={(e) => setCatFormName(e.target.value)}
                  placeholder="مثال: وجبات مشوية..."
                  className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white placeholder-gray-600 focus:outline-none focus:border-brand-gold text-right"
                />
              </div>
              <div>
                <label className="text-gray-400 text-xs block mb-1">الترتيب</label>
                <input
                  type="number"
                  min="0"
                  value={catFormSortOrder}
                  onChange={(e) => setCatFormSortOrder(e.target.value)}
                  className="w-full bg-brand-card border border-brand-border/50 rounded-xl p-3 text-white focus:outline-none focus:border-brand-gold text-center font-mono"
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowCatForm(false)}
                  className="flex-1 py-3 bg-brand-card border border-brand-border/40 text-gray-300 rounded-xl font-bold"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="flex-1 py-3 bg-brand-gold text-brand-dark hover:bg-opacity-90 rounded-xl font-bold"
                >
                  حفظ
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
