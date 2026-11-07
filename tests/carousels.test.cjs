'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const corporate = fs.existsSync(path.join(__dirname, '../assets/carousels.js'));
const source = fs.readFileSync(path.join(__dirname, corporate ? '../assets/carousels.js' : '../assets/js/site.js'), 'utf8');

class Element {
  constructor() {
    this.events = new Map(); this.attrs = {}; this.dataset = {}; this.children = [];
    this.style = {values: {}, setProperty(key, value) {this.values[key] = value;}};
    const classes = new Set();
    this.classList = {add: key => classes.add(key), remove: key => classes.delete(key)};
  }
  addEventListener(type, callback) {this.events.set(type, [...(this.events.get(type) || []), callback]);}
  emit(type, extra = {}) {
    const event = {target: this, preventDefault() {this.prevented = true;}, ...extra};
    for (const callback of this.events.get(type) || []) callback(event);
    if (this.parentElement && ['click', 'pointerdown', 'pointerup', 'pointercancel', 'keydown', 'wheel', 'focusin', 'focusout'].includes(type)) {
      this.parentElement.emit(type, event);
    }
    return event;
  }
  getAttribute(key) {return this.attrs[key];}
  removeAttribute(key) {delete this.attrs[key];}
  prepend(node) {this.children.unshift(node);}
  append(node) {this.children.push(node);}
  cloneNode() {
    const copy = new Element(); copy.attrs = {...this.attrs};
    copy.selectors = Object.fromEntries(Object.entries(this.selectors || {}).map(([key, value]) => [key, value.cloneNode()]));
    copy.getBoundingClientRect = this.getBoundingClientRect;
    return copy;
  }
  setAttribute(key, value) {this.attrs[key] = value;}
  querySelector(selector) {return this.selectors?.[selector] || null;}
  querySelectorAll(selector) {
    if (selector === '.slide') return this.children;
    if (selector === 'img') return this.selectors?.img ? [this.selectors.img] : [];
    if (selector === '[id]') return Object.values(this.selectors || {}).filter(node => node.attrs.id);
    return [];
  }
}

function fixture({rtl = false, reduced = false, count = 3} = {}) {
  const gallery = new Element(), track = new Element(), previous = new Element();
  const next = new Element(), status = new Element(), controls = new Element();
  const toggle = new Element(), icon = new Element(), document = new Element();
  const motion = new Element(), observers = [], visibility = [], frames = [], timers = new Map();
  let serial = 0, now = 0;
  motion.matches = reduced;
  status.dataset.positionTemplate = '{current} / {total}';
  toggle.dataset = {pauseLabel: 'Pause slideshow', playLabel: 'Resume slideshow'};
  toggle.selectors = {span: icon};
  gallery.dataset.carouselAutoplay = '1000';
  track.clientWidth = 300;
  let scrollLeft = 0;
  Object.defineProperty(track, 'scrollLeft', {get: () => scrollLeft, set(value) {
    scrollLeft = value; track.lastScroll = {left: value, behavior: 'instant'}; track.emit('scroll');
  }});
  track.getBoundingClientRect = () => ({left: 0, right: track.clientWidth});
  const dimensions = [[1024, 500], [891, 2000], [1080, 1920]];
  track.children = Array.from({length: count}, (_, index) => {
    const slide = new Element(), image = new Element();
    image.attrs = {id: 'image-' + index, width: String(dimensions[index][0]), height: String(dimensions[index][1])};
    slide.selectors = {img: image};
    slide.getBoundingClientRect = function () {
      const width = track.clientWidth, offset = track.children.indexOf(this) * (width + 24);
      const left = rtl ? -offset - track.scrollLeft : offset - track.scrollLeft;
      return {left, right: left + width};
    };
    return slide;
  });
  track.scrollTo = options => {track.scrollLeft = options.left; track.lastScroll = options;};
  gallery.selectors = {'.gallery-track': track, '.carousel-track': track, '.gallery-tools': controls,
    '.carousel-controls': controls, '[data-previous]': previous, '[data-next]': next, '[data-status]': status};
  controls.selectors = {'[data-carousel-prev]': previous, '[data-carousel-next]': next,
    '.carousel-position': status, '[data-carousel-toggle]': toggle};
  const members = new Set([gallery, track, previous, next, toggle, status]);
  for (const member of [track, previous, next, toggle, status]) member.parentElement = gallery;
  gallery.parentElement = document;
  gallery.contains = element => members.has(element);
  document.activeElement = null; document.hidden = false;
  document.querySelectorAll = selector => selector === (corporate ? '[data-carousel]' : '[data-gallery]') ? [gallery] : [];
  document.querySelector = () => null;
  const flush = () => {while (frames.length) frames.shift()();};
  const context = {document, matchMedia: () => motion, getComputedStyle: () => ({direction: rtl ? 'rtl' : 'ltr'}),
    performance: {now: () => now},
    requestAnimationFrame: callback => {frames.push(callback); return ++serial;},
    setTimeout: (callback, delay) => {const id = ++serial; timers.set(id, {callback, at: now + delay, delay}); return id;},
    clearTimeout: id => timers.delete(id),
    ResizeObserver: class {constructor(callback) {observers.push(callback);} observe() {}},
    IntersectionObserver: class {constructor(callback) {visibility.push(callback);} observe() {}}
  };
  context.window = context;
  vm.runInNewContext(source, context);
  flush();
  function advance(milliseconds) {
    const end = now + milliseconds;
    for (;;) {
      const pending = [...timers.entries()].filter(([, value]) => value.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!pending) break;
      now = pending[1].at; timers.delete(pending[0]); pending[1].callback(); flush();
    }
    now = end; flush();
  }
  return {gallery, track, previous, next, status, toggle, document, motion, timers,
    flush, advance, resize: width => {track.clientWidth = width; observers.forEach(callback => callback()); flush();},
    visible: value => visibility.forEach(callback => callback([{isIntersecting: value}]))};
}

