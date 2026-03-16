import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { Message } from '../../types';
import { MessageBubble } from './MessageBubble';

describe('MessageBubble', () => {
  it('renders assistant message with intent and grouped sources', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    const message: Message = {
      id: 'm1',
      role: 'assistant',
      content: 'Hi there',
      timestamp: new Date('2026-03-16T00:00:00Z'),
      intent: { need_rag: true, intent: 'recipe_search', reason: 'x' },
      sources: [
        { type: 'rag', info: 'doc: how-to-cook' },
        { type: 'web', info: 'example.com', url: 'https://example.com' },
      ],
      thinkingStartTime: 1,
      thinkingEndTime: 1001,
      answerStartTime: 1001,
      answerEndTime: 1501,
    };

    render(<MessageBubble message={message} />);

    expect(screen.getByText(/知识库检索/)).toBeInTheDocument();
    expect(screen.getByText(/菜谱搜索/)).toBeInTheDocument();

    expect(screen.getByText('📚 知识库来源：')).toBeInTheDocument();
    expect(screen.getByText('🌐 网络来源：')).toBeInTheDocument();

    const webLink = screen.getByRole('link', { name: /example\.com/ });
    expect(webLink).toHaveAttribute('href', 'https://example.com');

    await user.click(screen.getByRole('button', { name: /copy to clipboard/i }));
    expect(writeText).toHaveBeenCalledWith('Hi there');
  });

  it('shows a thinking block and hides text while streaming without content', () => {
    const message: Message = {
      id: 'm2',
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      thinking: ['step a'],
    };

    render(<MessageBubble message={message} />);

    expect(screen.getByText('Thinking Process')).toBeInTheDocument();
    expect(screen.getByText('step a')).toBeInTheDocument();
  });
});
