import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MarkdownRenderer } from './MarkdownRenderer';

describe('MarkdownRenderer', () => {
  it('renders basic markdown elements and links safely', () => {
    render(
      <MarkdownRenderer
        content={
          [
            '# Title',
            '',
            'Hello **bold** `inline`.',
            '',
            '- item 1',
            '',
            '[Link](https://example.com)',
          ].join('\n')
        }
      />,
    );

    expect(screen.getByRole('heading', { name: 'Title' })).toBeInTheDocument();
    expect(screen.getByText('bold')).toBeInTheDocument();
    expect(screen.getByText('inline')).toBeInTheDocument();

    const link = screen.getByRole('link', { name: 'Link' });
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});

