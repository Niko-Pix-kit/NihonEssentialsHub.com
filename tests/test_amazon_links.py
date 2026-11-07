"""Amazon Japan language routing and BAMBOOM catalogue regression checks."""
from html.parser import HTMLParser
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import catalog

LOCALES = json.loads((ROOT / 'data/i18n/locales.json').read_text())
STORE_PATH = '/stores/page/61C25806-DBA1-428D-98F5-53DD6FBB7863'
VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class HomepageLinks(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            section = next((a.get('id') for t, a in reversed(self.stack) if t == 'section'), None)
            card = next((a.get('data-catalog-id') for t, a in reversed(self.stack) if t == 'article'), None)
            self.links.append({'href': attrs.get('href', ''), 'section': section, 'card': card})
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        if any(t == tag for t, _ in self.stack):
            while self.stack:
                if self.stack.pop()[0] == tag:
                    break


def webp_declares_alpha(path):
    data = path.read_bytes()
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return False
    offset = 12
    while offset + 8 <= len(data):
        kind, length = data[offset:offset + 4], struct.unpack('<I', data[offset + 4:offset + 8])[0]
        payload = data[offset + 8:offset + 8 + length]
        if kind == b'ALPH' or (kind == b'VP8X' and payload and payload[0] & 0x10):
            return True
        if kind == b'VP8L' and len(payload) >= 5 and payload[0] == 0x2f:
            return bool(struct.unpack('<I', payload[1:5])[0] & (1 << 28))
        offset += 8 + length + (length & 1)
    return False


class AmazonLanguageUrlTests(unittest.TestCase):
    def route(self, url, locale):
        return catalog.amazon_language_url(url, locale)

    def assert_language(self, url, expected):
        self.assertEqual([value for key, value in parse_qsl(urlsplit(url).query) if key == 'language'], [expected])

    def test_japanese_products_and_stores_request_japanese(self):
        for hostname in ('amazon.co.jp', 'www.amazon.co.jp'):
            for path in ('/dp/B0FDFVGCWS', STORE_PATH):
                with self.subTest(hostname=hostname, path=path):
                    result = self.route(f'https://{hostname}{path}', 'ja')
                    self.assertEqual(urlsplit(result).path, path)
                    self.assert_language(result, 'ja_JP')

    def test_all_other_site_languages_request_english(self):
        for locale in LOCALES:
            code = locale['code']
            if code == 'ja':
                continue
            with self.subTest(locale=code):
                self.assert_language(self.route('https://www.amazon.co.jp/dp/B0FDFVGCWS', code), 'en_US')

    def test_existing_language_parameters_are_replaced_once_with_other_data_preserved(self):
        original = 'https://www.amazon.co.jp/dp/B0FDFVGCWS?tag=test-22&language=de_DE&ref_=abc&language=fr_FR&blank=#details'
        for locale, expected in (('ja', 'ja_JP'), ('fr', 'en_US')):
            with self.subTest(locale=locale):
                result = self.route(original, locale)
                before, after = urlsplit(original), urlsplit(result)
                self.assertEqual((after.scheme, after.netloc, after.path, after.fragment), (before.scheme, before.netloc, before.path, before.fragment))
                self.assertEqual([(key, value) for key, value in parse_qsl(after.query, keep_blank_values=True) if key != 'language'], [('tag', 'test-22'), ('ref_', 'abc'), ('blank', '')])
                self.assert_language(result, expected)
                self.assertEqual(self.route(result, locale), result, 'Routing should be idempotent')

    def test_other_hosts_and_localized_book_links_remain_byte_for_byte_unchanged(self):
        urls = (
            'https://www.amazon.fr/dp/BOOKFR?language=fr_FR#book',
            'https://www.amazon.de/dp/BOOKDE?tag=test&language=de_DE',
            'https://www.amazon.com/dp/BOOKEN?language=en_US',
            'https://us.amazon.com/stores/author/B0GWS78TV2/about',
            'https://amazon.co.jp.example.org/dp/example?language=fr_FR',
            'https://notamazon.co.jp/dp/example',
            'https://pix-kit.com/fr/apps/pix-graph/',
        )
        for url in urls:
            for locale in ('ja', 'fr'):
                with self.subTest(url=url, locale=locale):
                    self.assertEqual(self.route(url, locale), url)


class BamboomHomepageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / 'site'
        cls.root.mkdir()
        for name in ('scripts', 'data'):
            shutil.copytree(ROOT / name, cls.root / name, ignore=shutil.ignore_patterns('__pycache__'))
        # The generator only reads assets; symlinking avoids duplicating the product imagery.
        (cls.root / 'assets').symlink_to(ROOT / 'assets', target_is_directory=True)
        shutil.copy2(ROOT / 'favicon.ico', cls.root / 'favicon.ico')
        cls.result = subprocess.run([sys.executable, 'scripts/build.py'], cwd=cls.root, capture_output=True, text=True)
        cls.catalog = catalog.load_catalog(ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def page_links(self, code):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        html = (self.root / ('' if code == 'en' else code) / 'index.html').read_text()
        return HomepageLinks(html).links

    def test_every_product_cta_and_both_bamboom_store_links_use_the_site_amazon_language(self):
        products = self.catalog['products']
        self.assertGreaterEqual(len(products), 5)
        for locale in LOCALES:
            code = locale['code']
            expected_language = 'ja_JP' if code == 'ja' else 'en_US'
            links = self.page_links(code)
            product_links = [link for link in links if link['section'] == 'latest-products']
            store_links = [link for link in links if link['section'] == 'brands' and urlsplit(link['href']).path == STORE_PATH]
            with self.subTest(locale=code):
                self.assertEqual(len(product_links), len(products))
                self.assertEqual(len(store_links), 2, 'Both the BAMBOOM logo and CTA must link to the store')
                for link in product_links + store_links:
                    parsed = urlsplit(link['href'])
                    self.assertIn(parsed.hostname, ('amazon.co.jp', 'www.amazon.co.jp'))
                    self.assertEqual([value for key, value in parse_qsl(parsed.query) if key == 'language'], [expected_language])
                for item in products:
                    actual = next(link['href'] for link in product_links if link['card'] == item['id'])
                    variant = catalog.select_variant(item, code, 'products')
                    self.assertEqual(urlsplit(actual).path, urlsplit(variant['url']).path)

    def test_book_links_keep_the_selected_edition_url(self):
        for locale in LOCALES:
            code = locale['code']
            links = [link for link in self.page_links(code) if link['section'] == 'latest-books']
            for book in self.catalog['books']:
                edition = catalog.select_variant(book, code, 'books')
                if edition:
                    with self.subTest(locale=code, book=book['id']):
                        self.assertEqual(next(link['href'] for link in links if link['card'] == book['id']), edition['url'])

    def test_of_05_has_the_verified_asin_all_locales_and_a_transparent_webp(self):
        matches = [item for item in self.catalog['products'] if item['id'] == 'bamboom-of-05']
        self.assertEqual(len(matches), 1)
        product = matches[0]
        self.assertEqual(set(product['locales']), {locale['code'] for locale in LOCALES})
        for code in product['locales']:
            edition = catalog.select_variant(product, code, 'products')
            self.assertIn('B0FDFVGCWS', urlsplit(edition['url']).path)
        image = ROOT / product['image']
        self.assertEqual(image.suffix, '.webp')
        self.assertTrue(image.is_file())
        self.assertTrue(webp_declares_alpha(image), 'OF-05 WebP must preserve its transparent background')


if __name__ == '__main__':
    unittest.main()
