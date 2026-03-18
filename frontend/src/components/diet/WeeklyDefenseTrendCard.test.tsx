import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WeeklyDefenseTrendCard } from './WeeklyDefenseTrendCard';

describe('WeeklyDefenseTrendCard', () => {
  it('renders daily intake, goal, exemption marker and source lane', () => {
    render(
      <WeeklyDefenseTrendCard
        summary={{
          week_start_date: '2026-03-16',
          week_end_date: '2026-03-22',
          daily_data: {
            '2026-03-16': { calories: 1800, protein: 120, fat: 60, carbs: 180, meals: ['lunch'] },
            '2026-03-17': { calories: 2050, protein: 130, fat: 65, carbs: 220, meals: ['dinner'] },
            '2026-03-18': { calories: 2250, protein: 110, fat: 78, carbs: 240, meals: ['lunch', 'dinner'] },
          },
          total_calories: 6100,
          total_protein: 360,
          total_fat: 203,
          total_carbs: 640,
          avg_daily_calories: 2033,
          goal_source: 'tdee_estimate',
          base_goal: 2000,
          effective_goal: 2150,
          weekly_goal_gap: 250,
          emotion_exemption: {
            active: true,
            date: '2026-03-18',
            summary: '豁免',
          },
        } as never}
        budgetSnapshot={{
          date: '2026-03-18',
          base_goal: 2000,
          effective_goal: 2150,
          goal_source: 'tdee_estimate',
          emotion_exemption: {
            active: true,
            date: '2026-03-18',
            summary: '豁免',
          },
        }}
      />
    );

    expect(screen.getByText('一周趋势总览')).toBeInTheDocument();
    expect(screen.getByText('周偏差 +250 kcal')).toBeInTheDocument();
    expect(screen.getByText('偏差 +100 kcal')).toBeInTheDocument();
    expect(screen.getByText('偏差 -200 kcal')).toBeInTheDocument();
    expect(screen.getAllByText('代谢').length).toBeGreaterThan(0);
    expect(screen.getByText('豁免')).toBeInTheDocument();
  });
});
