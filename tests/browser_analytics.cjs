'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium, firefox } = require('playwright');

const root = path.resolve(process.env.NEH_SITE_ROOT || path.join(__dirname, '..'));
const site = 'https://nihonessentialshub.com';
const preview = 'https://preview.example.test';
const id = 'G-LHR5R3H8ZP';
const tag = 'https://www.googletagmanager.com/gtag/js?id=' + id;
const collect = 'https://www.google-analytics.com/g/collect';
const gaCookie = '_ga_' + id.slice(2);
const isCollection = url => /(^|\.)google-analytics\.com$/.test(url.hostname) && url.pathname === '/g/collect';
const mime = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg'
};

// Exercise the same browser fields the real tag can read, independently of
// gtag config. All provider requests are intercepted; no test data leaves.
const fakeTag = `
  document.cookie = '_ga=browser; Path=/; Domain=nihonessentialshub.com; Secure';
  document.cookie = '${gaCookie}=session; Path=/; Secure';
  const config = dataLayer.find(command => command[0] === 'config');
  const pixel = new Image();
  pixel.src = ${JSON.stringify(collect)} + '?' + new URLSearchParams({
    tid: config[1], en: 'page_view', dl: location.href, dr: document.referrer
  });
`;

async function fixture(browser, providerTag = fakeTag) {
  const context = await browser.newContext({ locale: 'en-US', serviceWorkers: 'block' });
  const google = [];
  const unexpected = [];
  const errors = [];
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.href === tag) {
      google.push(url.href);
      return route.fulfill({ contentType: 'text/javascript', body: providerTag });
    }
    if (isCollection(url)) {
      google.push(url.href);
      return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*' } });
    }
    if (![site, preview].includes(url.origin)) {
      unexpected.push(url.href);
      return route.abort();
    }
    const relative = url.pathname.endsWith('/') ? url.pathname + 'index.html' : url.pathname;
    const file = path.resolve(root, '.' + relative);
    if (!file.startsWith(root + path.sep)) return route.fulfill({ status: 404 });
    try {
      const body = await fs.readFile(file);
      return route.fulfill({ contentType: mime[path.extname(file)] || 'application/octet-stream', body });
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      if (!route.request().isNavigationRequest()) return route.fulfill({ status: 404 });
      const body = await fs.readFile(path.join(root, '404.html'));
      return route.fulfill({ status: 404, contentType: 'text/html', body });
    }
  });
  context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
  return { context, google, unexpected, errors };
}

const banner = page => page.locator('#cookie-banner');
const dialog = page => page.locator('#cookie-dialog');
const language = page => page.locator('#cookie-preferences');
const analytics = page => page.locator('#cookie-analytics');
const frame = page => page.locator('#neh-analytics-frame');
const decision = page => page.evaluate(() => window.nehPreferences.getConsent());
const save = page => dialog(page).locator('[data-cookie-save]').click();
const cookieNames = async context => (await context.cookies(site)).map(cookie => cookie.name).sort();
const manage = page => page.locator('[data-cookie-manage]:visible').first().click();
const waitForCollection = page => page.waitForRequest(request => isCollection(new URL(request.url())));

function assertPageView(request, canonical, referrer) {
  const payload = new URL(request.url()).searchParams;
  assert.equal(payload.get('tid'), id);
  assert.equal(payload.get('en'), 'page_view');
  assert.equal(payload.get('dl'), canonical);
  assert.equal(payload.get('dr'), referrer);
  assert.doesNotMatch(request.url() + (request.postData() || ''), /private-(query|fragment|path|referrer)/);
}

