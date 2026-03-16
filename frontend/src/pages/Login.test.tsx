import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import LoginPage from './Login';

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
}));

vi.mock('../contexts', () => ({
  useAuth: () => ({ login: mocks.login }),
}));

describe('LoginPage', () => {
  it('shows a validation error when username/password are missing', async () => {
    mocks.login.mockReset();
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(
      screen.getByText('Username and password are required.'),
    ).toBeInTheDocument();
    expect(mocks.login).not.toHaveBeenCalled();
  });
});

