'use strict';

document.querySelectorAll('[data-carousel]').forEach(section => {
  const track = section.querySelector('.carousel-track');
  const slides = track ? Array.from(track.children) : [];
  const controls = section.querySelector('.carousel-controls');
  if (!controls || slides.length < 2 || track.dataset.carouselLoop) return;
  const previous = controls.querySelector('[data-carousel-prev]');
  const next = controls.querySelector('[data-carousel-next]');
  const position = controls.querySelector('.carousel-position');
  const toggle = controls.querySelector('[data-carousel-toggle]');
  const autoplayDelay = Number(section.dataset.carouselAutoplay) || 1000;
  const arrowDelay = 10000;
  const rtl = getComputedStyle(track).direction === 'rtl';
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

  function boundaryCopy(slide) {
    const copy = slide.cloneNode(true);
    copy.setAttribute('data-carousel-clone', 'true');
    copy.setAttribute('aria-hidden', 'true');
    copy.removeAttribute('id');
    copy.removeAttribute('data-catalog-id');
    copy.classList.remove('is-arriving');
    copy.inert = true;
    copy.querySelectorAll('[id]').forEach(element => element.removeAttribute('id'));
    copy.querySelectorAll('img').forEach(image => { image.loading = 'eager'; });
    return copy;
  }

  // Boundary copies let the last-to-first transition move one card forward.
  // The invisible recenter uses the identical original card after scrolling ends.
  const leading = boundaryCopy(slides[slides.length - 1]);
  const trailing = boundaryCopy(slides[0]);
  track.prepend(leading);
  track.append(trailing);
  track.dataset.carouselLoop = 'true';
  const pages = [leading, ...slides, trailing];
  let current = 0, requested = 0, activePage = 1;
  let navigating = false, wrapping = false, initialized = false;
  let keyboardFocus = false, interacting = false, hovered = false, paused = false, visible = true;
  let frame = 0, settleTimer = 0, arrivalTimer = 0, autoplayTimer = 0;
  let arriving = null;
  let resumeAfter = 0;

  function navigateByArrow(step) {
    resumeAfter = performance.now() + arrowDelay;
    go(requested + step);
  }

  function syncPlayback(restart = false, minimumDelay = autoplayDelay) {
    const focused = keyboardFocus && section.contains(document.activeElement) && document.activeElement !== toggle;
    const stopped = paused || reducedMotion.matches;
    if (toggle) {
      toggle.disabled = reducedMotion.matches;
      toggle.setAttribute('aria-pressed', String(stopped));
      toggle.setAttribute('aria-label', stopped ? toggle.dataset.playLabel : toggle.dataset.pauseLabel);
      toggle.querySelector('span').textContent = stopped ? '▶' : 'Ⅱ';
    }
    const playing = !stopped && !focused && !interacting && !hovered && visible && !document.hidden;
    position.setAttribute('aria-live', playing ? 'off' : 'polite');
    if (!playing || restart) {
      clearTimeout(autoplayTimer);
      autoplayTimer = 0;
    }
    // Repeated scrollend/observer events must not keep postponing the next tick.
    if (playing && !autoplayTimer) autoplayTimer = setTimeout(() => {
      autoplayTimer = 0;
      if (!navigating) go(requested + 1);
      syncPlayback();
    }, Math.max(minimumDelay, resumeAfter - performance.now()));
  }

  function clearArrival() {
    clearTimeout(arrivalTimer);
    if (arriving) arriving.classList.remove('is-arriving');
    arriving = null;
  }

  function arrive(index, from) {
    clearArrival();
    if (reducedMotion.matches) return;
    arriving = slides[index];
    arriving.style.setProperty('--carousel-enter-x', `${(index > from ? 1 : -1) * (rtl ? -1 : 1) * 18}px`);
    arriving.classList.add('is-arriving');
    arrivalTimer = setTimeout(clearArrival, 580);
  }

  function offsetFor(page) {
    const bounds = track.getBoundingClientRect();
    const target = page.getBoundingClientRect();
    return track.scrollLeft + (rtl ? target.right - bounds.right : target.left - bounds.left);
  }

  function jumpTo(page) {
    const left = offsetFor(page);
    const behavior = track.style.scrollBehavior;
    const snap = track.style.scrollSnapType;
    track.style.scrollBehavior = 'auto';
    track.style.scrollSnapType = 'none';
    track.scrollLeft = left;
    // Commit the offset before restoring snap; Firefox must not animate the reset.
    track.getBoundingClientRect();
    track.style.scrollBehavior = behavior;
    track.style.scrollSnapType = snap;
  }

  function update(animate = true) {
    frame = 0;
    const from = current;
    const bounds = track.getBoundingClientRect();
    const center = (bounds.left + bounds.right) / 2;
    let distance = Infinity;
    pages.forEach((page, index) => {
      const rect = page.getBoundingClientRect();
      const delta = Math.abs((rect.left + rect.right) / 2 - center);
      if (delta < distance) { distance = delta; activePage = index; }
    });
    current = activePage === 0 ? slides.length - 1 : activePage === pages.length - 1 ? 0 : activePage - 1;
    if (initialized && current !== from) {
      if (animate && !wrapping && activePage > 0 && activePage < pages.length - 1) arrive(current, from);
      else clearArrival();
    }
    if (!navigating) requested = current;
    previous.disabled = next.disabled = false;
    position.textContent = position.dataset.positionTemplate
      .replace('{current}', String(current + 1)).replace('{total}', String(slides.length));
    slides.forEach((slide, index) => { slide.inert = index !== current; });
    initialized = true;
  }

  function go(index, instant = false) {
    if (navigating && wrapping) {
      jumpTo(pages[requested + 1]);
      current = requested;
      activePage = current + 1;
    }
    wrapping = index < 0 || index >= slides.length;
    const target = index < 0 ? leading : index >= slides.length ? trailing : pages[index + 1];
    requested = ((index % slides.length) + slides.length) % slides.length;
    navigating = true;
    if (wrapping) clearArrival();
    if (instant || reducedMotion.matches) jumpTo(target);
    else track.scrollTo({left: offsetFor(target), behavior: 'smooth'});
    clearTimeout(settleTimer);
    settleTimer = setTimeout(settle, 250);
    syncPlayback(true);
  }

  function settle() {
    clearTimeout(settleTimer);
    update(!wrapping);
    navigating = false;
    requested = current;
    if (activePage === 0 || activePage === pages.length - 1) {
      jumpTo(pages[current + 1]);
      update(false);
    }
    wrapping = false;
    syncPlayback();
  }

  function interruptNavigation() {
    navigating = false;
    requested = current;
    interacting = true;
    syncPlayback();
  }
  function finishInteraction() {
    if (!interacting) return;
    interacting = false;
    syncPlayback(true);
  }

  previous.addEventListener('click', () => navigateByArrow(-1));
  next.addEventListener('click', () => navigateByArrow(1));
  track.addEventListener('keydown', event => {
    if (event.target !== track || event.altKey || event.ctrlKey || event.metaKey) return;
    keyboardFocus = true;
    let index;
    if (event.key === 'ArrowRight') index = requested + (rtl ? -1 : 1);
    if (event.key === 'ArrowLeft') index = requested + (rtl ? 1 : -1);
    if (event.key === 'Home') index = 0;
    if (event.key === 'End') index = slides.length - 1;
    if (index !== undefined) { event.preventDefault(); go(index); }
  });
  track.addEventListener('scroll', () => {
    if (!frame) frame = requestAnimationFrame(() => update());
    clearTimeout(settleTimer);
    settleTimer = setTimeout(settle, 250);
  }, {passive: true});
  track.addEventListener('scrollend', settle);
  track.addEventListener('pointerdown', interruptNavigation, {passive: true});
  track.addEventListener('pointerup', finishInteraction, {passive: true});
  track.addEventListener('pointercancel', finishInteraction, {passive: true});
  track.addEventListener('wheel', () => { navigating = false; requested = current; syncPlayback(true); }, {passive: true});
  document.addEventListener('pointerup', finishInteraction, {passive: true});
  toggle?.addEventListener('click', () => { paused = !paused; syncPlayback(); });
  // Only mouse hover pauses playback; touch pointerenter must not latch a pause.
  section.addEventListener('pointerenter', event => {
    if (event.pointerType === 'mouse') { hovered = true; syncPlayback(); }
  });
  section.addEventListener('pointerleave', event => {
    // Hover adds no exit delay; only a previous arrow click may still be waiting.
    if (event.pointerType === 'mouse') { hovered = false; syncPlayback(true, 0); }
  });
  // Mouse-click focus must not keep playback paused after the pointer leaves.
  section.addEventListener('pointerdown', () => {
    keyboardFocus = false;
    interacting = true;
    syncPlayback();
  }, {passive: true});
  section.addEventListener('pointercancel', finishInteraction, {passive: true});
  section.addEventListener('keydown', () => { keyboardFocus = true; syncPlayback(); });
  section.addEventListener('focusin', () => syncPlayback());
  section.addEventListener('focusout', () => setTimeout(() => syncPlayback(), 0));
  document.addEventListener('keydown', event => { if (event.key === 'Tab') { keyboardFocus = true; syncPlayback(); } });
  document.addEventListener('visibilitychange', () => syncPlayback());
  reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) clearArrival(); syncPlayback(); });
  if ('IntersectionObserver' in window) new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    syncPlayback();
  }).observe(section);
  if ('ResizeObserver' in window) {
    let width = track.clientWidth;
    new ResizeObserver(() => {
      if (width !== track.clientWidth) { width = track.clientWidth; go(current, true); }
      update(false);
    }).observe(track);
  }
  jumpTo(pages[1]);
  controls.hidden = false;
  update(false);
  syncPlayback();
});
