"""Run dependency-free JavaScript behavior tests from the standard test command."""
from pathlib import Path
from html.parser import HTMLParser
import json
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CarouselRuntimeTests(unittest.TestCase):
    def test_pause_and_resume_labels_are_localized_on_every_homepage(self):
        labels = json.loads((ROOT / 'data/catalog/labels.json').read_text())
        class Controls(HTMLParser):
            def __init__(self, source):
                super().__init__()
                self.buttons, self.sections = [], []
                self.feed(source)
            def handle_starttag(self, tag, attributes):
                attrs = dict(attributes)
                if tag == 'button' and 'data-carousel-toggle' in attrs:
                    self.buttons.append(attrs)
                if tag == 'section' and 'data-carousel' in attrs:
                    self.sections.append(attrs)
        for code, strings in labels.items():
            page = ROOT / ('' if code == 'en' else code) / 'index.html'
            parsed = Controls(page.read_text())
            with self.subTest(locale=code):
                self.assertEqual(len(parsed.buttons), 3)
                self.assertEqual(len(parsed.sections), 3)
                self.assertTrue(strings['pause'].strip())
                self.assertTrue(strings['play'].strip())
                for button in parsed.buttons:
                    self.assertEqual(button['aria-label'], strings['pause'])
                    self.assertEqual(button['data-pause-label'], strings['pause'])
                    self.assertEqual(button['data-play-label'], strings['play'])
                self.assertTrue(all(s['data-carousel-autoplay'] == '1000' for s in parsed.sections))

    def test_carousel_behavior(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js 18+ is required for carousel runtime checks')
        result = subprocess.run([node, '--test', 'tests/carousels.test.cjs'],
                                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
