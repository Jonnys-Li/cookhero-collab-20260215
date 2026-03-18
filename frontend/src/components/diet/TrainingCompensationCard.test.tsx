import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { TrainingCompensationCard } from './TrainingCompensationCard';

describe('TrainingCompensationCard', () => {
  it('prefers backend suggestion when provided', () => {
    render(
      <TrainingCompensationCard
        summary={{
          week_start_date: '2026-03-16',
          week_end_date: '2026-03-22',
          daily_data: {},
          total_calories: 4300,
          total_protein: 300,
          total_fat: 150,
          total_carbs: 520,
          avg_daily_calories: 614,
          training_suggestion: {
            title: '训练日建议温和补偿',
            description: '后端建议今天只加 20 分钟低冲击有氧。',
            focus: '先保证晚餐蛋白与补水，不需要额外扣热量。',
            source_label: '后端 suggestion',
          },
        } as never}
        budgetSnapshot={null}
        preference={null}
      />
    );

    expect(screen.getByText('训练日建议温和补偿')).toBeInTheDocument();
    expect(screen.getByText('后端建议今天只加 20 分钟低冲击有氧。')).toBeInTheDocument();
    expect(screen.getByText('后端 suggestion')).toBeInTheDocument();
  });

  it('falls back to emotion-safe guidance when exemption is active', () => {
    render(
      <TrainingCompensationCard
        summary={{
          week_start_date: '2026-03-16',
          week_end_date: '2026-03-22',
          daily_data: {},
          total_calories: 4300,
          total_protein: 300,
          total_fat: 150,
          total_carbs: 520,
          avg_daily_calories: 614,
          emotion_exemption: {
            active: true,
            date: '2026-03-18',
            summary: '今天是恢复优先日',
          },
        }}
        budgetSnapshot={{
          date: '2026-03-18',
          effective_goal: 2100,
          emotion_exemption: {
            active: true,
            date: '2026-03-18',
            summary: '今天是恢复优先日',
          },
        }}
        preference={null}
      />
    );

    expect(screen.getByText('今天先稳住节奏，不做补偿训练')).toBeInTheDocument();
    expect(screen.getByText('今天是恢复优先日')).toBeInTheDocument();
    expect(screen.getByText(/10-20 分钟轻步行、舒缓拉伸或呼吸放松/)).toBeInTheDocument();
  });
});
