"""End-to-end regression checks for file-driven homepage catalogues."""
from html.parser import HTMLParser
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCALES = json.loads((ROOT / 'data/i18n/locales.json').read_text())


class Homepage(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.sections = []
        self.stack = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section' and self.stack and self.stack[-1] == 'main':
            self.current = {'attrs': attrs, 'text': '', 'links': [], 'images': []}
            self.sections.append(self.current)
        if self.current:
            if tag == 'a':
                self.current['links'].append(attrs.get('href', ''))
            if tag == 'img':
                self.current['images'].append(attrs.get('src', ''))
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack:
                popped = self.stack.pop()
                if popped == tag:
                    break
        if tag == 'section' and self.stack and self.stack[-1] == 'main':
            self.current = None

    def handle_data(self, data):
        if self.current:
            self.current['text'] += data


sys.path.insert(0, str(ROOT / 'scripts'))
from catalog import load_catalog, render_carousels, select_variant


class CatalogContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        image = self.root / 'assets/catalog/applications/fixture.webp'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'fixture')

    def write(self, category, record, filename=None):
        folder = self.root / 'data/catalog' / category
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (filename or record['id'] + '.json')
        path.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        return path

    def app(self, identifier, order=100, title='Fixture'):
        return {'id': identifier, 'order': order, 'brand': 'Fixture',
                'url': 'https://example.com/app?x=1&y=2',
                'image': 'assets/catalog/applications/fixture.webp',
                'locales': {'en': {'title': title, 'description': 'A descriptive fixture.'}}}

    def test_new_json_is_discovered_without_a_code_change_and_order_is_stable(self):
        self.write('applications', self.app('middle', 50))
        self.assertEqual([x['id'] for x in load_catalog(self.root)['applications']], ['middle'])
        self.write('applications', self.app('later', 900))
        self.write('applications', self.app('first', 1))
        self.write('applications', self.app('tie', 50))
        self.assertEqual([x['id'] for x in load_catalog(self.root)['applications']], ['first', 'middle', 'tie', 'later'])

    def test_books_prefer_the_requested_language_then_use_the_english_edition(self):
        book = {'id': 'fixture-book', 'editions': {language: {
            'title': f'Book {language}', 'description': f'Description {language}',
            'url': f'https://example.com/{language}', 'image': f'https://example.com/{language}.jpg'
        } for language in ('en', 'fr', 'pt')}}
        for language in ('en', 'fr', 'pt'):
            with self.subTest(language=language):
                chosen = select_variant(book, language, 'books')
                self.assertEqual(chosen['title'], f'Book {language}')
                self.assertEqual(chosen['url'], f'https://example.com/{language}')
                self.assertEqual(chosen['image'], f'https://example.com/{language}.jpg')
        for language in ('ja', 'ar', 'de'):
            with self.subTest(fallback_language=language):
                chosen = select_variant(book, language, 'books')
                self.assertEqual(chosen['editionLocale'], 'en')
                self.assertEqual(chosen['title'], 'Book en')
                self.assertEqual(chosen['description'], 'Description en')
                self.assertEqual(chosen['url'], 'https://example.com/en')
                self.assertEqual(chosen['image'], 'https://example.com/en.jpg')
        without_english = dict(book, editions={'fr': book['editions']['fr']})
        self.assertIsNone(select_variant(without_english, 'ja', 'books'))
        self.assertEqual(select_variant(without_english, 'fr', 'books')['editionLocale'], 'fr')
        self.assertEqual(select_variant(book, 'pt-br', 'books')['editionLocale'], 'pt')
        exact = dict(book, editions={**book['editions'], 'pt-br': {
            'title': 'Brazil edition', 'description': 'Brazil description',
            'url': 'https://example.com/br', 'image': 'https://example.com/br.jpg'}})
        self.assertEqual(select_variant(exact, 'pt-br', 'books')['url'], 'https://example.com/br')

    def test_render_escapes_content_and_url_attributes(self):
        title = 'Fixture & <strong>plain text</strong> "quoted"'
        self.write('applications', self.app('fixture-escaped', title=title))
        labels = json.loads((ROOT / 'data/catalog/labels.json').read_text())['en']
        html = render_carousels(load_catalog(self.root), labels, 'en', author_url='https://example.com/author')
        self.assertIn('Fixture &amp; &lt;strong&gt;plain text&lt;/strong&gt;', html)
        self.assertNotIn('<strong>plain text</strong>', html)
        self.assertIn('https://example.com/app?x=1&amp;y=2', html)

    def test_malformed_json_reports_the_bad_filename(self):
        path = self.root / 'data/catalog/applications/broken.json'
        path.parent.mkdir(parents=True)
        path.write_text('{this is not JSON', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'broken.json'):
            load_catalog(self.root)

    def test_unsafe_schemes_missing_images_and_path_traversal_are_rejected(self):
        cases = [('url', 'javascript:alert(1)'), ('url', '//example.com/app'),
                 ('url', 'http://example.com/app'), ('image', '../outside.webp'),
                 ('image', 'assets/catalog/../../outside.webp'),
                 ('image', 'assets/catalog/missing.webp'), ('image', 'data:image/svg+xml,bad')]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                fixture = self.app('fixture-invalid')
                fixture[field] = value
                path = self.write('applications', fixture)
                with self.assertRaises(ValueError):
                    load_catalog(self.root)
                path.unlink()

    def test_invalid_edition_is_not_published_and_duplicate_ids_are_rejected(self):
        first = self.app('same')
        self.write('applications', first, 'one.json')
        self.write('applications', first, 'two.json')
        with self.assertRaisesRegex(ValueError, 'unique'):
            load_catalog(self.root)
        (self.root / 'data/catalog/applications/two.json').unlink()
        bad = self.app('bad-book')
        bad['editions'] = {'fr': {'title': 'Incomplete edition'}}
        self.write('books', bad)
        with self.assertRaises(ValueError):
            load_catalog(self.root)

    def test_drafts_can_be_added_without_being_published(self):
        self.write('applications', {'id': 'draft', 'published': False})
        self.assertEqual(load_catalog(self.root)['applications'], [])


class HomepageBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / 'site'
        cls.root.mkdir()
        # One build copy serves all locale checks, without copying Git history or generated pages.
        for name in ('scripts', 'data', 'assets'):
            shutil.copytree(ROOT / name, cls.root / name, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT / 'favicon.ico', cls.root / 'favicon.ico')
        cls.result = subprocess.run([sys.executable, 'scripts/build.py'], cwd=cls.root, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_three_localized_sections_immediately_follow_mission_in_all_languages(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        labels = json.loads((self.root / 'data/catalog/labels.json').read_text())
        for locale in LOCALES:
            code = locale['code']
            with self.subTest(locale=code):
                html = (self.root / ('' if code == 'en' else code) / 'index.html').read_text()
                page = Homepage(html)
                mission = next(i for i, section in enumerate(page.sections) if section['attrs'].get('id') == 'mission')
                following = page.sections[mission + 1:mission + 4]
                self.assertEqual([x['attrs'].get('id') for x in following], ['latest-products', 'latest-applications', 'latest-books'])
                for section, category in zip(following, ('products', 'applications', 'books')):
                    self.assertIn(labels[code][category]['title'], section['text'])
                self.assertIn('assets/carousels.js', html)

    def test_all_homepages_show_books_with_matching_or_english_cover_title_and_link(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        books = [json.loads(path.read_text()) for path in (self.root / 'data/catalog/books').glob('*.json')]
        self.assertTrue(books, 'The live catalogue must contain book fiches')
        for locale in LOCALES:
            code = locale['code']
            html = (self.root / ('' if code == 'en' else code) / 'index.html').read_text()
            section = next(section for section in Homepage(html).sections if section['attrs'].get('id') == 'latest-books')
            for book in books:
                editions = book['editions']
                expected = editions.get(code) or editions.get(code.split('-')[0]) or editions.get('en')
                if expected is None:
                    continue
                with self.subTest(locale=code, book=book['id']):
                    self.assertIn(expected['title'], section['text'])
                    self.assertIn(expected.get('url', book.get('url')), section['links'])
                    self.assertTrue(any(image.endswith(expected.get('image', book.get('image'))) for image in section['images']))


if __name__ == '__main__':
    unittest.main()
