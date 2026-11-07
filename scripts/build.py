#!/usr/bin/env python3
"""Generate the localized public website from its content files."""
from pathlib import Path
from html import escape
import json
import hashlib
import re
from catalog import load_catalog, render_carousels, amazon_language_url

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://nihonessentialshub.com'
BAMBOOM = 'https://www.amazon.co.jp/stores/page/61C25806-DBA1-428D-98F5-53DD6FBB7863'
AUTHOR = 'https://us.amazon.com/stores/author/B0GWS78TV2/about'
EMAIL = 'info@nihonessentialshub.com'
CORPORATE_NUMBER = '6290003014525'
CORPORATE_REGISTRY = 'https://info.gbiz.go.jp/hojin/ichiran?hojinBango=6290003014525'
TRADEMARK_RECORDS = {
    '6953015': 'https://www.j-platpat.inpit.go.jp/c1801/TR/JP-2024-117812/40/en',
    '6953016': 'https://www.j-platpat.inpit.go.jp/c1801/TR/JP-2024-117813/40/en',
    '6953017': 'https://www.j-platpat.inpit.go.jp/c1801/TR/JP-2024-117814/40/en',
    '2025-145412': 'https://www.j-platpat.inpit.go.jp/c1801/TR/JP-2025-145412/40/en',
    '7094172': 'https://www.j-platpat.inpit.go.jp/c1801/TR/JP-2026-014245/40/en',
}
LOCALES = json.loads((ROOT / 'data/i18n/locales.json').read_text())
META = {item['code']: item for item in LOCALES}
CONTENT = {code: json.loads((ROOT / 'data/i18n' / f'{code}.json').read_text()) for code in META}
CATALOG = load_catalog(ROOT)
CATALOG_LABELS = json.loads((ROOT / 'data/catalog/labels.json').read_text(encoding='utf-8'))
ROUTES = ('/', '/about/', '/contact/', '/privacy/', '/team/', '/cookie-policy/')


def esc(value):
    return escape(str(value), quote=True)


def prefix(lang):
    return '' if lang == 'en' else f'{lang}/'


def absolute(lang, route):
    return f'{SITE}/{prefix(lang)}{route.lstrip("/")}'


def external(url, label):
    return f'<a class="external-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}<span aria-hidden="true">↗</span></a>'


def trademark_notice(text):
    # Registration and application numbers link to their corresponding dossiers.
    numbers = '|'.join(re.escape(number) for number in TRADEMARK_RECORDS)
    def reference(match):
        number = match[0]
        return f'<a href="{esc(TRADEMARK_RECORDS[number])}" target="_blank" rel="noopener noreferrer" title="J-PlatPat: {number}"><bdi dir="ltr">{number}</bdi></a>'
    return re.sub(r'(?<!\d)(?:' + numbers + r')(?!\d)', reference, esc(text))


def favicon_links(base):
    """Serve the approved symbol in modern, legacy and touch-icon formats."""
    icons = (
        ('favicon.ico', 'icon', 'image/x-icon', '16x16 32x32 48x48'),
        ('assets/brand/favicon-32.png', 'icon', 'image/png', '32x32'),
        ('assets/brand/favicon-192.png', 'icon', 'image/png', '192x192'),
        ('assets/brand/favicon.svg', 'icon', 'image/svg+xml', 'any'),
        ('assets/brand/apple-touch-icon.png', 'apple-touch-icon', 'image/png', '180x180'),
    )
    result = ''
    for path, rel, mime, sizes in icons:
        version = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()[:12]
        result += f'<link rel="{rel}" type="{mime}" sizes="{sizes}" href="{base}{path}?v={version}">'
    return result


