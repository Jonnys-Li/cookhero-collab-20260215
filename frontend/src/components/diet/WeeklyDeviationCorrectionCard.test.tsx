import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { WeeklyDeviationCorrectionCard } from './WeeklyDeviationCorrectionCard';

vi.mock('../../services/api/diet', () => {
  return {
    getDeviationAnalysis: vi.fn(),
    addMealToPlan: vi.fn(),
  };
});

vi.mock('../../services/api/events', () => {
  return {
    trackEvent: vi.fn(),
  };
});

import * as dietApi from '../../services/api/diet';

describe('WeeklyDeviationCorrectionCard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('loads deviation analysis when clicking generate button', async () => {
    const user = userEvent.setup();
    vi.mocked(dietApi.getDeviationAnalysis).mockResolvedValue({
      has_plan: true,
      week_start_date: '2026-03-16',
      total_deviation: 300,
      total_deviation_pct: 10,
      execution_rate: 75,
      meal_deviations: [],
    });

    render(
      <WeeklyDeviationCorrectionCard
        token="t1"
        weekStartDate="2026-03-16"
        weeklySummary={null}
        planMeals={[]}
      />
    );

    await user.click(screen.getByRole('button', { name: '生成纠偏建议' }));

    await waitFor(() => {
      expect(dietApi.getDeviationAnalysis).toHaveBeenCalledTimes(1);
      expect(dietApi.getDeviationAnalysis).toHaveBeenCalledWith('t1', '2026-03-16');
    });
  });

  it('applies correction by writing next meal plan via addMealToPlan', async () => {
    const user = userEvent.setup();
    vi.mocked(dietApi.getDeviationAnalysis).mockResolvedValue({
      has_plan: true,
      week_start_date: '2026-03-16',
      total_deviation: 300,
      total_deviation_pct: 10,
      execution_rate: 75,
      meal_deviations: [],
    });
    vi.mocked(dietApi.addMealToPlan).mockResolvedValue(undefined);

    render(
      <WeeklyDeviationCorrectionCard
        token="t1"
        weekStartDate="2026-03-16"
        weeklySummary={null}
        planMeals={[]}
      />
    );

    await user.click(screen.getByRole('button', { name: '生成纠偏建议' }));
    await waitFor(() => {
      expect(dietApi.getDeviationAnalysis).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: '一键写入下一餐' }));

    await waitFor(() => {
      expect(dietApi.addMealToPlan).toHaveBeenCalledTimes(1);
    });

    expect(vi.mocked(dietApi.addMealToPlan).mock.calls[0]?.[0]).toBe('t1');
    expect(vi.mocked(dietApi.addMealToPlan).mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        plan_date: expect.any(String),
        meal_type: expect.any(String),
        dishes: expect.any(Array),
      })
    );
  });
});
