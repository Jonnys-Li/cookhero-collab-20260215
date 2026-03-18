import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DietPreferencesForm } from './DietPreferencesForm';
import { trackEvent } from '../../services/api/events';

vi.mock('../../services/api/diet', () => {
  return {
    getPreferences: vi.fn(),
    updatePreferences: vi.fn(),
  };
});

vi.mock('../../services/api/events', () => {
  return {
    trackEvent: vi.fn(),
  };
});

import * as dietApi from '../../services/api/diet';

describe('DietPreferencesForm', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });
  afterEach(() => {
    cleanup();
  });

  it('submits preferences and shows success message', async () => {
    const user = userEvent.setup();
    vi.mocked(dietApi.getPreferences).mockResolvedValue({
      preference: {
        id: 'p1',
        user_id: 'u1',
        avoided_foods: ['奶茶'],
        stats: {},
        created_at: '2026-03-17T00:00:00Z',
        updated_at: '2026-03-17T00:00:00Z',
      },
    });
    vi.mocked(dietApi.updatePreferences).mockResolvedValue({
      preference: {
        id: 'p1',
        user_id: 'u1',
        avoided_foods: ['奶茶', '油炸'],
        stats: {
          goals: {
            calorie_goal: 2310,
          },
          metabolic_profile: {
            age: 28,
            biological_sex: 'male',
            height_cm: 178,
            weight_kg: 76,
            activity_level: 'moderate',
            goal_intent: 'fat_loss',
          },
        },
        calorie_goal: 2310,
        metabolic_profile: {
          age: 28,
          biological_sex: 'male',
          height_cm: 178,
          weight_kg: 76,
          activity_level: 'moderate',
          goal_intent: 'fat_loss',
        },
        metabolic_estimate: {
          formula: 'mifflin_st_jeor',
          bmr_kcal: 1720,
          tdee_kcal: 2670,
          activity_factor: 1.55,
          goal_adjustment_kcal: -450,
          recommended_calorie_goal: 2220,
          goal_intent: 'fat_loss',
          is_complete: true,
        },
        created_at: '2026-03-17T00:00:00Z',
        updated_at: '2026-03-17T00:00:00Z',
      },
    });

    render(<DietPreferencesForm token="t1" />);

    await waitFor(() => {
      expect(dietApi.getPreferences).toHaveBeenCalledTimes(1);
    });

    const avoided = screen.getByPlaceholderText('例如：奶茶, 油炸');
    await user.clear(avoided);
    await user.type(avoided, '奶茶, 油炸');

    const calorie = screen.getByPlaceholderText('例如 1800');
    await user.type(calorie, '1800');
    await user.type(screen.getByLabelText('年龄'), '28');
    await user.selectOptions(screen.getByLabelText('生理性别'), 'male');
    await user.type(screen.getByLabelText('身高 (cm)'), '178');
    await user.type(screen.getByLabelText('体重 (kg)'), '76');
    await user.selectOptions(screen.getByLabelText('活动水平'), 'moderate');
    await user.selectOptions(screen.getByLabelText('当前目标方向'), 'fat_loss');
    await user.click(screen.getByLabelText('保存时用建议目标覆盖当前热量目标'));

    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(dietApi.updatePreferences).toHaveBeenCalledTimes(1);
    });

    expect(dietApi.updatePreferences).toHaveBeenCalledWith('t1', {
      dietary_restrictions: [],
      allergies: [],
      favorite_cuisines: [],
      avoided_foods: ['奶茶', '油炸'],
      calorie_goal: 1800,
      protein_goal: undefined,
      fat_goal: undefined,
      carbs_goal: undefined,
      age: 28,
      biological_sex: 'male',
      height_cm: 178,
      weight_kg: 76,
      activity_level: 'moderate',
      goal_intent: 'fat_loss',
      use_estimated_calorie_goal: true,
    });
    expect(screen.getByRole('status')).toHaveTextContent('已保存饮食偏好');
    expect(screen.getAllByText('2220 kcal').length).toBeGreaterThan(0);
    expect(trackEvent).toHaveBeenCalledWith(
      't1',
      'diet_preferences_updated',
      expect.objectContaining({
        has_metabolic_profile: true,
        has_calorie_goal: true,
      })
    );
  });

  it('shows error message when update fails', async () => {
    const user = userEvent.setup();
    vi.mocked(dietApi.getPreferences).mockResolvedValue({ preference: null });
    vi.mocked(dietApi.updatePreferences).mockRejectedValue(
      new Error('代谢画像未填写完整，无法根据 BMR/TDEE 自动估算热量目标')
    );

    render(<DietPreferencesForm token="t1" />);
    await waitFor(() => {
      expect(dietApi.getPreferences).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(dietApi.updatePreferences).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByRole('alert')).toHaveTextContent(
      '代谢画像未填写完整，无法根据 BMR/TDEE 自动估算热量目标'
    );
  });

  it('renders metabolic estimate returned from preferences API', async () => {
    vi.mocked(dietApi.getPreferences).mockResolvedValue({
      preference: {
        id: 'p2',
        user_id: 'u2',
        avoided_foods: [],
        stats: {
          metabolic_profile: {
            age: 31,
            biological_sex: 'female',
            height_cm: 165,
            weight_kg: 58,
            activity_level: 'light',
            goal_intent: 'maintain',
          },
        },
        metabolic_profile: {
          age: 31,
          biological_sex: 'female',
          height_cm: 165,
          weight_kg: 58,
          activity_level: 'light',
          goal_intent: 'maintain',
        },
        metabolic_estimate: {
          formula: 'mifflin_st_jeor',
          bmr_kcal: 1290,
          tdee_kcal: 1770,
          activity_factor: 1.375,
          goal_adjustment_kcal: 0,
          recommended_calorie_goal: 1770,
          goal_intent: 'maintain',
          is_complete: true,
        },
        created_at: '2026-03-17T00:00:00Z',
        updated_at: '2026-03-17T00:00:00Z',
      },
    });
    vi.mocked(dietApi.updatePreferences).mockResolvedValue({
      preference: {
        id: 'p2',
        user_id: 'u2',
        avoided_foods: [],
        stats: {},
        created_at: '2026-03-17T00:00:00Z',
        updated_at: '2026-03-17T00:00:00Z',
      },
    });

    render(<DietPreferencesForm token="t2" />);

    await waitFor(() => {
      expect(dietApi.getPreferences).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText('当前生效目标说明')).toBeInTheDocument();
    expect(screen.getByText('估算代谢目标')).toBeInTheDocument();
    expect(screen.getAllByText('1770 kcal').length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue('31')).toBeInTheDocument();
  });
});