def build_page(lang, route):
    c, meta = CONTENT[lang], META[lang]
    bamboom_url = amazon_language_url(BAMBOOM, lang)
    depth = (lang != 'en') + (route != '/')
    base = '../' * depth if depth else './'
    asset = f'{base}assets/'

    def versioned(name):
        digest = hashlib.sha256((ROOT / 'assets' / name).read_bytes()).hexdigest()[:12]
        return asset + name + '?v=' + digest

    def link(target='/', language=lang):
        return f'{base}{prefix(language)}{target.lstrip("/")}'

    titles = {'/': c['seoTitle'], '/about/': c['aboutLabel'], '/contact/': c['contactLabel'], '/privacy/': c['privacyTitle'], '/team/': c['team']['title'], '/cookie-policy/': c['cookies']['title']}
    descriptions = {'/': c['description'], '/about/': c['aboutLead'], '/contact/': c['contactText'], '/privacy/': c['privacyContent'][0][1], '/team/': c['team']['subtitle'] + ' ' + c['team']['tagline'], '/cookie-policy/': c['cookies']['intro']}
    page_description = descriptions[route]
    nav_items = [(link(), c['navHome'], '/'), (link() + '#mission', c['nav'][0], None), (link() + '#brands', c['nav'][1], None), (link() + '#authors', c['navAuthors'], None), (link('/team/'), c['navTeam'], '/team/'), (link('/about/'), c['nav'][2], '/about/'), (link('/contact/'), c['nav'][3], '/contact/')]
    nav = ''.join(f'<a href="{esc(href)}"'+(' aria-current="page"' if route == target else '')+f'>{esc(label)}</a>' for href, label, target in nav_items)
    languages = ''.join(f'<a href="{esc(link(route, code))}" lang="{esc(META[code]["tag"])}" data-locale-choice="{code}"'+(' aria-current="page"' if code == lang else '')+f'>{esc(META[code]["name"])}</a>' for code in CONTENT)
    language_menu = f'''<details class="language-picker"><summary><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a20 20 0 0 1 0 18 20 20 0 0 1 0-18Z"/></svg><span>{esc(meta['name'])}</span><span data-language-mode hidden>{esc(c['languageMode'])}</span><span aria-hidden="true">⌄</span></summary><div class="language-options"><button type="button" data-language-auto hidden>{esc(c['autoLabel'])} ↻</button>{languages}</div></details>'''
    alternates = ''.join(f'<link rel="alternate" hreflang="{esc(META[code]["tag"])}" href="{esc(absolute(code, route))}">' for code in CONTENT)
    config = json.dumps({'locales': LOCALES}, ensure_ascii=False)
    head = f'''<!doctype html>
<html lang="{esc(meta['tag'])}" dir="{meta.get('dir', 'ltr')}" data-locale="{lang}" data-route="{route}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titles[route])} | Nihon Essentials Hub</title><meta name="description" content="{esc(page_description)}"><meta name="robots" content="index,follow,max-image-preview:large"><meta name="theme-color" content="#152b3a">
<link rel="canonical" href="{esc(absolute(lang, route))}">{alternates}<link rel="alternate" hreflang="x-default" href="{esc(absolute('en', route))}">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(titles[route])} | Nihon Essentials Hub"><meta property="og:description" content="{esc(page_description)}"><meta property="og:locale" content="{esc(meta['og'])}"><meta property="og:url" content="{esc(absolute(lang, route))}">
<meta name="referrer" content="strict-origin-when-cross-origin"><meta property="og:image" content="{SITE}/assets/brand/neh-social.png"><meta property="og:image:alt" content="Nihon Essentials Hub">
{favicon_links(base)}<link rel="stylesheet" href="{versioned('site.css')}"><script defer src="{versioned('site.js')}"></script><script defer src="{versioned('brand-letters.js')}"></script><script id="locale-config" type="application/json">{config}</script><script defer src="{versioned('consent.js')}"></script><script defer src="{versioned('language.js')}"></script><script defer src="{versioned('analytics.js')}"></script></head>
<body><a class="skip-link" href="#main">{esc(c['skip'])}</a>
<header class="site-header"><div class="container header-inner"><a class="company-logo" href="{esc(link())}"><img src="{asset}brand/neh-wordmark-dark.svg" alt="Nihon Essentials Hub" width="360" height="88"></a><button type="button" class="menu-toggle" aria-expanded="false" aria-controls="navigation"><span>{esc(c['menu'])}</span><span class="menu-lines" aria-hidden="true"></span></button><nav id="navigation" class="nav-links" aria-label="{esc(c['menu'])}">{nav}{language_menu}</nav></div></header>'''
    if route == '/':
        verbs = ''.join(f'<span>{esc(word)}</span>' for word in c['principles'])
        longest = max(len(word) for word in c['principles'])
        compact = ' compact-heading' if longest > 12 else ''
        missions = ''
        for i, (title, text) in enumerate(c['caps']):
            missions += f'<article class="mission-item"><span class="item-number">0{i+1}</span><h3>{esc(title)}</h3><p>{esc(text)}</p></article>'
        body = f'''<main id="main">
<section class="hero"><div class="container"><p class="eyebrow">{esc(c['heroEyebrow'])}</p><div class="hero-layout"><h1 class="hero-heading{compact}">{verbs}</h1><div class="hero-copy"><p>{esc(c['heroText'])}</p><a class="primary-link" href="#mission">{esc(c['heroAction'])}<span aria-hidden="true">↓</span></a><p class="hero-note">{esc(c['heroNote'])}</p></div></div></div></section>
<section class="mission-section" id="mission"><div class="container"><div class="section-heading"><p class="eyebrow">{esc(c['missionLabel'])}</p><h2>{esc(c['missionTitle'])}</h2><p>{esc(c['missionText'])}</p></div><div class="mission-grid">{missions}</div></div></section>
<section class="brands-section" id="brands"><div class="container"><div class="section-heading"><p class="eyebrow">{esc(c['brandsLabel'])}</p><h2>{esc(c['brandsTitle'])}</h2><p>{esc(c['brandsText'])}</p></div><div class="brands-grid">
<article class="brand-card"><h3 class="brand-logo-area"><a href="{esc(bamboom_url)}" target="_blank" rel="noopener noreferrer" aria-label="{esc(c['bamLink'])}"><img class="brand-logo bamboom-logo" src="{asset}brand/bamboom-logo.png" alt="BAMBOOM" width="2048" height="448" loading="lazy"></a></h3><p>{esc(c['bamText'])}</p><p class="brand-trademark">{trademark_notice(c['bamTrademark'])}</p>{external(bamboom_url, c['bamLink'])}</article>
<article class="brand-card"><h3 class="brand-logo-area"><a href="https://pix-kit.com/" target="_blank" rel="noopener noreferrer" aria-label="{esc(c['pixLink'])}"><img class="brand-logo pixkit-logo" src="{asset}brand/pix-kit-logo.png" alt="Pix-kit" width="346" height="132" loading="lazy"></a></h3><p data-pixkit-copy>{esc(c['pixText'])}</p><p class="brand-trademark">{trademark_notice(c['pixTrademark'])}</p>{external('https://pix-kit.com/', c['pixLink'])}</article>
</div></div></section>
<section class="authors-section" id="authors"><div class="container"><div class="section-heading"><p class="eyebrow">{esc(c['authors']['label'])}</p><h2>{esc(c['authors']['title'])}</h2></div><article class="author-card"><a class="author-photo-link" href="{AUTHOR}" target="_blank" rel="noopener noreferrer"><img class="author-photo" src="{asset}people/author.webp" alt="{esc(c['authors']['alt'])}" srcset="{asset}people/author-360.webp 360w, {asset}people/author.webp 600w" sizes="160px" width="600" height="592" loading="lazy" decoding="async"></a><div class="author-details"><h3>Nicolas Loffredo</h3><p>{esc(c['authors']['bio'])}</p>{external(AUTHOR, c['authors']['link'])}</div></article></div></section></main>'''
    elif route == '/about/':
        approach = ''.join(f'<article class="approach-item"><span class="item-number">0{i+1}</span><h3>{esc(title)}</h3><p>{esc(text)}</p></article>' for i, (title, text) in enumerate(c['approach']))
        facts = ''.join(f'<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>' for label, value in c['facts'])
        facts += f'<div><dt>{esc(c["corporateNumberLabel"])}</dt><dd><bdi dir="ltr">{CORPORATE_NUMBER}</bdi><br>{external(CORPORATE_REGISTRY, c["corporateNumberLink"])}</dd></div>'
        body = f'''<main id="main"><section class="page-intro"><div class="container narrow"><p class="eyebrow">{esc(c['aboutLabel'])}</p><h1>{esc(c['aboutTitle'])}</h1><p class="lead">{esc(c['aboutLead'])}</p><p>{esc(c['aboutBody'])}</p></div></section><section class="approach-section"><div class="container"><h2>{esc(c['approachTitle'])}</h2><div class="approach-grid">{approach}</div><dl class="company-facts">{facts}</dl></div></section></main>'''
    elif route == '/contact/':
        body = f'''<main id="main" class="contact-main"><section class="contact-section"><div class="container narrow"><p class="eyebrow">{esc(c['contactLabel'])}</p><h1>{esc(c['contactTitle'])}</h1><p class="lead">{esc(c['contactText'])}</p><div class="contact-address"><p>{esc(c['emailAction'])}</p><a href="mailto:{EMAIL}" dir="ltr">{EMAIL}<span aria-hidden="true">↗</span></a></div></div></section></main>'''
    elif route == '/team/':
        team = c['team']
        cards = ''
        for i, (key, member) in enumerate(zip(('ceo', 'web', 'android', 'apple', 'marketing', 'sourcing'), team['members'])):
            badge = f'<span class="team-badge">{esc(team["newcomer"])}</span>' if key == 'apple' else ''
            heading = member['name']
            role = f'<p class="team-role">{esc(member["role"])}</p>'
            cards += f'''<article class="team-card" data-team-role="{key}"><div class="team-portrait"><img src="{versioned(f'people/{key}.webp')}" srcset="{versioned(f'people/{key}-360.webp')} 360w, {versioned(f'people/{key}.webp')} 720w" sizes="(max-width: 550px) calc(100vw - 40px), (max-width: 900px) 45vw, 380px" alt="{esc(member['alt'])}" width="720" height="900" loading="{'eager' if i == 0 else 'lazy'}" decoding="async">{badge}</div><div class="team-info"><h2>{esc(heading)}</h2>{role}<p class="team-bio">{esc(member['bio'])}</p><p class="team-motto"><span>{esc(team['mottoLabel'])}</span>{esc(member['motto'])}</p></div></article>'''
        honorary = team['honorary']
        honorary_card = f'''<section class="container honorary-section" aria-labelledby="honorary-heading"><article class="team-card honorary-card" data-team-role="honorary"><div class="team-portrait"><img src="{versioned('people/honorary.webp')}" srcset="{versioned('people/honorary-360.webp')} 360w, {versioned('people/honorary.webp')} 720w" sizes="(max-width: 700px) calc(100vw - 40px), 360px" alt="{esc(honorary['alt'])}" width="720" height="900" loading="lazy" decoding="async"></div><div class="team-info"><p class="eyebrow">{esc(team['honoraryLabel'])}</p><h2 id="honorary-heading">{esc(honorary['name'])}</h2><p class="team-role">{esc(honorary['role'])}</p><p class="team-bio">{esc(honorary['bio'])}</p><p class="team-motto"><span>{esc(team['mottoLabel'])}</span>{esc(honorary['motto'])}</p></div></article></section>'''
        body = f'''<main id="main"><section class="team-hero container"><p class="eyebrow">Nihon Essentials Hub</p><h1>{esc(team['title'])}</h1><p class="lead">{esc(team['subtitle'])}</p><p class="team-tagline">{esc(team['tagline'])}</p></section><div class="container team-grid">{cards}</div>{honorary_card}</main>'''
    elif route == '/cookie-policy/':
        cookies = c['cookies']
        paragraphs = ''.join(f'<section><h2>{esc(title)}</h2><p>{esc(text)}</p></section>' for title, text in cookies['sections'])
        paragraphs += f'<p>{external("https://policies.google.com/privacy", cookies["analyticsPrivacyLink"])}</p>'
        body = f'''<main id="main"><article class="container narrow privacy-content"><p class="eyebrow">Nihon Essentials Hub</p><h1>{esc(cookies['title'])}</h1><p class="lead">{esc(cookies['intro'])}</p>{paragraphs}<button type="button" class="preference-button" data-cookie-manage>{esc(cookies['manage'])}</button> <a class="text-link" href="{esc(link('/contact/'))}">{esc(c['contactLabel'])} →</a></article></main>'''
    else:
        paragraphs = ''.join(f'<section><h2>{esc(title)}</h2><p>{esc(text)}</p></section>' for title, text in c['privacyContent'])
        body = f'''<main id="main"><article class="container narrow privacy-content"><p class="eyebrow">Nihon Essentials Hub</p><h1>{esc(c['privacyTitle'])}</h1>{paragraphs}<p><a class="text-link" href="{esc(link('/cookie-policy/'))}">{esc(c['cookies']['policyLink'])}</a></p><a class="text-link" href="{esc(link('/contact/'))}">{esc(c['contactLabel'])} →</a></article></main>'''
    organization = {'@type': 'Organization', '@id': SITE + '/#organization', 'name': 'Nihon Essentials Hub', 'legalName': 'Nihon Essentials Hub G.K.', 'alternateName': 'Nihon Essentials Hub 合同会社', 'url': SITE + '/', 'description': c['description'], 'identifier': {'@type': 'PropertyValue', 'propertyID': 'JP Corporate Number', 'value': CORPORATE_NUMBER}, 'sameAs': [CORPORATE_REGISTRY]}
    if route == '/contact/':
        organization['email'] = EMAIL
    website = {'@type': 'WebSite', '@id': SITE + '/#website', 'url': SITE + '/', 'name': 'Nihon Essentials Hub', 'publisher': {'@id': SITE + '/#organization'}, 'inLanguage': [item['tag'] for item in LOCALES]}
    page_type = 'AboutPage' if route == '/about/' else 'ContactPage' if route == '/contact/' else 'WebPage'
    page = {'@type': page_type, '@id': absolute(lang, route) + '#webpage', 'url': absolute(lang, route), 'name': titles[route] + ' | Nihon Essentials Hub', 'description': page_description, 'inLanguage': meta['tag'], 'isPartOf': {'@id': SITE + '/#website'}, 'about': {'@id': SITE + '/#organization'}}
    graph = [organization, website, page]
    if route == '/':
        graph.append({'@type': 'Person', '@id': SITE + '/#author', 'name': 'Nicolas Loffredo', 'url': AUTHOR, 'image': SITE + '/assets/people/author.webp', 'description': c['authors']['bio']})
    schema = '<script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False) + '</script>'
    cookies = c['cookies']
    consent = f'''<section id="cookie-banner" class="cookie-banner" hidden role="region" aria-labelledby="cookie-banner-title"><div class="container cookie-layout"><div><h2 id="cookie-banner-title">{esc(cookies['title'])}</h2><p>{esc(cookies['intro'])} <a href="{esc(link('/cookie-policy/'))}">{esc(cookies['policyLink'])}</a></p></div><div class="cookie-actions"><button type="button" data-cookie-accept>{esc(cookies['accept'])}</button><button type="button" data-cookie-reject>{esc(cookies['reject'])}</button><button type="button" data-cookie-manage>{esc(cookies['manage'])}</button></div></div></section>
<dialog id="cookie-dialog" aria-labelledby="cookie-dialog-title" aria-describedby="cookie-dialog-intro"><div class="cookie-dialog-inner"><h2 id="cookie-dialog-title">{esc(cookies['manage'])}</h2><p id="cookie-dialog-intro">{esc(cookies['intro'])}</p><div class="cookie-option"><h3>{esc(cookies['essential'])}</h3><p>{esc(cookies['essentialDescription'])}</p></div><div class="cookie-option"><label for="cookie-preferences"><input type="checkbox" id="cookie-preferences"> {esc(cookies['optional'])}</label><p>{esc(cookies['optionalDescription'])}</p></div><div class="cookie-option"><label for="cookie-analytics"><input type="checkbox" id="cookie-analytics" aria-describedby="cookie-analytics-description"> {esc(cookies['analytics'])}</label><p id="cookie-analytics-description">{esc(cookies['analyticsDescription'])}</p></div><div class="cookie-actions"><button type="button" data-cookie-save>{esc(cookies['save'])}</button><button type="button" data-cookie-reject>{esc(cookies['reject'])}</button><button type="button" data-cookie-close>{esc(cookies['close'])}</button></div><a href="{esc(link('/cookie-policy/'))}">{esc(cookies['policyLink'])}</a></div></dialog>'''
    footer = f'''<footer class="site-footer"><div class="container footer-inner"><p>© 2026 Nihon Essentials Hub G.K.</p><nav aria-label="{esc(c['menu'])}"><a href="{esc(link('/about/'))}">{esc(c['nav'][2])}</a><a href="{esc(link('/contact/'))}">{esc(c['nav'][3])}</a><a href="{esc(link('/privacy/'))}">{esc(c['privacy'])}</a><a href="{esc(link('/cookie-policy/'))}">{esc(cookies['label'])}</a><button type="button" data-cookie-manage>{esc(cookies['manage'])}</button></nav></div></footer>{consent}{schema}</body></html>'''
    if route == '/':
        # All three collections live directly below the three activities.
        carousel_html = render_carousels(CATALOG, CATALOG_LABELS[lang], lang, base, AUTHOR, locale_meta=LOCALES)
        body = body.replace('<section class="brands-section"', carousel_html + '\n<section class="brands-section"', 1)
        head = head.replace('</head>', f'<link rel="stylesheet" href="{versioned("carousels.css")}"><script defer src="{versioned("carousels.js")}"></script></head>')
    return head + body + footer


for language in CONTENT:
    for page_route in ROUTES:
        output = ROOT / prefix(language) / page_route.lstrip('/')
        output.mkdir(parents=True, exist_ok=True)
        (output / 'index.html').write_text(build_page(language, page_route), encoding='utf-8')
urls = [absolute(language, route) for language in CONTENT for route in ROUTES]
(ROOT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{url}</loc></url>' for url in urls) + '</urlset>')
(ROOT / '404.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex"><title>Page not found | Nihon Essentials Hub</title>''' + favicon_links('/') + '''<style>body{margin:12vh 8vw;font:18px/1.6 Arial,sans-serif;color:#152b3a;background:#f7f9fa}h1{font-size:48px;line-height:1.1}a{color:inherit}</style><h1>Page not found.</h1><p>Cette page est introuvable。ページが見つかりませんでした。</p><a href="https://nihonessentialshub.com/">Nihon Essentials Hub →</a></html>''')
print(f'Generated {len(CONTENT)} languages × {len(ROUTES)} pages.')
