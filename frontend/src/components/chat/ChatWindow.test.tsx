import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ChatWindow } from './ChatWindow';

describe('ChatWindow', () => {
  it('invokes onSuggestionClick when a suggestion chip is clicked', async () => {
    const onSuggestionClick = vi.fn();
    const user = userEvent.setup();

    render(
      <ChatWindow
        messages={[]}
        isLoading={false}
        onSuggestionClick={onSuggestionClick}
      />,
    );

    await user.click(screen.getByRole('button', { name: /红烧肉怎么做/ }));
    expect(onSuggestionClick).toHaveBeenCalledWith('红烧肉怎么做？');
  });
});

