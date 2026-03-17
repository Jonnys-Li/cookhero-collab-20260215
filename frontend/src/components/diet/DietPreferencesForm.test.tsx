import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DietPreferencesForm } from './DietPreferencesForm';

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
        stats: {},
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

    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(dietApi.updatePreferences).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByRole('status')).toHaveTextContent('已保存饮食偏好');
  });

  it('shows error message when update fails', async () => {
    const user = userEvent.setup();
    vi.mocked(dietApi.getPreferences).mockResolvedValue({ preference: null });
    vi.mocked(dietApi.updatePreferences).mockRejectedValue(new Error('Failed to update preferences'));

    render(<DietPreferencesForm token="t1" />);
    await waitFor(() => {
      expect(dietApi.getPreferences).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(dietApi.updatePreferences).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Failed to update preferences');
  });
});