const next = env => {env.next.emit('click'); env.flush();};
const previous = env => {env.previous.emit('click'); env.flush();};

test('manual wrap advances through boundary copies before an invisible reset', () => {
  const env = fixture(); previous(env);
  assert.equal(env.status.textContent, '3 / 3');
  assert.equal(env.track.lastScroll.behavior, 'smooth');
  env.advance(250);
  assert.equal(env.track.scrollLeft, 3 * 324);
  const before = env.track.scrollLeft; next(env);
  assert.equal(env.status.textContent, '1 / 3');
  assert.ok(env.track.scrollLeft > before, 'last-to-first must keep moving forward');
  assert.equal(env.track.lastScroll.behavior, 'smooth');
  env.advance(250); assert.equal(env.track.scrollLeft, 324);
  assert.equal(env.previous.disabled, false); assert.equal(env.next.disabled, false);
});

test('boundary copies are hidden, inert, preloaded and have no duplicate IDs', () => {
  const env = fixture();
  const copies = env.track.children.filter(node => node.attrs['data-carousel-clone']);
  assert.equal(copies.length, 2);
  for (const copy of copies) {
    assert.equal(copy.attrs['aria-hidden'], 'true'); assert.equal(copy.inert, true);
    assert.equal(copy.attrs.id, undefined); assert.equal(copy.selectors.img.attrs.id, undefined);
    assert.equal(copy.selectors.img.loading, 'eager');
  }
});

test('rotation preserves the selected image', () => {
  const env = fixture(); next(env); env.advance(250); env.resize(640);
  assert.equal(env.status.textContent, '2 / 3');
  assert.equal(env.track.lastScroll.left, 1328);
  assert.equal(env.track.lastScroll.behavior, 'instant');
});

test('reduced motion disables autoplay and uses immediate navigation', () => {
  const env = fixture({reduced: true}); next(env);
  assert.equal(env.track.lastScroll.behavior, 'instant');
  assert.equal([...env.timers.values()].filter(timer => timer.delay === 1000).length, 0);
});

test('autoplay follows a one-second cadence and wraps forward', () => {
  const env = fixture(); env.advance(999); assert.equal(env.status.textContent, '1 / 3');
  env.advance(1); assert.equal(env.status.textContent, '2 / 3');
  env.advance(1000); assert.equal(env.status.textContent, '3 / 3');
  env.advance(1000); assert.equal(env.status.textContent, '1 / 3');
  assert.equal(env.track.lastScroll.behavior, 'smooth');
  env.advance(250); assert.equal(env.track.scrollLeft, 324);
});

test('repeated scrollend and visibility reports do not postpone the deadline', () => {
  const env = fixture(); env.advance(600);
  env.track.emit('scrollend'); env.visible(true); env.advance(400);
  assert.equal(env.status.textContent, '2 / 3');
});

test('mouse hover pauses and leaving resumes immediately without a reading delay', () => {
  const env = fixture();
  env.advance(900); env.gallery.emit('pointerenter', {pointerType: 'mouse'}); env.advance(3000);
  assert.equal(env.status.textContent, '1 / 3');
  assert.equal(env.status.attrs['aria-live'], 'polite');
  env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(0);
  assert.equal(env.status.textContent, '2 / 3');
  assert.equal(env.status.attrs['aria-live'], 'off');
});