async function verifyLifecycle(browser) {
  const { context, google, unexpected, errors } = await fixture(browser);
  try {
    const page = await context.newPage();
    await page.goto(site + '/?lang=en');
    assert.ok(await banner(page).isVisible());
    assert.deepEqual(await cookieNames(context), []);
    assert.deepEqual(google, []);

    await manage(page);
    assert.ok(await dialog(page).isVisible());
    assert.equal(await language(page).isChecked(), false);
    assert.equal(await analytics(page).isChecked(), false);
    await language(page).check();
    await save(page);
    assert.deepEqual(await decision(page), { preferences: true, analytics: false });
    assert.deepEqual(await cookieNames(context), ['cookie_consent', 'site_language']);
    assert.deepEqual(google, []);

    await page.goto(site + '/contact/?lang=en&probe=private-query#private-fragment', {
      referer: site + '/private-path?probe=private-referrer'
    });
    assert.equal(await banner(page).isVisible(), false);
    assert.deepEqual(google, []);
    await manage(page);
    await language(page).uncheck();
    await analytics(page).check();
    const [collection] = await Promise.all([waitForCollection(page), save(page)]);
    assertPageView(collection, site + '/contact/', site + '/');
    assert.deepEqual(await decision(page), { preferences: false, analytics: true });
    assert.deepEqual(await cookieNames(context), ['_ga', gaCookie, 'cookie_consent']);
    assert.equal(google.filter(url => url === tag).length, 1);
    assert.equal(new URL(page.url()).searchParams.get('probe'), 'private-query');
    assert.equal(new URL(page.url()).hash, '#private-fragment');

    const commands = await frame(page).evaluate(element =>
      element.contentWindow.dataLayer.map(command => Array.from(command)));
    const denied = { ad_storage: 'denied', ad_user_data: 'denied',
      ad_personalization: 'denied', analytics_storage: 'denied' };
    assert.deepEqual(commands.slice(0, 2), [
      ['consent', 'default', denied],
      ['consent', 'update', { ...denied, analytics_storage: 'granted' }]
    ]);
    const settings = commands.find(command => command[0] === 'set')[1];
    assert.equal(settings.cookie_expires, 180 * 24 * 60 * 60);
    assert.equal(settings.cookie_update, false);
    assert.match(settings.cookie_flags, /(?:^|;)Secure(?:;|$)/i);
    const config = commands.find(command => command[0] === 'config')[2];
    assert.equal(config.allow_google_signals, false);
    assert.equal(config.allow_ad_personalization_signals, false);

    const other = await context.newPage();
    await Promise.all([waitForCollection(other), other.goto(site + '/privacy/?lang=en')]);
    assert.deepEqual(await decision(other), { preferences: false, analytics: true });
    assert.equal(google.filter(url => url === tag).length, 2);

    const beforeWithdrawal = google.length;
    await manage(page);
    await language(page).check();
    await analytics(page).uncheck();
    await Promise.all([page.waitForEvent('load'), other.waitForEvent('load'), save(page)]);
    assert.deepEqual(await decision(page), { preferences: true, analytics: false });
    assert.deepEqual(await decision(other), { preferences: true, analytics: false });
    assert.deepEqual(await cookieNames(context), ['cookie_consent', 'site_language']);
    assert.equal(await frame(page).count(), 0);
    assert.equal(await frame(other).count(), 0);
    assert.equal(google.length, beforeWithdrawal);

    await page.goto(site + '/fr/team/?lang=fr');
    assert.equal(await page.locator('html').getAttribute('lang'), 'fr');
    assert.equal(await banner(page).isVisible(), false);
    assert.equal(await page.evaluate(() => window.nehPreferences.getLanguage()), 'fr');
    assert.equal(google.length, beforeWithdrawal);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

async function verifyRejectLegacyAndPreview(browser) {
  const { context, google, unexpected, errors } = await fixture(browser);
  try {
    await context.addCookies([
      { name: 'cookie_consent', value: 'v1%3Aaccept', url: site },
      { name: 'site_language', value: 'fr', url: site }
    ]);
    const page = await context.newPage();
    await page.goto(site + '/fr/contact/');
    assert.deepEqual(await decision(page), { preferences: true, analytics: false });
    assert.ok(await banner(page).isVisible());
    assert.deepEqual(google, []);
    await banner(page).locator('[data-cookie-reject]').click();
    assert.deepEqual(await decision(page), { preferences: false, analytics: false });
    assert.deepEqual(await cookieNames(context), ['cookie_consent']);
    await page.goto(site + '/fr/cookie-policy/?lang=fr');
    assert.equal(await banner(page).isVisible(), false);
    assert.equal(await frame(page).count(), 0);
    assert.deepEqual(google, []);

    await page.goto(preview + '/?lang=en');
    await banner(page).locator('[data-cookie-accept]').click();
    assert.deepEqual(await decision(page), { preferences: true, analytics: true });
    assert.equal(await frame(page).count(), 0);
    assert.deepEqual(google, []);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

async function verifyLocalizedLayout(browser) {
  const { context, google, unexpected, errors } = await fixture(browser);
  try {
    const page = await context.newPage();
    const locales = JSON.parse(await fs.readFile(path.join(root, 'data/i18n/locales.json'), 'utf8'));
    for (const { code } of locales) {
      const prefix = code === 'en' ? '' : '/' + code;
      await page.goto(site + prefix + '/cookie-policy/?lang=' + code);
      for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }]) {
        await page.setViewportSize(viewport);
        assert.ok(await banner(page).isVisible(), code);
        await manage(page);
        assert.ok(await dialog(page).isVisible(), code);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, code);
        await analytics(page).scrollIntoViewIfNeeded();
        assert.ok(await analytics(page).isVisible(), code);
        await dialog(page).locator('[data-cookie-close]').click();
      }
    }
    assert.deepEqual(google, []);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

async function verifyRealTag(browser, file) {
  const { context, google, unexpected, errors } = await fixture(browser, await fs.readFile(file));
  try {
    const page = await context.newPage();
    await page.goto(site + '/?lang=en&probe=private-query#private-fragment', {
      referer: site + '/private-path?probe=private-referrer'
    });
    assert.deepEqual(google, []);
    await manage(page);
    await analytics(page).check();
    const [request] = await Promise.all([waitForCollection(page), save(page)]);
    assertPageView(request, site + '/', site + '/');
    const actual = (await context.cookies(site)).filter(cookie => ['_ga', gaCookie].includes(cookie.name));
    assert.deepEqual(actual.map(cookie => cookie.name).sort(), ['_ga', gaCookie]);
    for (const cookie of actual) {
      const duration = cookie.expires - Date.now() / 1000;
      assert.ok(duration > 0 && duration <= 180 * 24 * 60 * 60 + 1, cookie.name + ' expiry');
      assert.equal(cookie.secure, true, cookie.name + ' Secure flag');
      assert.equal(cookie.sameSite, 'Lax', cookie.name + ' SameSite flag');
    }
    assert.deepEqual(unexpected, []);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
}

(async () => {
  for (const browserType of [chromium, firefox]) {
    const browser = await browserType.launch({
      headless: true,
      executablePath: browserType === chromium ? process.env.BROWSER_CHROMIUM_EXECUTABLE : undefined
    });
    try {
      await verifyLifecycle(browser);
      await verifyRejectLegacyAndPreview(browser);
      if (browserType === chromium) await verifyLocalizedLayout(browser);
      if (process.env.NEH_GOOGLE_TAG_FILE) await verifyRealTag(browser, process.env.NEH_GOOGLE_TAG_FILE);
      console.log(`PASS ${browserType.name()}: Analytics consent, withdrawal, request privacy, and preview isolation` +
        (browserType === chromium ? ', including preferences layout for every locale' : '') +
        (process.env.NEH_GOOGLE_TAG_FILE ? ' (also checked the real Google tag)' : ''));
    } finally {
      await browser.close();
    }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
