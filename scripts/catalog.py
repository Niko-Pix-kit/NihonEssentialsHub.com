"""Discover descriptive JSON cards and render accessible, localized carousels."""
from html import escape
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import json
import math
import re

CATEGORIES = ('products', 'applications', 'books')


def amazon_language_url(url, lang):
    """Keep the Japanese marketplace and select its requested interface language."""
    parsed = urlsplit(url)
    if (parsed.hostname or '').lower() not in ('amazon.co.jp', 'www.amazon.co.jp'):
        return url
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != 'language']
    query.append(('language', 'ja_JP' if lang == 'ja' else 'en_US'))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def canonical_language(code):
    code = code.lower().replace('_', '-')
    return {'zh-cn': 'zh-hans', 'zh-tw': 'zh-hant', 'in': 'id'}.get(code, code)


def render_app_languages(card, labels, lang, locale_meta=()):
    """Describe verified app UI languages independently of the marketing page language."""
    languages = card.get('availableLanguages', [])
    if not languages:
        return ''
    esc = lambda value: escape(str(value), quote=True)
    names, site_names = {}, {}
    for locale in locale_meta:
        name = locale['name']
        site_names[locale['code']] = name
        for field in ('code', 'tag', 'play'):
            if locale.get(field):
                names[canonical_language(locale[field])] = name
    names.update({'en': 'English', 'pt': 'Português'})
    supported = {canonical_language(code) for code in languages}
    current = canonical_language(lang)
    local_name = site_names.get(lang, lang)
    if lang in ('fr', 'es', 'it', 'pt', 'pt-br', 'pl', 'ru', 'uk'):
        local_name = local_name[:1].lower() + local_name[1:]
    if len(languages) == 1:
        code = canonical_language(languages[0])
        name = labels['appEnglishLanguage'] if code == 'en' else names.get(code, languages[0])
        summary = labels['appSingleLanguage'].format(language=name)
    else:
        summary = labels['appLanguages'].format(count=len(languages))
    local_note = ''
    if lang != 'en' and (current in supported or current.split('-')[0] in supported):
        local_note = f'<p class="catalog-local-language">{esc(labels["appLocalLanguage"].format(language=local_name))}</p>'
    entries = ''.join(f'<li lang="{esc(code)}" dir="auto">{esc(names.get(canonical_language(code), code))}</li>' for code in languages)
    return f'''<div class="catalog-app-languages"><p class="catalog-language-count">{esc(summary)}</p>{local_note}<details class="catalog-language-details"><summary>{esc(labels['appLanguageList'])}</summary><ul>{entries}</ul></details></div>'''


def safe_url(value, root=None, image=False):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError('A non-empty URL is required')
    parsed = urlsplit(value)
    if parsed.scheme == 'https' and parsed.netloc and not parsed.username and not parsed.password:
        return value
    if image and not parsed.scheme and not parsed.netloc and value.startswith('assets/catalog/'):
        path = Path(value)
        if '..' not in path.parts and not parsed.query and not parsed.fragment:
            if root is None or (Path(root) / path).is_file():
                return value
    raise ValueError(f'Invalid {"image" if image else "link"} URL: {value!r}')


