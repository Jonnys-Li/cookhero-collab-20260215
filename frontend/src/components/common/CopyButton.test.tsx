import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CopyButton } from './CopyButton';

describe('CopyButton', () => {
  it('writes content to clipboard and toggles copied state', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    render(<CopyButton content="hello" />);

    await user.click(screen.getByRole('button', { name: /copy to clipboard/i }));
    expect(writeText).toHaveBeenCalledWith('hello');

    expect(screen.getByRole('button', { name: /copied/i })).toBeInTheDocument();
  });
});
