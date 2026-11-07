'use strict';
// Final CI checks use real Firefox and Chromium, not the DOM fixture.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium, firefox } = require('playwright');
const root = path.resolve(__dirname, '..');
const mime = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json',
  '.png':'image/png', '.webp':'image/webp', '.jpg':'image/jpeg', '.svg':'image/svg+xml', '.ico':'image/x-icon'};
const server = http.createServer((request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    let file = path.resolve(root, '.' + pathname);
    if ((file !== root && !file.startsWith(root + path.sep)) || pathname.split('/').some(part => part.startsWith('.'))) {
      response.writeHead(403); response.end(); return;
    }
    if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    response.writeHead(200, {'Content-Type': mime[path.extname(file)] || 'application/octet-stream'});
    fs.createReadStream(file).pipe(response);
  } catch {response.writeHead(404); response.end();}
});

async function aligned(page, selector, index) {
  await page.waitForFunction(({selector, index}) => {
    const section = document.querySelector(selector);
    const current = Number(section.querySelector('.carousel-position').textContent.match(/\d+/)[0]) - 1;
    const track = section.querySelector('.carousel-track');
    const slides = [...track.children].filter(node => !node.hasAttribute('data-carousel-clone'));
    const bounds = track.getBoundingClientRect(), card = slides[index].getBoundingClientRect();
    const delta = getComputedStyle(track).direction === 'rtl' ? card.right - bounds.right : card.left - bounds.left;
    return current === index && Math.abs(delta) < 2;
  }, {selector, index}, {timeout: 5000});
}
async function current(section) {
  return Number((await section.locator('.carousel-position').innerText()).match(/\d+/)[0]) - 1;
}
async function changed(page, selector, from) {
  await page.waitForFunction(({selector, from}) => Number(document.querySelector(selector)
    .querySelector('.carousel-position').textContent.match(/\d+/)[0]) - 1 !== from,
    {selector, from}, {timeout: 3500});
}

async function checkHover(page, selector) {
  await page.mouse.move(1, 1);
  const section = page.locator(selector);
  await section.scrollIntoViewIfNeeded();
  // Enter through the stable heading, then hover the aligned image.
  await section.locator('h2').hover();
  await page.waitForTimeout(700);
  const index = await current(section);
  await aligned(page, selector, index);
  await section.locator('.catalog-slide:not([data-carousel-clone]) .catalog-image').nth(index).hover();
  const before = await section.locator('.carousel-track').evaluate(track => track.scrollLeft);
  await page.waitForTimeout(2200);
  assert.equal(await current(section), index, `${selector}: mouse hover must pause beyond two ticks`);
  const after = await section.locator('.carousel-track').evaluate(track => track.scrollLeft);
  assert.ok(Math.abs(after - before) < 2, `${selector}: hovered card must remain aligned`);
  // Scrolling the page while hovering must not create the arrow-only deadline.
  await page.mouse.wheel(0, 1);
  await page.waitForTimeout(100);
  const exitAt = await page.evaluate(() => performance.now());
  await page.mouse.move(1, 1);
  await changed(page, selector, index);
  const delay = await page.evaluate(start => performance.now() - start, exitAt);
  assert.ok(delay < 1800, `${selector}: hover exit must resume promptly, got ${delay} ms`);
}

