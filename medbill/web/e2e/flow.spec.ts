import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const SAMPLES = fileURLToPath(new URL('../../data/samples', import.meta.url))

async function start(page: Page, sample: string, language = 'English') {
  await page.goto('/')
  if (language !== 'English') {
    await page.locator('#language-text').fill(language === 'Español' ? 'Quiero entender mi factura' : 'Би нэхэмжлэхээ ойлгохыг хүсэж байна')
    await page.getByRole('button', { name: 'Send', exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('lang', language === 'Español' ? 'es' : 'mn')
  }
  await page.getByRole('button', { name: /^(Get started|Comenzar|Эхлэх)$/ }).click()
  await page.getByTestId(`sample-${sample}`).click()
  await page.getByTestId('looks-right').waitFor()
}
const toResults = async (page: Page) => {
  await page.getByTestId('looks-right').click()
  await page.getByTestId('headline').waitFor()
}

for (const locale of [
  { code: 'fr', direction: 'ltr', text: 'Je veux comprendre ma facture', title: 'Comprendre votre facture' },
  { code: 'ps', direction: 'rtl', text: 'زه غواړم خپل بل وپېژنم', title: 'خپل بل وپېژنئ' },
  { code: 'ja', direction: 'ltr', text: '請求書について質問したいです', title: '医療費の請求書を理解する' },
  { code: 'es-MX', direction: 'ltr', text: 'Quiero entender mi factura', title: '' },
]) {
  test(`automatic locale response supports ${locale.code}`, async ({ page }) => {
    await page.route('**/api/language', async (route) => {
      await route.fulfill({ json: { language: locale.code, strings: locale.title ? { welcomeTitle: locale.title } : {} } })
    })
    await page.goto('/')
    await page.locator('#language-text').fill(locale.text)
    await page.getByRole('button', { name: 'Send', exact: true }).click()
    await expect(page.locator('html')).toHaveAttribute('lang', locale.code)
    await expect(page.locator('html')).toHaveAttribute('dir', locale.direction)
    if (locale.title) await expect(page.getByRole('heading', { level: 1 })).toHaveText(locale.title)
    else await expect(page.getByRole('button', { name: 'Comenzar', exact: true })).toBeVisible()
    if (locale.code === 'ps') {
      await page.getByRole('button', { name: 'Get started', exact: true }).click()
      await page.getByTestId('sample-overcharge').click()
      await page.getByTestId('looks-right').waitFor()
      await toResults(page)
      await expect(page.getByTestId('headline')).toContainText('$412.00')
      await page.getByRole('button', { name: 'Write the letter', exact: true }).click()
      await expect(page.locator('pre[lang="en"]').first()).toHaveAttribute('dir', 'ltr')
    }
  })
}

test('overcharge sample: total, three findings, evidence highlight, ask, letter', async ({ page }) => {
  await start(page, 'overcharge')
  await toResults(page)
  await expect(page.getByTestId('headline')).toContainText('You may be overcharged $412.00')
  await expect(page.locator('article')).toHaveCount(3)
  await expect(page.getByText('Definite').first()).toBeVisible()
  await expect(page.getByText('Likely')).toBeVisible()

  // Evidence: highlights the bill line, and the EOB line on the other tab.
  await page.getByTestId('evidence-eob_mismatch').click()
  await expect(page.getByTestId('highlight-B5')).toBeVisible()
  await page.getByRole('tab', { name: /Insurance statement/ }).click()
  await expect(page.getByTestId('highlight-E4')).toBeVisible()

  // Ask: grounded answer with citations that jump back to the evidence.
  await page.getByRole('button', { name: 'Ask a question' }).click()
  await page.getByRole('button', { name: 'How much do I actually owe?' }).click()
  const answer = page.getByTestId('msg-assistant').first()
  await expect(answer).toContainText('$412.00')
  await answer.getByTestId('citation').first().click()
  await expect(page.getByTestId('headline')).toContainText('$412.00')
  await expect(page.locator('[data-testid^=highlight-]').first()).toBeVisible()
  await page.getByRole('button', { name: 'Ask a question' }).click()
  await expect(page.getByRole('heading', { name: 'Ask about your bill' })).toBeVisible()
  await expect(page.getByTestId('msg-assistant')).toHaveCount(1) // history survived the jump to the evidence
  await page.getByLabel('Type your question').fill('Will my insurance cover my next surgery?')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByTestId('msg-assistant').last()).toContainText('do not show that information')

  // Letter
  await page.getByRole('button', { name: 'Write the letter' }).click()
  await expect(page.getByTestId('letter-english')).toContainText('Total amount in question: $412.00')
  await page.getByLabel('Your name').fill('Ana Diaz')
  await expect(page.getByTestId('letter-english')).toContainText('Ana Diaz')
  const href = await page.getByRole('link', { name: 'Download PDF' }).getAttribute('href')
  const pdf = await page.request.get(href!)
  expect(pdf.ok()).toBeTruthy()
  expect((await pdf.body()).subarray(0, 4).toString()).toBe('%PDF')
})

test('clean sample says no errors found and what was checked', async ({ page }) => {
  await start(page, 'clean')
  await toResults(page)
  await expect(page.getByTestId('headline')).toContainText('No errors found')
  await expect(page.getByText('What we checked')).toBeVisible()
  await expect(page.locator('article')).toHaveCount(0)
})

test('typed overcharge question explains the flagged charges', async ({ page }) => {
  await start(page, 'overcharge')
  await toResults(page)
  await page.getByRole('button', { name: 'Ask a question' }).click()
  await page.getByLabel('Type your question').fill('Why am I being overcharged')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  const answer = page.getByTestId('msg-assistant').last()
  await expect(answer).toContainText('$412.00')
  await expect(answer).toContainText('80053')
  await expect(answer.getByTestId('citation').first()).toBeVisible()
  await expect(answer).not.toContainText('could not answer')
  await expect(page.getByRole('combobox')).toHaveCount(0)
})

test('additional sample documents can be downloaded and reviewed', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Get started' }).click()
  for (const sample of ['duplicate_lab', 'bundled_tests', 'insurance_mismatch', 'balance_billing', 'excess_units', 'routine_visit']) {
    await expect(page.getByTestId(`sample-${sample}`)).toBeVisible()
  }
  const sample = page.getByTestId('sample-duplicate_lab')
  const download = page.waitForEvent('download')
  await sample.locator('..').getByRole('link', { name: 'Itemized bill', exact: true }).click()
  expect((await download).suggestedFilename()).toBe('duplicate_lab-bill.pdf')
  await sample.click()
  await page.getByTestId('looks-right').waitFor()
  await toResults(page)
  await expect(page.getByTestId('headline')).toContainText('$30.00')
})

