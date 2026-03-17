import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PhotoLogModal } from './PhotoLogModal';

vi.mock('../../services/api/diet', () => {
  return {
    parseDietLog: vi.fn(),
    createLog: vi.fn(),
    createLogFromText: vi.fn(),
  };
});

vi.mock('../../services/api/events', () => {
  return {
    trackEvent: vi.fn(),
  };
});

import * as dietApi from '../../services/api/diet';

class MockFileReader {
  result: string | ArrayBuffer | null = null;
  onload: null | (() => void) = null;
  onerror: null | (() => void) = null;
  readAsDataURL() {
    this.result = 'data:image/png;base64,AAAA';
    this.onload?.();
  }
}

describe('PhotoLogModal', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // @ts-expect-error - test shim
    globalThis.FileReader = MockFileReader;
  });

  afterEach(() => {
    cleanup();
  });

  it('opens and triggers parseDietLog on recognize', async () => {
    const user = userEvent.setup();
    vi.mocked(dietApi.parseDietLog).mockResolvedValue({
      items: [{ food_name: '牛肉面', calories: 500 }],
      meal_type: 'lunch',
    });

    render(
      <PhotoLogModal
        isOpen
        onClose={() => {}}
        token="t1"
        defaultDate={new Date('2026-03-17T00:00:00')}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['x'], 'a.png', { type: 'image/png' });
    await user.upload(input, file);

    await user.click(screen.getByRole('button', { name: '开始识别' }));

    await waitFor(() => {
      expect(dietApi.parseDietLog).toHaveBeenCalledTimes(1);
    });
  });

  it('confirms save and calls createLog', async () => {
    const user = userEvent.setup();
    vi.mocked(dietApi.parseDietLog).mockResolvedValue({
      items: [{ food_name: '牛肉面', calories: 500 }],
      meal_type: 'lunch',
    });
    vi.mocked(dietApi.createLog).mockResolvedValue({
      id: 'l1',
      user_id: 'u1',
      log_date: '2026-03-17',
      meal_type: 'lunch',
      total_calories: 500,
      total_protein: 0,
      total_fat: 0,
      total_carbs: 0,
      notes: '',
      items: [],
      created_at: '2026-03-17T00:00:00Z',
      updated_at: '2026-03-17T00:00:00Z',
    });

    render(
      <PhotoLogModal
        isOpen
        onClose={() => {}}
        token="t1"
        defaultDate={new Date('2026-03-17T00:00:00')}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['x'], 'a.png', { type: 'image/png' });
    await user.upload(input, file);

    await user.click(screen.getByRole('button', { name: '开始识别' }));
    await waitFor(() => {
      expect(dietApi.parseDietLog).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole('button', { name: '确认写入' }));

    await waitFor(() => {
      expect(dietApi.createLog).toHaveBeenCalledTimes(1);
    });
  });
});
