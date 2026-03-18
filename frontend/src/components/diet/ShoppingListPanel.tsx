import { useMemo, useState } from 'react';
import { Check, ShoppingBasket } from 'lucide-react';

import type { ShoppingListResponse } from '../../types/diet';

export function ShoppingListPanel({
  shoppingList,
}: {
  shoppingList: ShoppingListResponse | null;
}) {
  const [checkedKeys, setCheckedKeys] = useState<string[]>([]);
  const checkedSet = useMemo(() => new Set(checkedKeys), [checkedKeys]);
  const groupedIngredients = shoppingList?.grouped_ingredients || [];
  const unmatchedDishes = shoppingList?.unmatched_dishes || [];

  const toggleItem = (key: string) => {
    setCheckedKeys((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]
    );
  };

  return (
    <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 shadow-sm transition-all duration-200 hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-900/20 dark:text-emerald-200">
            <ShoppingBasket className="h-3.5 w-3.5" />
            本周采购清单
          </div>
          <h3 className="mt-3 text-lg font-semibold text-gray-900 dark:text-gray-100">
            先把食材准备好，执行会轻松很多
          </h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            基于本周计划与菜谱知识库聚合食材，未匹配菜品会单独提示。
          </p>
        </div>
        <div className="rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-950/40 px-3 py-2 text-right">
          <div className="text-[11px] text-gray-500">已汇总食材</div>
          <div className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {groupedIngredients.length}
          </div>
        </div>
      </div>

      {groupedIngredients.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-950/30 px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
          本周还没有可汇总的计划菜品。先把餐次排进去，这里会自动生成采购清单。
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
          {groupedIngredients.map((item) => {
            const checked = checkedSet.has(item.name);
            return (
              <button
                key={item.name}
                type="button"
                onClick={() => toggleItem(item.name)}
                className={`rounded-2xl border p-4 text-left transition-all ${
                  checked
                    ? 'border-emerald-200 bg-emerald-50/70 dark:border-emerald-900/40 dark:bg-emerald-900/10'
                    : 'border-gray-100 bg-gray-50/70 hover:border-amber-200 hover:bg-amber-50/60 dark:border-gray-800 dark:bg-gray-950/30 dark:hover:border-amber-900/40 dark:hover:bg-amber-900/10'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {item.name}
                    </div>
                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      关联 {item.count} 道菜
                    </div>
                  </div>
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-full border ${
                      checked
                        ? 'border-emerald-500 bg-emerald-500 text-white'
                        : 'border-gray-300 text-transparent dark:border-gray-700'
                    }`}
                    aria-hidden="true"
                  >
                    <Check className="h-3.5 w-3.5" />
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {item.dishes.slice(0, 3).map((dish) => (
                    <span
                      key={dish}
                      className="rounded-full bg-white/80 px-2.5 py-1 text-[11px] text-gray-600 dark:bg-gray-900 dark:text-gray-300"
                    >
                      {dish}
                    </span>
                  ))}
                  {item.dishes.length > 3 ? (
                    <span className="rounded-full bg-white/80 px-2.5 py-1 text-[11px] text-gray-500 dark:bg-gray-900 dark:text-gray-400">
                      +{item.dishes.length - 3}
                    </span>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {unmatchedDishes.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-amber-200/70 bg-amber-50/70 px-4 py-3 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/10 dark:text-amber-200">
          <div className="font-medium">未匹配菜品</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {unmatchedDishes.map((dish) => (
              <span
                key={dish}
                className="rounded-full bg-white/80 px-2.5 py-1 dark:bg-gray-900/70"
              >
                {dish}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