test('ask sample uses careful wording and shows no overcharge total', async ({ page }) => {
  await start(page, 'ask')
  await toResults(page)
  await expect(page.getByTestId('headline')).toContainText('worth asking about')
  await expect(page.getByTestId('headline')).not.toContainText('overcharged')
  await expect(page.getByText('Worth asking').first()).toBeVisible()
  await expect(page.locator('main')).not.toContainText(/fraud|illegal|scam|lawsuit/i)
})

test('photo sample flags a low-confidence line; editing a value changes the audit', async ({ page }) => {
  await start(page, 'overcharge_photo')
  await expect(page.getByText('Please check this').first()).toBeVisible()
  await page.getByLabel('You owe').last().fill('40')
  await page.getByLabel('Balance shown on the bill').fill('295') // the printed balance must match the lines
  await toResults(page)
  await expect(page.getByTestId('headline')).toContainText('$205.00')
})

test('Spanish interface, results and question', async ({ page }) => {
  await start(page, 'overcharge', 'Español')
  await expect(page.getByRole('heading', { name: 'Revise lo que leímos' })).toBeVisible()
  await toResults(page)
  await expect(page.getByTestId('headline')).toContainText('Es posible que le hayan cobrado de más: $412.00')
  await page.getByRole('button', { name: 'Hacer una pregunta' }).click()
  await page.getByRole('button', { name: '¿Cuánto debo realmente?' }).click()
  await expect(page.getByTestId('msg-assistant').first()).toContainText('$412.00')
  const original = page.getByTestId('msg-assistant').first().getByText('Original en inglés', { exact: true })
  await original.click()
  await expect(page.getByTestId('msg-assistant').first().locator('p[lang="en"]')).toContainText('$412.00')
})

test('uploads: a PDF is read, a photo without a model gives a plain message', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Get started' }).click()
  await page.getByTestId('bill-input').setInputFiles(`${SAMPLES}/overcharge/bill.pdf`)
  await page.getByTestId('eob-input').setInputFiles(`${SAMPLES}/overcharge/eob.pdf`)
  await page.getByRole('button', { name: 'Read my documents' }).click()
  await page.getByTestId('looks-right').waitFor()
  await page.goto('/')
  await page.getByRole('button', { name: 'Get started' }).click()
  await page.getByTestId('bill-input').setInputFiles(`${SAMPLES}/overcharge_photo/bill.jpg`)
  await page.getByTestId('eob-input').setInputFiles(`${SAMPLES}/overcharge_photo/eob.jpg`)
  await page.getByRole('button', { name: 'Read my documents' }).click()
  await expect(page.getByRole('alert')).toContainText('AI reader')
  await page.getByRole('button', { name: 'Enter lines by hand' }).click()
  await expect(page.getByRole('heading', { name: 'Check what we read' })).toBeVisible()
})

