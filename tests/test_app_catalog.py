"""Regression checks for release ordering and genuine app language support."""
from html.parser import HTMLParser
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from catalog import canonical_language, load_catalog, render_app_languages, render_carousels

LOCALES = json.loads((ROOT / 'data/i18n/locales.json').read_text())
LABELS = json.loads((ROOT / 'data/catalog/labels.json').read_text())


class CardText(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.cards = {}
        self.current = None
        self.text = ''
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == 'article':
            self.current = dict(attrs).get('data-catalog-id')
            if self.current:
                self.cards[self.current] = ''

    def handle_endtag(self, tag):
        if tag == 'article':
            self.current = None

    def handle_data(self, data):
        self.text += data
        if self.current:
            self.cards[self.current] += data


class AppCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'data/catalog/applications'
        self.folder.mkdir(parents=True)

    def app(self, identifier, **fields):
        return {
            'id': identifier, 'order': 100,
            'url': 'https://example.com/app',
            'image': 'https://example.com/cover.webp',
            'locales': {'en': {'title': identifier, 'description': 'Fixture description.'}},
            **fields,
        }

    def write(self, item):
        path = self.folder / f'{item["id"]}.json'
        path.write_text(json.dumps(item), encoding='utf-8')
        return path

    def test_latest_release_wins_over_editorial_order_and_undated_apps_follow(self):
        records = [
            self.app('older', order=1, publishedAt='2026-06-26'),
            self.app('newer-b', order=20, publishedAt='2026-09-28'),
            self.app('newer-a', order=10, publishedAt='2026-09-28'),
            self.app('undated-b', order=2),
            self.app('undated-a', order=1),
        ]
        for item in records:
            self.write(item)
        actual = [item['id'] for item in load_catalog(self.root)['applications']]
        self.assertEqual(actual, ['newer-a', 'newer-b', 'older', 'undated-a', 'undated-b'])

    def test_bad_release_dates_fail_instead_of_silently_changing_the_order(self):
        invalid = ['2026-02-30', '2026-13-01', '2026-9-8', '28/09/2026',
                   '2026-09-28T12:00:00Z', '', 20260928]
        for value in invalid:
            with self.subTest(publishedAt=value):
                self.write(self.app('invalid-date', publishedAt=value))
                with self.assertRaises(ValueError):
                    load_catalog(self.root)
        self.write(self.app('invalid-date', publishedAt='2024-02-29'))
        self.assertEqual(load_catalog(self.root)['applications'][0]['publishedAt'], '2024-02-29')

    def test_language_lists_reject_empty_malformed_and_equivalent_duplicates(self):
        invalid = [[], 'en', [''], ['fr_FR'], ['en', 7], ['en', 'en'],
                   ['en', 'EN'], ['zh-CN', 'zh-Hans'], ['zh-TW', 'zh-Hant'], ['in', 'id']]
        for value in invalid:
            with self.subTest(availableLanguages=value):
                self.write(self.app('invalid-languages', availableLanguages=value))
                with self.assertRaises(ValueError):
                    load_catalog(self.root)

    def test_language_aliases_match_the_same_language_without_merging_portuguese_regions(self):
        for left, right in [('zh-CN', 'zh-Hans'), ('zh-TW', 'zh-Hant'),
                            ('in', 'id'), ('pt-br', 'pt-BR')]:
            with self.subTest(alias=left):
                self.assertEqual(canonical_language(left), canonical_language(right))
        self.assertNotEqual(canonical_language('pt'), canonical_language('pt-BR'))

    def test_french_marketing_copy_does_not_imply_french_app_support(self):
        catalog = load_catalog(ROOT)
        apps = {app['id']: app for app in catalog['applications']}
        graph = CardText(render_app_languages(apps['pix-graph'], LABELS['fr'], 'fr', LOCALES)).text
        moments = CardText(render_app_languages(apps['pix-moments'], LABELS['fr'], 'fr', LOCALES)).text
        self.assertIn('Disponible en anglais', graph)
        self.assertNotIn('Français', graph)
        self.assertNotIn('19 langues', graph)
        self.assertIn('Disponible en 19 langues', moments)
        self.assertIn('Français', moments)
        self.assertIn('日本語', moments)
        # An old or incomplete fiche may omit support metadata; translated copy is no evidence.
        no_support_metadata = self.app('unverified', locales={
            'fr': {'title': 'Application', 'description': 'Présentation française.'}})
        self.assertEqual(render_app_languages(no_support_metadata, LABELS['fr'], 'fr', LOCALES), '')

    def test_all_site_languages_render_real_app_availability_and_the_language_list(self):
        catalog = load_catalog(ROOT)
        for locale in LOCALES:
            code = locale['code']
            labels = LABELS[code]
            with self.subTest(locale=code):
                markup = render_carousels(catalog, labels, code, locale_meta=LOCALES)
                cards = CardText(markup).cards
                self.assertIn(labels['appSingleLanguage'].format(language=labels['appEnglishLanguage']), cards['pix-graph'])
                self.assertIn(labels['appLanguages'].format(count=19), cards['pix-moments'])
                self.assertIn(labels['appLanguageList'], cards['pix-moments'])
                self.assertIn('Français', cards['pix-moments'])
                self.assertIn('日本語', cards['pix-moments'])


if __name__ == '__main__':
    unittest.main()
