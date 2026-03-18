import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WeeklyGoalTrendCard } from './WeeklyGoalTrendCard';

describe('WeeklyGoalTrendCard', () => {
  it('renders actual/target/deviation rows with goal-source and exemption markers', () => {
    render(
      <WeeklyGoalTrendCard
        weeklySummary={{
          week_start_date: '2026-03-16',
          week_end_date: '2026-03-22',
          daily_data: {
            '2026-03-16': { calories: 1820, protein: 120, fat: 60, carbs: 180, meals: ['breakfast'] },
            '2026-03-17': { calories: 2310, protein: 135, fat: 72, carbs: 210, meals: ['lunch'] },
          },
          total_calories: 4130,
          total_protein: 255,
          total_fat: 132,
          total_carbs: 390,
          avg_daily_calories: 590,
          goal_source: 'tdee_estimate',
          weekly_goal_calories: 16170,
          weekly_goal_gap: -12040,
          daily_budget_timeline: [
            {
              date: '2026-03-16',
              base_goal: 2310,
              effective_goal: 2310,
              goal_source: 'avg7d',
              goal_seeded: true,
              emotion_exemption: { date: '2026-03-16', active: false },
            },
            {
              date: '2026-03-17',
              base_goal: 2310,
              effective_goal: 2310,
              goal_source: 'tdee_estimate',
              goal_seeded: false,
              emotion_exemption: { date: '2026-03-17', active: true, summary: '暂停预算调整' },
            },
            {
              date: '2026-03-18',
              base_goal: 2310,
              effective_goal: 2310,
              goal_source: 'tdee_estimate',
              goal_seeded: false,
              emotion_exemption: { date: '2026-03-18', active: false },
            },
            {
              date: '2026-03-19',
              base_goal: 2310,
              effective_goal: 2310,
              goal_source: 'tdee_estimate',
              goal_seeded: false,
              emotion_exemption: { date: '2026-03-19', active: false },
            },
            {
              date: '2026-03-20',
              base_goal: 2310,
              effective_goal: 2310,
              goal_source: 'tdee_estimate',
              goal_seeded: false,
              emotion_exemption: { date: '2026-03-20', active: false },
            },
            {
              date: '2026-03-21',
              base_goal: 2310,
              effective_goal: 2310,
              goal_source: 'tdee_estimate',
              goal_seeded: false,
              emotion_exemption: { date: '2026-03-21', active: false },
            },
            {
              date: '2026-03-22',
              base_goal: 2310,
              effective_goal: 2310,
              goal_source: 'tdee_estimate',
              goal_seeded: false,
              emotion_exemption: { date: '2026-03-22', active: false },
            },
          ],
        }}
      />
    );

    expect(screen.getByText('周趋势视图')).toBeInTheDocument();
    expect(screen.getByText('实际摄入')).toBeInTheDocument();
    expect(screen.getByText('基线目标')).toBeInTheDocument();
    expect(screen.getByText('当日偏差')).toBeInTheDocument();
    expect(screen.getByText('来源切换')).toBeInTheDocument();
    expect(screen.getByText('情绪保护期')).toBeInTheDocument();
    expect(screen.getAllByText('TDEE 估算').length).toBeGreaterThan(0);
  });
});
