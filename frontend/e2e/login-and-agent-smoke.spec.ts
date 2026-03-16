import { expect, test } from '@playwright/test';

const username = process.env.E2E_USERNAME;
const password = process.env.E2E_PASSWORD;

test.describe('E2E Smoke', () => {
  test('can login and reach agent chat', async ({ page }) => {
    test.skip(!username || !password, 'E2E credentials are not configured');

    await page.goto('/login');

    await page.getByLabel('Username').fill(username!);
    await page.getByLabel('Password').fill(password!);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page).toHaveURL(/\/agent(\/.*)?$/);

    await expect(
      page.getByPlaceholder('Ask Agent to calculate, analyze, or plan...')
    ).toBeVisible();
  });
});

