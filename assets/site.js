'use strict';
document.documentElement.classList.add('js');
const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
const languagePicker = document.querySelector('.language-picker');
function closeMenu() {
  navigation?.classList.remove('open');
  menuButton?.setAttribute('aria-expanded', 'false');
  languagePicker?.removeAttribute('open');
}
if (menuButton && navigation) {
  menuButton.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') !== 'true';
    menuButton.setAttribute('aria-expanded', String(open));
    navigation.classList.toggle('open', open);
    if (!open) languagePicker?.removeAttribute('open');
  });
  navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
}
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (languagePicker?.open) {
    languagePicker.removeAttribute('open');
    languagePicker.querySelector('summary')?.focus();
  } else if (menuButton?.getAttribute('aria-expanded') === 'true') {
    closeMenu();
    menuButton.focus();
  }
});
document.addEventListener('click', event => {
  if (languagePicker?.open && !languagePicker.contains(event.target)) languagePicker.removeAttribute('open');
});
