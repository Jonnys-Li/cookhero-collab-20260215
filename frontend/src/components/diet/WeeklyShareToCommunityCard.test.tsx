import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { WeeklyShareToCommunityCard } from './WeeklyShareToCommunityCard';

vi.mock('../../services/api/community', () => {
  return {
    createCommunityPost: vi.fn(),
    polishCommunityPost: vi.fn(),
  };
});

vi.mock('../../services/api/events', () => {
  return {
    trackEvent: vi.fn(),
  };
});

import * as communityApi from '../../services/api/community';

describe('WeeklyShareToCommunityCard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('shares weekly summary by calling createCommunityPost', async () => {
    const user = userEvent.setup();
    vi.mocked(communityApi.createCommunityPost).mockResolvedValue({});

    render(
      <WeeklyShareToCommunityCard
        token="t1"
        weeklySummary={{
          week_start_date: '2026-03-16',
          week_end_date: '2026-03-22',
          daily_data: {},
          total_calories: 1234,
          total_protein: 100,
          total_fat: 40,
          total_carbs: 150,
          avg_daily_calories: 176,
        }}
      />
    );

    await user.click(screen.getByRole('button', { name: '分享本周' }));

    await waitFor(() => {
      expect(communityApi.createCommunityPost).toHaveBeenCalledTimes(1);
    });

    expect(vi.mocked(communityApi.createCommunityPost).mock.calls[0]?.[0]).toBe('t1');
    expect(vi.mocked(communityApi.createCommunityPost).mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        content: expect.any(String),
        nutrition_snapshot: expect.any(Object),
      })
    );
  });
});

