import { test } from '@playwright/test'

// Visual check helper: saves screenshots of each screen to $SHOTS (skipped unless set).
test('screens', async ({ page }, info) => {
  const dir = process.env.SHOTS
  test.skip(!dir, 'set SHOTS to a folder to capture screenshots')
  const shot = (n: string) => page.screenshot({ path: `${dir}/${info.project.name}-${n}.png`, fullPage: true })
  await page.goto('/')
  await shot('1-welcome')
  await page.getByRole('button', { name: 'Get started' }).click()
  await shot('2-upload')
})
