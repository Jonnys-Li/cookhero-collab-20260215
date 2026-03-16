import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ThinkingBlock } from './ThinkingBlock';

describe('ThinkingBlock', () => {
  it('renders steps while thinking and auto-collapses when done', async () => {
    const { rerender } = render(
      <ThinkingBlock steps={['step 1']} isThinking={true} />,
    );

    expect(screen.getByText('Thinking Process')).toBeInTheDocument();
    expect(screen.getByText('step 1')).toBeInTheDocument();

    rerender(
      <ThinkingBlock steps={['step 1']} isThinking={false} thinkingDuration={1200} />,
    );

    await waitFor(() => {
      expect(screen.queryByText('step 1')).not.toBeInTheDocument();
    });

    // Duration hint should be shown when thinking is done and no error was raised.
    expect(screen.getByText(/\(1\.2s\)/)).toBeInTheDocument();
  });
});

