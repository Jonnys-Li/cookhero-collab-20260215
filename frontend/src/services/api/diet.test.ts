import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  DietReplanApplyResponse,
  DietReplanPreview,
  ShoppingListResponse,
} from '../../types/diet';
import { apiGet, apiPost } from './client';
import { applyReplan, getReplanPreview, getShoppingList } from './diet';

vi.mock('./client', () => ({
  apiDelete: vi.fn(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
}));

const mockedApiGet = vi.mocked(apiGet);
const mockedApiPost = vi.mocked(apiPost);

const previewFixture: DietReplanPreview = {
  week_start_date: '2026-03-16',
  affected_days: [],
  before_summary: {},
  after_summary: {},
  meal_changes: [],
  write_conflicts: [],
  compensation_summary: null,
  compensation_suggestions: [],
};

const shoppingListFixture: ShoppingListResponse = {
  week_start_date: '2026-03-16',
  week_end_date: '2026-03-22',
  aggregation_basis: 'compat',
  item_count: 0,
  items: [],
  matched_items: [],
  unmatched_dishes: [],
  grouped_ingredients: [],
};

const applyFixture: DietReplanApplyResponse = {
  action: 'compatibility_noop',
  applied_count: 0,
  updated_meal_ids: [],
  write_conflicts: [],
};

describe('diet api deployment skew guards', () => {
  beforeEach(() => {
    mockedApiGet.mockReset();
    mockedApiPost.mockReset();
  });

  it('prefers the primary base first for replan preview', async () => {
    mockedApiGet.mockResolvedValue(previewFixture);

    await expect(getReplanPreview('token', '2026-03-16')).resolves.toEqual(previewFixture);

    expect(mockedApiGet).toHaveBeenCalledTimes(1);
    expect(mockedApiGet).toHaveBeenCalledWith(
      '/diet/replan/preview?week_start_date=2026-03-16',
      'token',
      { preferFallback: false },
    );
  });

  it('retries shopping list via fallback when the primary route is missing', async () => {
    mockedApiGet
      .mockRejectedValueOnce(new Error('接口不存在（404 Not Found）'))
      .mockResolvedValueOnce(shoppingListFixture);

    await expect(getShoppingList('token', '2026-03-16')).resolves.toEqual(shoppingListFixture);

    expect(mockedApiGet).toHaveBeenCalledTimes(2);
    expect(mockedApiGet).toHaveBeenNthCalledWith(
      1,
      '/diet/shopping-list?week_start_date=2026-03-16',
      'token',
      { preferFallback: false },
    );
    expect(mockedApiGet).toHaveBeenNthCalledWith(
      2,
      '/diet/shopping-list?week_start_date=2026-03-16',
      'token',
      { preferFallback: true },
    );
  });

  it('retries apply-replan via fallback when the primary route is missing', async () => {
    mockedApiPost
      .mockRejectedValueOnce(new Error('接口不存在（404 Not Found）'))
      .mockResolvedValueOnce(applyFixture);

    await expect(applyReplan('token', [])).resolves.toEqual(applyFixture);

    expect(mockedApiPost).toHaveBeenCalledTimes(2);
    expect(mockedApiPost).toHaveBeenNthCalledWith(
      1,
      '/diet/replan/apply',
      { meal_changes: [] },
      'token',
      { preferFallback: false },
    );
    expect(mockedApiPost).toHaveBeenNthCalledWith(
      2,
      '/diet/replan/apply',
      { meal_changes: [] },
      'token',
      { preferFallback: true },
    );
  });
});
