"""Check the generated consent controls and policy text for every locale."""

import hashlib
import json
from html import escape
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / 'data/i18n'
ROUTES = ('', 'about', 'contact', 'privacy', 'team', 'cookie-policy')
ANALYTICS_COOKIE = '_ga_LHR5R3H8ZP'


class AnalyticsPageTests(unittest.TestCase):
    def test_localized_pages_load_only_the_first_party_consent_gate(self):
        version = hashlib.sha256((ROOT / 'assets/analytics.js').read_bytes()).hexdigest()[:12]
        for locale in json.loads((I18N / 'locales.json').read_text()):
            code = locale['code']
            directory = ROOT if code == 'en' else ROOT / code
            for route in ROUTES:
                with self.subTest(locale=code, route=route):
                    page = (directory / route / 'index.html').read_text()
                    self.assertIn(f'analytics.js?v={version}', page)
                    self.assertLess(page.index('consent.js?v='), page.index('analytics.js?v='))
                    self.assertIn('id="cookie-analytics"', page)
                    self.assertIn('id="cookie-preferences"', page)
                    self.assertNotIn('googletagmanager.com', page)
                    self.assertNotIn('G-Y3KP2PKKS3', page)
            cookies = json.loads((I18N / f'{code}.json').read_text())['cookies']
            for route in ('privacy', 'cookie-policy'):
                with self.subTest(locale=code, policy=route):
                    page = (directory / route / 'index.html').read_text()
                    self.assertIn(ANALYTICS_COOKIE, page)
                    self.assertIn(escape(cookies['analyticsDescription']), page)

    def test_not_found_page_is_untracked(self):
        page = (ROOT / '404.html').read_text()
        self.assertNotIn('analytics.js', page)
        self.assertNotIn('googletagmanager.com', page)