test('wheel movement and non-arrow pointer clicks during hover add no exit delay', () => {
  const env = fixture(); env.gallery.emit('pointerenter', {pointerType: 'mouse'});
  env.track.emit('wheel'); env.gallery.emit('pointerdown', {pointerType: 'mouse'});
  env.document.emit('pointerup'); env.gallery.emit('click'); env.advance(3000);
  assert.equal(env.status.textContent, '1 / 3');
  env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(0);
  assert.equal(env.status.textContent, '2 / 3');
});

test('non-arrow interactions and hover cannot refresh or clear an arrow deadline', () => {
  const env = fixture(); next(env); env.advance(3000);
  env.gallery.emit('pointerenter', {pointerType: 'mouse'}); env.track.emit('wheel');
  env.gallery.emit('pointerdown', {pointerType: 'mouse'}); env.document.emit('pointerup'); env.gallery.emit('click');
  env.advance(2000); env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(4999);
  assert.equal(env.status.textContent, '2 / 3');
  env.advance(1); assert.equal(env.status.textContent, '3 / 3');
});

test('manual navigation works during hover and click focus does not block exit resume', () => {
  const env = fixture(); env.gallery.emit('pointerenter', {pointerType: 'mouse'});
  env.document.activeElement = env.next;
  env.gallery.emit('pointerdown', {pointerType: 'mouse'}); env.document.emit('pointerup'); next(env); env.advance(3000);
  assert.equal(env.status.textContent, '2 / 3');
  env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(6999);
  assert.equal(env.status.textContent, '2 / 3');
  env.advance(1);
  assert.equal(env.status.textContent, '3 / 3');
});

test('hover during a transition survives settle and observer notifications', () => {
  const env = fixture(); env.advance(1000);
  env.gallery.emit('pointerenter', {pointerType: 'mouse'});
  env.advance(250); env.track.emit('scrollend'); env.visible(true); env.advance(3000);
  assert.equal(env.status.textContent, '2 / 3');
  env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(0);
  assert.equal(env.status.textContent, '3 / 3');
});

test('leaving hover cannot override an explicit pause', () => {
  const env = fixture(); env.gallery.emit('pointerenter', {pointerType: 'mouse'});
  env.toggle.emit('click'); env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(3000);
  assert.equal(env.status.textContent, '1 / 3');
  assert.equal(env.toggle.attrs['aria-pressed'], 'true');
  env.gallery.emit('pointerenter', {pointerType: 'mouse'}); env.toggle.emit('click'); env.advance(3000);
  assert.equal(env.status.textContent, '1 / 3');
  env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(0);
  assert.equal(env.status.textContent, '2 / 3');
});

test('touch enter and leave never latch a hover pause', () => {
  const env = fixture(); env.gallery.emit('pointerenter', {pointerType: 'touch'}); env.advance(1000);
  assert.equal(env.status.textContent, '2 / 3');
  env.gallery.emit('pointerleave', {pointerType: 'touch'}); env.advance(1000);
  assert.equal(env.status.textContent, '3 / 3');
});

test('pause and resume update accessible labels', () => {
  const env = fixture(); env.toggle.emit('click'); env.advance(60000);
  assert.equal(env.status.textContent, '1 / 3');
  assert.equal(env.toggle.attrs['aria-label'], 'Resume slideshow');
  assert.equal(env.toggle.attrs['aria-pressed'], 'true');
  env.toggle.emit('click'); env.advance(999);
  assert.equal(env.status.textContent, '1 / 3');
  env.advance(1);
  assert.equal(env.status.textContent, '2 / 3');
  assert.equal(env.toggle.attrs['aria-label'], 'Pause slideshow');
});

test('keyboard focus, hidden pages and offscreen sections pause playback', () => {
  const env = fixture(); env.document.activeElement = env.track;
  env.document.emit('keydown', {key: 'Tab'}); env.gallery.emit('focusin'); env.advance(3000);
  assert.equal(env.status.textContent, '1 / 3');
  env.document.activeElement = null; env.gallery.emit('focusout'); env.advance(0);
  env.document.hidden = true; env.document.emit('visibilitychange'); env.advance(3000);
  assert.equal(env.status.textContent, '1 / 3');
  env.document.hidden = false; env.document.emit('visibilitychange'); env.visible(false); env.advance(3000);
  assert.equal(env.status.textContent, '1 / 3');
  env.visible(true); env.advance(1000); assert.equal(env.status.textContent, '2 / 3');
});

