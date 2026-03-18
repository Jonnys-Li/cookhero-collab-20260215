import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { CalorieGoalSourceCard } from './CalorieGoalSourceCard';

describe('CalorieGoalSourceCard', () => {
  it('explains when explicit goal is aligned with metabolic estimate', () => {
    render(
      <CalorieGoalSourceCard
        budgetSnapshot={{
          date: '2026-03-18',
          base_goal: 2220,
          effective_goal: 2220,
          today_adjustment: 0,
          goal_source: 'explicit',
        }}
        preference={{
          id: 'p1',
          user_id: 'u1',
          calorie_goal: 2220,
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
          created_at: '2026-03-18T00:00:00Z',
          updated_at: '2026-03-18T00:00:00Z',
        }}
      />
    );

    expect(screen.getByText('代谢画像估算目标')).toBeInTheDocument();
    expect(screen.getByText('当前基线目标已经和代谢画像估算值对齐。')).toBeInTheDocument();
    expect(screen.getByText('BMR 1720 / TDEE 2670')).toBeInTheDocument();
    expect(screen.getByText(/当前画像：28 岁 · 男 · 178 cm · 76 kg · 中等活动 · 减脂/)).toBeInTheDocument();
  });

  it('explains avg7d fallback and keeps metabolic estimate as reference', () => {
    render(
      <CalorieGoalSourceCard
        budgetSnapshot={{
          date: '2026-03-18',
          base_goal: 1910,
          effective_goal: 1910,
          today_adjustment: 0,
          goal_source: 'avg7d',
        }}
        preference={{
          id: 'p2',
          user_id: 'u2',
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
          created_at: '2026-03-18T00:00:00Z',
          updated_at: '2026-03-18T00:00:00Z',
        }}
      />
    );

    expect(screen.getByText('近 7 天均值')).toBeInTheDocument();
    expect(
      screen.getByText('当前基线目标来自最近 7 天平均摄入，是未设固定目标时的自动估算。')
    ).toBeInTheDocument();
    expect(screen.getByText('1770 kcal')).toBeInTheDocument();
  });

  it('explains tdee_estimate as a first-class goal source', () => {
    render(
      <CalorieGoalSourceCard
        budgetSnapshot={{
          date: '2026-03-18',
          base_goal: 2310,
          effective_goal: 2310,
          today_adjustment: 0,
          goal_source: 'tdee_estimate',
        }}
        preference={{
          id: 'p3',
          user_id: 'u3',
          calorie_goal: 2310,
          metabolic_profile: {
            age: 30,
            biological_sex: 'male',
            height_cm: 180,
            weight_kg: 80,
            activity_level: 'moderate',
            goal_intent: 'fat_loss',
          },
          metabolic_estimate: {
            formula: 'mifflin_st_jeor',
            bmr_kcal: 1780,
            tdee_kcal: 2760,
            activity_factor: 1.55,
            goal_adjustment_kcal: -450,
            recommended_calorie_goal: 2310,
            goal_intent: 'fat_loss',
            is_complete: true,
          },
          created_at: '2026-03-18T00:00:00Z',
          updated_at: '2026-03-18T00:00:00Z',
        }}
      />
    );

    expect(screen.getByText('TDEE 估算目标')).toBeInTheDocument();
    expect(screen.getByText('当前基线目标来自代谢画像估算（BMR / TDEE）。')).toBeInTheDocument();
  });

  it('explains default1800 fallback when no individualized goal exists', () => {
    render(
      <CalorieGoalSourceCard
        budgetSnapshot={{
          date: '2026-03-18',
          base_goal: 1800,
          effective_goal: 1800,
          today_adjustment: 0,
          goal_source: 'default1800',
        }}
        preference={{
          id: 'p4',
          user_id: 'u4',
          created_at: '2026-03-18T00:00:00Z',
          updated_at: '2026-03-18T00:00:00Z',
        }}
      />
    );

    expect(screen.getByText('系统默认值')).toBeInTheDocument();
    expect(screen.getByText('当前基线目标还没有个体化设定，系统先用默认 1800 kcal 兜底。')).toBeInTheDocument();
  });
});
