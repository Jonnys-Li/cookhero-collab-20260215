import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CommunityFeedPage from './CommunityFeed';

const mocks = vi.hoisted(() => ({
  getCommunityFeed: vi.fn(),
  getCapabilities: vi.fn(),
}));

vi.mock('../../contexts', () => ({
  useAuth: () => ({ token: 'token-test' }),
}));

vi.mock('../../services/api/community', () => ({
  getCommunityFeed: (...args: any[]) => mocks.getCommunityFeed(...args),
  suggestCommunityCard: vi.fn(),
  toggleCommunityReaction: vi.fn(),
}));

vi.mock('../../services/api/meta', () => ({
  getCapabilities: (...args: any[]) => mocks.getCapabilities(...args),
}));

vi.mock('./CreatePostModal', () => ({
  CreatePostModal: () => null,
}));

describe('CommunityFeedPage', () => {
  beforeEach(() => {
    mocks.getCommunityFeed.mockReset();
    mocks.getCapabilities.mockReset();
    mocks.getCommunityFeed.mockResolvedValue({ posts: [], total: 0 });
    mocks.getCapabilities.mockResolvedValue({ community_ai_modes: [] });
  });

  it('requests need_support feed when switching to the tab', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/community']}>
        <CommunityFeedPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mocks.getCommunityFeed).toHaveBeenCalled();
    });
    expect(mocks.getCommunityFeed).toHaveBeenLastCalledWith(
      'token-test',
      expect.objectContaining({ sort: 'latest' })
    );

    await user.click(screen.getByRole('button', { name: '需要支持' }));

    await waitFor(() => {
      expect(mocks.getCommunityFeed).toHaveBeenLastCalledWith(
        'token-test',
        expect.objectContaining({ sort: 'need_support' })
      );
    });
  });
});