test('delete my data wipes the case', async ({ page }) => {
  await start(page, 'clean')
  const id = await page.evaluate(() => document.querySelector('img')?.getAttribute('src')?.match(/cases\/(\w+)\//)?.[1])
  await page.getByRole('button', { name: 'Delete my data and start over' }).click()
  await expect(page.getByRole('heading', { name: 'Understand your medical bill' })).toBeVisible()
  expect((await page.request.get(`/api/cases/${id}`)).status()).toBe(404)
})

test('keyboard: focus moves to each screen heading and the skip link works', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused()
  await page.getByRole('button', { name: 'Get started' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Add your documents' })).toBeFocused()
})

test('workflow navigation requires review and preserves question history', async ({ page }) => {
  await page.goto('/')
  const nav = page.getByRole('navigation')
  await expect(nav.getByRole('button', { name: 'Check', exact: true })).toBeDisabled()
  await expect(nav.getByRole('button', { name: 'Results', exact: true })).toBeDisabled()
  await nav.getByRole('button', { name: 'Upload', exact: true }).click()
  await page.getByTestId('sample-overcharge').click()
  await page.getByTestId('looks-right').waitFor()
  await expect(nav.getByRole('button', { name: 'Ask', exact: true })).toBeDisabled()
  await toResults(page)
  await nav.getByRole('button', { name: 'Ask', exact: true }).click()
  await page.getByRole('button', { name: 'What is an EOB?', exact: true }).click()
  await page.getByTestId('msg-assistant').first().waitFor()
  await nav.getByRole('button', { name: 'Results', exact: true }).click()
  await expect(page.getByTestId('headline')).toContainText('$412.00')
  await nav.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByTestId('msg-assistant')).toHaveCount(1)
  await nav.getByRole('button', { name: 'Check', exact: true }).click()
  await expect(nav.getByRole('button', { name: 'Results', exact: true })).toBeDisabled()
  await expect(nav.getByRole('button', { name: 'Letter', exact: true })).toBeDisabled()
  await toResults(page)
  await expect(nav.getByRole('button', { name: 'Letter', exact: true })).toBeEnabled()
})

test('reduced motion leaves content visible without continuous animation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Understand your medical bill' })).toBeVisible()
  const animations = await page.locator('.art-paper-front, .feature-card').evaluateAll((elements) =>
    elements.map((el) => ({ duration: parseFloat(getComputedStyle(el).animationDuration), iterations: getComputedStyle(el).animationIterationCount })))
  expect(animations.every((a) => a.duration <= 0.001 && a.iterations === '1')).toBeTruthy()
  await page.getByRole('button', { name: 'Get started', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Add your documents' })).toBeFocused()
})

test('no horizontal scroll and no overflow at this width', async ({ page }) => {
  await start(page, 'overcharge')
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(await overflow()).toBeLessThanOrEqual(0)
  await toResults(page)
  expect(await overflow()).toBeLessThanOrEqual(0)
})

test('accessibility: axe reports no critical violations on any screen', async ({ page }) => {
  const check = async (label: string) => {
    // Check the settled screen, after entrance and message transitions finish.
    await page.locator('.page-transition').evaluate(async (element) => {
      const entrance = element.getAnimations({ subtree: true }).filter((a) => {
        const timing = a.effect?.getTiming()
        return typeof timing?.duration === 'number' && timing.duration <= 600 && timing.iterations !== Infinity
      })
      await Promise.all(entrance.map((a) => a.finished.catch(() => {})))
    })
    const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    const bad = r.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious')
    expect(bad.map((v) => `${label}: ${v.id} (${v.impact})`), JSON.stringify(bad.map((v) => v.nodes.map((n) => ({ html: n.html, reason: n.failureSummary }))))).toEqual([])
  }
  await page.goto('/')
  await check('welcome')
  await page.getByRole('button', { name: 'Get started' }).click()
  await check('upload')
  await page.getByTestId('sample-overcharge').click()
  await page.getByTestId('looks-right').waitFor()
  await check('review')
  await toResults(page)
  await page.getByTestId('evidence-eob_mismatch').click()
  await check('results')
  await page.getByRole('button', { name: 'Ask a question' }).click()
  await page.getByRole('button', { name: 'What is an EOB?' }).click()
  await page.getByTestId('msg-assistant').first().waitFor()
  await check('ask')
  await page.getByRole('button', { name: 'Write the letter' }).click()
  await page.getByTestId('letter-english').waitFor()
  await check('letter')
})

test('Mongolian demo path: results, grounded answer and side-by-side letter, all verified offline', async ({ page }) => {
  await start(page, 'overcharge', 'Монгол')
  await expect(page.getByRole('heading', { name: 'Бидний уншсныг шалгана уу' })).toBeVisible()
  await toResults(page)
  await expect(page.getByTestId('headline')).toContainText('$412.00')
  await expect(page.getByText('Анхаарах')).toHaveCount(0)
  await expect(page.locator('article').first()).toContainText('кодыг')
  await expect(page.getByRole('note')).toHaveCount(1) // only the page banner: no "could not be checked" notices
  await page.getByRole('button', { name: 'Асуулт асуух' }).click()
  await page.getByRole('button', { name: 'Би үнэндээ хэдийг төлөх ёстой вэ?' }).click()
  const answer = page.getByTestId('msg-assistant').first()
  await expect(answer).toContainText('$412.00')
  await expect(answer).toContainText('нэхэмжлэх')
  await page.getByRole('button', { name: 'Захидал бичих' }).click()
  const sbs = page.getByTestId('letter-side-by-side')
  await expect(sbs).toContainText('Маргаантай нийт дүн: $412.00.')
  await expect(sbs).toContainText('Total amount in question: $412.00.')
  await expect(page.getByRole('note')).toHaveCount(1)
})
