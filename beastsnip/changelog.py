"""Parse the canonical, version-separated Markdown history without Qt."""
import re


def parse_changelog(markdown):
    releases, release, section = [], None, None
    for raw in markdown.splitlines():
        line = raw.strip()
        match = re.fullmatch(r'## (\d+\.\d+\.\d+) [—–-] (.+)', line)
        if match:
            release = dict(version=match[1], date=match[2], sections=[])
            releases.append(release); section = None
        elif release is not None and line.startswith('### '):
            section = dict(title=line[4:].strip(), items=[])
            release['sections'].append(section)
        elif release is not None and line.startswith('- '):
            if section is None:
                section = dict(title='Changes', items=[]); release['sections'].append(section)
            section['items'].append(line[2:])
    if not releases or len({r['version'] for r in releases}) != len(releases):
        raise ValueError('The changelog must have unique version headings.')
    return releases