def load_catalog(root):
    """Read every JSON card; fail the build on invalid data instead of publishing it."""
    root = Path(root)
    catalog = {}
    for category in CATEGORIES:
        items, seen = [], set()
        for path in sorted((root / 'data/catalog' / category).glob('*.json')):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                if item.get('published', True) is False:
                    continue
                identifier = item['id']
                if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', identifier) or identifier in seen:
                    raise ValueError('IDs must be unique lowercase slugs within a category')
                seen.add(identifier)
                if not isinstance(item.get('order', 100), (int, float)) or isinstance(item.get('order'), bool) or not math.isfinite(item.get('order', 100)):
                    raise ValueError('order must be a number')
                if 'publishedAt' in item:
                    if not isinstance(item['publishedAt'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', item['publishedAt']):
                        raise ValueError('publishedAt must be an ISO date (YYYY-MM-DD)')
                    date.fromisoformat(item['publishedAt'])
                if 'availableLanguages' in item:
                    languages = item['availableLanguages']
                    if not isinstance(languages, list) or not languages or any(not isinstance(code, str) or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', code) for code in languages):
                        raise ValueError('availableLanguages must be a non-empty list of language tags')
                    if len({canonical_language(code) for code in languages}) != len(languages):
                        raise ValueError('availableLanguages must not contain duplicate languages')
                variants = item['editions'] if category == 'books' else item['locales']
                if not isinstance(variants, dict) or not variants:
                    raise ValueError('At least one locale or edition is required')
                for locale, variant in variants.items():
                    for field in ('title', 'description'):
                        if not isinstance(variant.get(field), str) or not variant[field].strip():
                            raise ValueError(f'{locale}: missing {field}')
                    safe_url(variant.get('url', item.get('url')))
                    safe_url(variant.get('image', item.get('image')), root, image=True)
                    if variant.get('linkKind', 'product') not in ('product', 'search'):
                        raise ValueError('linkKind must be product or search')
                items.append(item)
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                raise ValueError(f'{path.relative_to(root)}: {error}') from error
        def sort_key(item):
            editorial = (item.get('order', 100), item['id'])
            if category == 'applications':
                published = item.get('publishedAt')
                return (not bool(published), -date.fromisoformat(published).toordinal() if published else 0, *editorial)
            return editorial
        catalog[category] = sorted(items, key=sort_key)
    return catalog


def select_variant(item, lang, category):
    """Prefer the requested edition, then its base language, then English."""
    variants = item['editions'] if category == 'books' else item['locales']
    language = lang.split('-')[0]
    keys = (lang, language, 'en')
    for key in keys:
        if key in variants:
            return {**item, **variants[key], 'editionLocale': key}
    return None


def render_carousels(catalog, labels, lang, base='./', author_url='', locale_meta=()):
    esc = lambda value: escape(str(value), quote=True)
    sections = []
    for category in CATEGORIES:
        copy = labels[category]
        cards = [variant for item in catalog[category] if (variant := select_variant(item, lang, category))]
        title_id, track_id = f'latest-{category}-title', f'latest-{category}-track'
        slides = []
        for index, card in enumerate(cards):
            image = card['image']
            if not image.startswith('https://'):
                image = base + image
            action = labels['bookLink'] if category == 'books' else labels['discover']
            if card.get('linkKind') == 'search':
                action = labels.get('bookSearch', labels['bookLink'])
            position = labels['position'].format(current=index + 1, total=len(cards))
            fallback = category == 'books' and card['editionLocale'] == 'en' and lang != 'en'
            language_note = f'<p class="catalog-edition">{esc(labels["englishEdition"])}</p>' if fallback else ''
            text_lang = f' lang="{esc(card["editionLocale"])}" dir="auto"' if category == 'books' else ''
            app_languages = render_app_languages(card, labels, lang, locale_meta) if category == 'applications' else ''
            url = amazon_language_url(card['url'], lang) if category == 'products' else card['url']
            slides.append(f'''<article class="catalog-slide" data-catalog-id="{esc(card['id'])}" aria-label="{esc(position)}"><div class="catalog-image"><img src="{esc(image)}" alt="{esc(card['title'])}" width="800" height="600" loading="lazy" decoding="async"></div><div class="catalog-copy"><p class="eyebrow">{esc(card.get('author', card.get('brand', '')))}</p>{language_note}<h3{text_lang}>{esc(card['title'])}</h3><p class="catalog-description"{text_lang}>{esc(card['description'])}</p>{app_languages}<a class="external-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(action)}<span aria-hidden="true">↗</span></a></div></article>''')
        controls = ''
        if len(cards) > 1:
            controls = f'''<div class="carousel-controls" hidden><span class="carousel-position" aria-live="polite" aria-atomic="true" data-position-template="{esc(labels['position'])}">{esc(labels['position'].format(current=1, total=len(cards)))}</span><button type="button" data-carousel-prev aria-label="{esc(labels['previous'])}" aria-controls="{track_id}"><span aria-hidden="true">←</span></button><button type="button" data-carousel-toggle aria-label="{esc(labels['pause'])}" data-pause-label="{esc(labels['pause'])}" data-play-label="{esc(labels['play'])}" aria-pressed="false"><span aria-hidden="true">Ⅱ</span></button><button type="button" data-carousel-next aria-label="{esc(labels['next'])}" aria-controls="{track_id}"><span aria-hidden="true">→</span></button></div>'''
        content = f'<div id="{track_id}" class="carousel-track" tabindex="0">{"".join(slides)}</div>' if cards else f'<div class="catalog-empty"><p>{esc(labels["emptyBooks"])}</p><a class="external-link" href="{esc(author_url)}" target="_blank" rel="noopener noreferrer">{esc(labels["authorLink"])}<span aria-hidden="true">↗</span></a></div>'
        sections.append(f'''<section class="catalog-section catalog-{category}" id="latest-{category}" aria-labelledby="{title_id}" data-carousel data-carousel-autoplay="1000"><div class="container"><div class="catalog-heading"><div class="section-heading"><p class="eyebrow">{esc(copy['eyebrow'])}</p><h2 id="{title_id}">{esc(copy['title'])}</h2><p>{esc(copy['description'])}</p></div>{controls}</div>{content}</div></section>''')
    return '\n'.join(sections)
