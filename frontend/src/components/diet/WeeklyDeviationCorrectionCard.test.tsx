import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { WeeklyDeviationCorrectionCard } from './WeeklyDeviationCorrectionCard';

vi.mock('../../services/api/diet', () => {
  return {
    getReplanPreview: vi.fn(),
    applyReplan: vi.fn(),
  };
});

vi.mock('../../services/api/events', () => {
  return {
    trackEvent: vi.fn(),
  };
});

import * as dietApi from '../../services/api/diet';

const weeklySummary = {
  week_start_date: '2026-03-16',
  week_end_date: '2026-03-22',
  daily_data: {},
  total_calories: 4200,
  total_protein: 320,
  total_fat: 160,
  total_carbs: 480,
  avg_daily_calories: 600,
};

const previewResponse = {
  week_start_date: '2026-03-16',
  affected_days: ['2026-03-19', '2026-03-20'],
  before_summary: {
    total_deviation: 240,
  },
  after_summary: {
    applied_shift: -180,
  },
  meal_changes: [
    {
      meal_id: 'meal-1',
      plan_date: '2026-03-19',
      meal_type: 'dinner',
      old_total_calories: 680,
      new_total_calories: 520,
      delta_calories: -160,
    },
  ],
  write_conflicts: [
    {
      plan_date: '2026-03-20',
      meal_type: 'lunch',
      reason: '该餐次已存在日志关联，已跳过。',
    },
  ],
  compensation_summary: '未来餐次可调整空间有限，建议补 1-2 次轻量运动帮助回到节奏。',
  compensation_suggestions: [
    {
      title: '晚饭后快走',
      minutes: 30,
      estimated_kcal_burn: 130,
      intensity: 'low_impact',
      reason: '优先稳态活动，帮助消化并降低补偿性节食的冲动。',
    },
  ],
};

describe('WeeklyDeviationCorrectionCard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('loads rolling replan preview on mount', async () => {
    vi.mocked(dietApi.getReplanPreview).mockResolvedValue(previewResponse);

    render(
      <WeeklyDeviationCorrectionCard
        token="t1"
        weekStartDate="2026-03-16"
        weeklySummary={weeklySummary}
        planMeals={[]}
      />
    );

    await waitFor(() => {
      expect(dietApi.getReplanPreview).toHaveBeenCalledWith('t1', '2026-03-16');
    });

    expect(await screen.findByText('2026-03-19 · 晚餐 · 680 → 520 kcal')).toBeInTheDocument();
    expect(screen.getByText('该餐次已存在日志关联，已跳过。')).toBeInTheDocument();
    expect(screen.getByText('训练 / 运动补偿建议')).toBeInTheDocument();
    expect(screen.getByText('晚饭后快走 · 30 分钟')).toBeInTheDocument();
  });

  it('applies rolling replan via applyReplan', async () => {
    const user = userEvent.setup();
    const onApplied = vi.fn().mockResolvedValue(undefined);
    vi.mocked(dietApi.getReplanPreview)
      .mockResolvedValueOnce(previewResponse)
      .mockResolvedValueOnce({
        ...previewResponse,
        meal_changes: [],
        write_conflicts: [],
      });
    vi.mocked(dietApi.applyReplan).mockResolvedValue({
      action: 'applied_weekly_replan',
      applied_count: 1,
      updated_meal_ids: ['meal-1'],
      write_conflicts: [],
    });

    render(
      <WeeklyDeviationCorrectionCard
        token="t1"
        weekStartDate="2026-03-16"
        weeklySummary={weeklySummary}
        planMeals={[]}
        onApplied={onApplied}
      />
    );

    await screen.findByText('2026-03-19 · 晚餐 · 680 → 520 kcal');
    await user.click(screen.getByRole('button', { name: '应用到计划' }));

    await waitFor(() => {
      expect(dietApi.applyReplan).toHaveBeenCalledWith('t1', previewResponse.meal_changes);
    });

    expect(onApplied).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(dietApi.getReplanPreview).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByText('当前没有可安全调整的未来餐次。')).toBeInTheDocument();
  });

  it('shows compatibility copy when backend has not deployed the new endpoint yet', async () => {
    vi.mocked(dietApi.getReplanPreview).mockResolvedValue({
      week_start_date: '2026-03-16',
      affected_days: [],
      before_summary: {
        fallback_mode: 'legacy_backend',
        fallback_message: '当前线上后端还没补齐新版自动调整接口，本周先保持现有计划不变。',
      },
      after_summary: {
        applied_shift: 0,
      },
      meal_changes: [],
      write_conflicts: [],
      compensation_suggestions: [],
    });

    render(
      <WeeklyDeviationCorrectionCard
        token="t1"
        weekStartDate="2026-03-16"
        weeklySummary={weeklySummary}
        planMeals={[]}
      />
    );

    expect(
      await screen.findByText('当前线上后端还没补齐新版自动调整接口，本周先保持现有计划不变。')
    ).toBeInTheDocument();
    expect(
      screen.getByText('当前线上版本先按现有计划执行，等后端补齐后这里会恢复自动调整。')
    ).toBeInTheDocument();
  });
});
