import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CommunityPostDetailPage from './CommunityPostDetail';

const mocks = vi.hoisted(() => ({
  getCommunityPostDetail: vi.fn(),
  addCommunityComment: vi.fn(),
}));

vi.mock('../../contexts', () => ({
  useAuth: () => ({ token: 'token-test' }),
}));

vi.mock('../../services/api/community', () => ({
  addCommunityComment: (...args: any[]) => mocks.addCommunityComment(...args),
  getCommunityPostDetail: (...args: any[]) => mocks.getCommunityPostDetail(...args),
  suggestCommunityReply: vi.fn(),
  toggleCommunityReaction: vi.fn(),
}));

describe('CommunityPostDetailPage', () => {
  beforeEach(() => {
    mocks.getCommunityPostDetail.mockReset();
    mocks.addCommunityComment.mockReset();

    mocks.getCommunityPostDetail.mockResolvedValue({
      post: {
        id: 'p1',
        user_id: 'u1',
        author_display_name: '匿名小厨0001',
        is_anonymous: true,
        post_type: 'check_in',
        mood: 'neutral',
        content: 'hello',
        tags: [],
        image_urls: [],
        nutrition_snapshot: null,
        like_count: 0,
        comment_count: 0,
        liked_by_me: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      comments: [],
    });

    mocks.addCommunityComment.mockResolvedValue({
      id: 'c1',
      post_id: 'p1',
      user_id: 'u1',
      author_display_name: '匿名小厨0002',
      is_anonymous: true,
      content: 'x',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  it('fills comment box when clicking a chip, allows editing, and sends successfully', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/community/p1']}>
        <Routes>
          <Route path="/community/:id" element={<CommunityPostDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mocks.getCommunityPostDetail).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: '我懂你现在很难，先抱抱你。' }));

    const textarea = screen.getByPlaceholderText('写一句支持的话...') as HTMLTextAreaElement;
    expect(textarea.value).toBe('我懂你现在很难，先抱抱你。');

    await user.type(textarea, ' 我也经历过，慢慢来。');
    await user.click(screen.getByRole('button', { name: /发布评论/i }));

    await waitFor(() => {
      expect(mocks.addCommunityComment).toHaveBeenCalledWith(
        'token-test',
        'p1',
        expect.objectContaining({
          content: '我懂你现在很难，先抱抱你。 我也经历过，慢慢来。',
          is_anonymous: true,
        })
      );
    });
  });
});

