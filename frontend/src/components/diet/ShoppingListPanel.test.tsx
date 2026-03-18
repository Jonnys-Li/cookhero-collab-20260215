import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ShoppingListPanel } from './ShoppingListPanel';

describe('ShoppingListPanel', () => {
  it('renders grouped ingredients and unmatched dishes', async () => {
    const user = userEvent.setup();

    render(
      <ShoppingListPanel
        shoppingList={{
          week_start_date: '2026-03-16',
          week_end_date: '2026-03-22',
          aggregation_basis: 'planned_meals',
          item_count: 2,
          items: [],
          matched_items: [
            {
              dish_name: '香煎鸡胸肉',
              matched_doc_id: 'doc-1',
              ingredients: ['鸡胸肉', '西兰花'],
            },
          ],
          unmatched_dishes: ['凉拌木耳'],
          grouped_ingredients: [
            { name: '鸡胸肉', count: 2, dishes: ['香煎鸡胸肉', '鸡肉沙拉'] },
            { name: '西兰花', count: 1, dishes: ['香煎鸡胸肉'] },
          ],
        }}
      />
    );

    expect(screen.getByText('本周采购清单')).toBeInTheDocument();
    expect(screen.getByText('鸡胸肉')).toBeInTheDocument();
    expect(screen.getByText('关联 2 道菜')).toBeInTheDocument();
    expect(screen.getByText('凉拌木耳')).toBeInTheDocument();

    const ingredientButtons = screen.getAllByRole('button');
    await user.click(ingredientButtons[0]);
  });

  it('shows empty state when there is no shopping list', () => {
    render(<ShoppingListPanel shoppingList={null} />);

    expect(
      screen.getByText('本周还没有可汇总的计划菜品。先把餐次排进去，这里会自动生成采购清单。')
    ).toBeInTheDocument();
  });
});