test('a tap without scrolling does not start an arrow reading delay', () => {
  const env = fixture(); env.track.emit('pointerdown'); env.advance(2500);
  assert.equal(env.status.textContent, '1 / 3');
  env.track.emit('pointerup'); env.advance(999); assert.equal(env.status.textContent, '1 / 3');
  env.advance(1); assert.equal(env.status.textContent, '2 / 3');
});

test('both manual arrows wait ten seconds then restore the one-second cadence', () => {
  for (const [navigate, selected, following, final] of [[next, '2 / 3', '3 / 3', '1 / 3'], [previous, '3 / 3', '1 / 3', '2 / 3']]) {
    const env = fixture(); navigate(env); env.advance(9999);
    assert.equal(env.status.textContent, selected);
    env.advance(1); assert.equal(env.status.textContent, following);
    env.advance(1000); assert.equal(env.status.textContent, final);
  }
});

test('each further arrow click restarts the ten-second reading period', () => {
  const env = fixture(); next(env); env.advance(5000); previous(env);
  env.advance(9999); assert.equal(env.status.textContent, '1 / 3');
  env.advance(1); assert.equal(env.status.textContent, '2 / 3');
});

test('other carousel controls do not start a reading delay', () => {
  const env = fixture(), button = new Element(); button.parentElement = env.gallery;
  button.emit('click'); env.advance(999); assert.equal(env.status.textContent, '1 / 3');
  env.advance(1); assert.equal(env.status.textContent, '2 / 3');
});

test('a long drag resumes the normal cadence on release', () => {
  const env = fixture(); env.track.emit('pointerdown'); env.advance(15000);
  assert.equal(env.status.textContent, '1 / 3');
  env.document.emit('pointerup'); env.advance(999);
  assert.equal(env.status.textContent, '1 / 3');
  env.advance(1); assert.equal(env.status.textContent, '2 / 3');
});

test('settle, observers and resize cannot shorten or extend the interaction deadline', () => {
  const env = fixture(); next(env); env.advance(6000);
  env.track.emit('scrollend'); env.visible(true); env.resize(640);
  env.advance(3999); assert.equal(env.status.textContent, '2 / 3');
  env.advance(1); assert.equal(env.status.textContent, '3 / 3');
});

test('wheel and track keyboard navigation do not start an arrow delay', () => {
  const wheel = fixture(); wheel.track.emit('wheel'); wheel.advance(999);
  assert.equal(wheel.status.textContent, '1 / 3');
  wheel.advance(1); assert.equal(wheel.status.textContent, '2 / 3');
  const keyboard = fixture(); keyboard.document.activeElement = keyboard.track;
  keyboard.track.emit('keydown', {key: 'ArrowRight'}); keyboard.flush(); keyboard.advance(6000);
  keyboard.document.activeElement = null; keyboard.gallery.emit('focusout'); keyboard.advance(999);
  assert.equal(keyboard.status.textContent, '2 / 3');
  keyboard.advance(1); assert.equal(keyboard.status.textContent, '3 / 3');
});

test('explicit pause survives manual arrows and an expired reading period', () => {
  const env = fixture(); env.toggle.emit('click'); next(env); env.advance(60000);
  assert.equal(env.status.textContent, '2 / 3');
  assert.equal(env.toggle.attrs['aria-pressed'], 'true');
});

test('pointer release outside an untouched carousel does not defer its autoplay', () => {
  const env = fixture(); env.advance(900); env.document.emit('pointerup'); env.advance(100);
  assert.equal(env.status.textContent, '2 / 3');
});

test('hover beyond the arrow reading period resumes immediately on exit', () => {
  const env = fixture(); env.gallery.emit('pointerenter', {pointerType: 'mouse'}); next(env);
  env.advance(12000); assert.equal(env.status.textContent, '2 / 3');
  env.gallery.emit('pointerleave', {pointerType: 'mouse'}); env.advance(0);
  assert.equal(env.status.textContent, '3 / 3');
  env.advance(1000); assert.equal(env.status.textContent, '1 / 3');
});

test('RTL arrows wrap continuously and rotation preserves the active slide', () => {
  const env = fixture({rtl: true}); previous(env); env.advance(250);
  assert.equal(env.status.textContent, '3 / 3');
  next(env); env.advance(250); assert.equal(env.status.textContent, '1 / 3');
  next(env); env.advance(250); env.resize(640);
  assert.equal(env.status.textContent, '2 / 3');
  assert.equal(env.track.lastScroll.left, -1328);
});
