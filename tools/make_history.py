"""Generate the bundled offline version history from the canonical Markdown."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beastsnip import __version__
from beastsnip.changelog import parse_changelog


def build_history():
    releases = parse_changelog((ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'))
    if releases[0]['version'] != __version__:
        raise ValueError('The first changelog release must be the current version.')
    path = ROOT / 'beastsnip/resources/changelog.json'
    path.write_text(json.dumps({'schema': 1, 'releases': releases}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return releases


if __name__ == '__main__':
    print(f'Bundled {len(build_history())} releases from CHANGELOG.md.')