async function check(browserType, viewport, base, rtl = false) {
  const browser = await browserType.launch({headless: true});
  let page;
  try {
    const touch = viewport.width < 700;
    const context = await browser.newContext({viewport, reducedMotion: 'no-preference', locale: 'en-US',
      hasTouch: touch, isMobile: touch});
    await context.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort());
    page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + (rtl ? '/ar/?lang=ar' : '/?lang=en'), {waitUntil: 'networkidle'});
    const reject = page.locator('#cookie-banner [data-cookie-reject]');
    const activate = locator => touch ? locator.tap() : locator.click();
    if (await reject.isVisible()) await activate(reject);
    if (!touch) {
      for (const id of ['#latest-products', '#latest-applications', '#latest-books']) await checkHover(page, id);
    }
    await page.mouse.move(1, 1);
    const selector = '#latest-applications', section = page.locator(selector);
    await section.scrollIntoViewIfNeeded();
    await page.waitForFunction(selector => document.querySelector(selector).querySelectorAll('[data-carousel-clone]').length === 2, selector);
    const total = await section.locator('.catalog-slide:not([data-carousel-clone])').count();
    assert.equal(await section.getAttribute('data-carousel-autoplay'), '1000');
    const toggle = section.locator('[data-carousel-toggle]'), next = section.locator('[data-carousel-next]');
    await activate(toggle);
    await page.waitForTimeout(700);
    let index = await current(section); await aligned(page, selector, index);
    // Go to the last real card while paused, then record the wrap trajectory.
    while (index !== total - 1) {
      await activate(next); index = (index + 1) % total; await aligned(page, selector, index);
    }
    await next.scrollIntoViewIfNeeded();
    const before = await section.locator('.carousel-track').evaluate(track => {
      window.wrapOffsets = [];
      track.addEventListener('scroll', () => window.wrapOffsets.push(track.scrollLeft));
      return {left: track.scrollLeft, y: window.scrollY};
    });
    await activate(next); await aligned(page, selector, 0);
    const after = await section.locator('.carousel-track').evaluate(track => ({left: track.scrollLeft,
      y: window.scrollY, offsets: window.wrapOffsets,
      clones: [...track.querySelectorAll('[data-carousel-clone]')].map(node => ({hidden:node.getAttribute('aria-hidden'), inert:node.inert, ids:node.querySelectorAll('[id]').length}))}));
    assert.ok(after.offsets.some(left => rtl ? left < before.left - 10 : left > before.left + 10),
      'wrap must move forward to a neighboring copy, not animate backwards through the list');
    assert.ok(Math.abs(after.y - before.y) <= 2, 'horizontal wrap must not jump the document vertically');
    assert.ok(after.clones.every(copy => copy.hidden === 'true' && copy.inert && copy.ids === 0));
    // Resume and use an arrow. Leaving must preserve a full ten-second reading
    // period after the last input, even with retained mouse-click focus or touch.
    await toggle.evaluate(button => button.click());
    await section.evaluate(node => node.addEventListener('click', () => {window.lastCarouselInput = performance.now();}));
    await activate(next);
    const selected = 1 % total;
    await aligned(page, selector, selected);
    await page.mouse.move(1, 1);
    await page.waitForTimeout(700);
    await section.locator('.carousel-track').evaluate(track => {
      const initial = track.scrollLeft;
      window.firstAutomaticScroll = null;
      track.addEventListener('scroll', () => {
        if (window.firstAutomaticScroll === null && Math.abs(track.scrollLeft - initial) > 2) {
          window.firstAutomaticScroll = performance.now();
        }
      });
    });
    const elapsed = await page.evaluate(() => performance.now() - window.lastCarouselInput);
    await page.waitForTimeout(Math.max(0, 9000 - elapsed));
    assert.equal(await current(section), selected, 'manual arrow must prevent autoplay before ten seconds');
    await changed(page, selector, selected);
    const firstAdvanceDelay = await page.evaluate(() => window.firstAutomaticScroll - window.lastCarouselInput);
    assert.ok(firstAdvanceDelay >= 9990, `automatic scrolling resumed too early: ${firstAdvanceDelay} ms`);
    const resumed = await current(section);
    await changed(page, selector, resumed);
    // Playback controls must not introduce a new ten-second arrow deadline.
    await activate(toggle);
    await page.waitForTimeout(700);
    const pausedIndex = await current(section);
    await aligned(page, selector, pausedIndex);
    await activate(toggle);
    await page.mouse.move(1, 1);
    await changed(page, selector, pausedIndex);
    assert.deepEqual(errors, [], 'no browser runtime errors');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    assert.equal(overflow, false, 'mobile/desktop document must not overflow horizontally');
    console.log(`PASS ${browserType.name()} ${viewport.width}x${viewport.height}${rtl ? ' RTL' : ''}: ${touch ? 'touch resume' : 'products/apps/books immediate hover exit after wheel'}, arrow-only ten-second delay, prompt playback controls, one-second idle cadence, retained click focus, forward wrap, stable document, inert copies`);
    await context.close();
  } catch (error) {
    if (page && process.env.BROWSER_TEST_ARTIFACTS) {
      const directory = process.env.BROWSER_TEST_ARTIFACTS;
      fs.mkdirSync(directory, {recursive:true});
      const name = `${browserType.name()}-${viewport.width}${rtl ? '-rtl' : ''}`;
      await page.screenshot({path:path.join(directory, name + '.png'), fullPage:true}).catch(() => {});
      fs.writeFileSync(path.join(directory, name + '.html'), await page.content());
    }
    throw error;
  } finally {await browser.close();}
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    assert.equal((await fetch(base + '/')).status, 200, 'local homepage server');
    assert.equal((await fetch(base + '/assets/carousels.js')).status, 200, 'local script server');
    if (process.argv.includes('--server-check')) {console.log('PASS local browser-test HTTP server'); return;}
    await check(firefox, {width:1440, height:1000}, base);
    await check(chromium, {width:1440, height:1000}, base);
    await check(chromium, {width:390, height:844}, base);
    await check(firefox, {width:1440, height:1000}, base, true);
  } finally {await new Promise(resolve => server.close(resolve));}
})().catch(error => {console.error(error); process.exitCode = 1;});
