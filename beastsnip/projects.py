"""Versioned editable projects and an ordered private recovery journal."""
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import struct
import zipfile

from PySide6.QtCore import QObject, QPointF, QTimer, Signal
from PySide6.QtGui import QColor, QImage

from .config import atomic_bytes
from .document import Annotation, Document, encode_image

MAX_BYTES = 256 * 1024 * 1024
MAX_PIXELS = 60_000_000
KINDS = {'pen', 'brush', 'highlight', 'line', 'arrow', 'rect', 'round_rect', 'filled', 'ellipse', 'text', 'number', 'redact'}


def project_snapshot(doc, png_path=''):
    def copy_states(states):
        return [(QImage(image), deepcopy(annotations), revision, text)
                for image, annotations, revision, text in states[-10:]]
    return {'current': doc.snapshot(), 'undo': copy_states(doc.undo_stack),
            'redo': copy_states(doc.redo_stack), 'next_revision': doc._next_revision,
            'png_path': str(png_path or '')}


def annotation_data(item):
    return dict(kind=item.kind, points=[[p.x(), p.y()] for p in item.points], color=item.color,
                width=item.width, text=item.text, font_size=item.font_size, number=item.number,
                offset=[item.offset.x(), item.offset.y()], opacity=item.opacity,
                line_style=item.line_style, cap=item.cap, fill_style=item.fill_style,
                arrow_heads=item.arrow_heads, smooth=item.smooth)


def encode_project(snapshot):
    stream, images = io.BytesIO(), {}
    total_pixels, total_bytes = 0, 0
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        def state_data(state):
            nonlocal total_pixels, total_bytes
            image, annotations, revision, text = state
            if len(text) > 2_000_000 or len(annotations) > 10000 or any(len(a.text) > 200000 or len(a.points) > 200000 for a in annotations):
                raise ValueError('The project contains too much editable text or annotation data. Export a flattened PNG instead.')
            key = image.cacheKey()
            if key not in images:
                pixels = image.width() * image.height()
                total_pixels += pixels
                if pixels > MAX_PIXELS or total_pixels > MAX_PIXELS * 2:
                    raise ValueError('The project contains too many image pixels. Export a flattened PNG instead.')
                name = f'images/{len(images)}.png'
                encoded = encode_image(image)
                total_bytes += len(encoded)
                if total_bytes > MAX_BYTES - 8 * 1024 * 1024:
                    raise ValueError('The project images exceed the supported size.')
                archive.writestr(name, encoded)
                images[key] = name
            return dict(image=images[key], annotations=[annotation_data(a) for a in annotations],
                        revision=revision, ocr=text)
        manifest = {'format': 'BeastSnip project', 'schema': 2,
                    'current': state_data(snapshot['current']),
                    'undo': [state_data(s) for s in snapshot['undo']],
                    'redo': [state_data(s) for s in snapshot['redo']],
                    'next_revision': snapshot['next_revision'], 'png_path': snapshot['png_path']}
        description = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
        # Keep a readable project even when repeated OCR/pen history is large.
        # Recent history is optional; the current editable state is retained.
        while len(description) > 8 * 1024 * 1024 and (manifest['undo'] or manifest['redo']):
            states = manifest['undo'] if len(manifest['undo']) >= len(manifest['redo']) else manifest['redo']
            states.pop(0)
            description = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
        if len(description) > 8 * 1024 * 1024:
            raise ValueError('The editable description is too large. Export a flattened PNG instead.')
        archive.writestr('project.json', description)
    result = stream.getvalue()
    if len(result) > MAX_BYTES:
        raise ValueError('The editable project is too large to save. Export a flattened PNG instead.')
    return result


def save_project(path, snapshot):
    atomic_bytes(path, encode_project(snapshot))


def load_project(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('This project exceeds the supported size.')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or len(names) > 23 or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError('The project has invalid or oversized contents.')
        if any(name != 'project.json' and not (name.startswith('images/') and name[7:-4].isdigit() and name.endswith('.png')) for name in names):
            raise ValueError('The project contains unsupported files.')
        if archive.getinfo('project.json').file_size > 8 * 1024 * 1024:
            raise ValueError('The project description is too large.')
        manifest = json.loads(archive.read('project.json'))
        if manifest.get('format') != 'BeastSnip project' or manifest.get('schema') not in (1, 2):
            raise ValueError('This project format is not supported.')
        images, total_pixels = {}, 0
        def point(values):
            if len(values) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) and abs(v) <= 1e7 for v in values):
                raise ValueError('The project contains an invalid annotation coordinate.')
            return QPointF(*values)
        def read_state(state):
            nonlocal total_pixels
            name = state['image']
            if name not in images:
                raw = archive.read(name)
                if len(raw) < 24 or raw[:8] != b'\x89PNG\r\n\x1a\n':
                    raise ValueError('A project image is not a PNG.')
                width, height = struct.unpack('>II', raw[16:24])
                total_pixels += width * height
                if not width or not height or width * height > MAX_PIXELS or total_pixels > MAX_PIXELS * 2:
                    raise ValueError('A project image exceeds the supported dimensions.')
                image = QImage.fromData(raw, 'PNG')
                if image.isNull():
                    raise ValueError('A project image could not be read.')
                images[name] = image
            annotations = []
            if len(state['annotations']) > 10000:
                raise ValueError('The project has too many annotations.')
            for item in state['annotations']:
                if item['kind'] not in KINDS or not 1 <= len(item['points']) <= 200000:
                    raise ValueError('The project contains an unsupported annotation.')
                if type(item['width']) is not int or type(item['font_size']) is not int or not 1 <= item['width'] <= 80 or not 8 <= item['font_size'] <= 160 or len(item['text']) > 200000:
                    raise ValueError('The project contains invalid annotation settings.')
                if not isinstance(item['text'], str) or not isinstance(item['color'], str) or not QColor(item['color']).isValid() or not isinstance(item['number'], int) or not 1 <= item['number'] <= 1_000_000_000:
                    raise ValueError('The project contains invalid annotation text, colour or numbering.')
                styles = {key: item.get(key, default) for key, default in dict(opacity=100, line_style='solid', cap='round', fill_style='none', arrow_heads='end', smooth=False).items()}
                if type(styles['opacity']) is not int or not 5 <= styles['opacity'] <= 100 or type(styles['smooth']) is not bool:
                    raise ValueError('The project contains invalid drawing opacity or smoothing.')
                for key, choices in [('line_style', ('solid', 'dash', 'dot')), ('cap', ('round', 'square')), ('fill_style', ('none', 'solid', 'soft')), ('arrow_heads', ('end', 'both', 'none'))]:
                    if styles[key] not in choices:
                        raise ValueError('The project contains an unsupported drawing style.')
                annotations.append(Annotation(item['kind'], [point(p) for p in item['points']],
                    item['color'], item['width'], item['text'], item['font_size'], item['number'], point(item['offset']), **styles))
            if not isinstance(state['ocr'], str) or len(state['ocr']) > 2_000_000 or not isinstance(state['revision'], int) or state['revision'] < 0:
                raise ValueError('The project contains invalid text or revision data.')
            return QImage(images[name]), annotations, state['revision'], state['ocr']
        current = read_state(manifest['current'])
        if len(manifest['undo']) > 10 or len(manifest['redo']) > 10:
            raise ValueError('The project has too many saved editing states.')
        undo = [read_state(s) for s in manifest['undo']]
        redo = [read_state(s) for s in manifest['redo']]
        doc = Document(current[0])
        doc.annotations, doc.revision, doc.ocr_text = current[1:]
        doc.undo_stack, doc.redo_stack = undo, redo
        next_revision = manifest.get('next_revision', doc.revision)
        if not isinstance(next_revision, int) or next_revision < 0:
            raise ValueError('The project revision data is invalid.')
        doc._next_revision = max([doc.revision, next_revision] + [s[2] for s in undo + redo])
        doc.saved_revision, doc.saved_ocr_text = doc.revision, doc.ocr_text
        # The path is a hint only. Callers must never trust a project to choose
        # an arbitrary file to overwrite; explicit projects open without it.
        return doc, str(manifest.get('png_path', ''))


class RecoveryJournal(QObject):
    state_changed = Signal()

    def __init__(self, path, submit, enabled=True, parent=None):
        super().__init__(parent)
        self.path, self.submit, self.enabled = Path(path), submit, enabled
        self.doc, self.png_path = None, ''
        self.busy, self.pending, self.error = False, False, ''
        self.generation = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(600)
        self.timer.timeout.connect(self.flush)

    def attach(self, doc, png_path=''):
        if self.doc:
            self.doc.changed.disconnect(self.schedule)
        self.doc, self.png_path = doc, str(png_path or '')
        self.doc.changed.connect(self.schedule)
        self.schedule()

    def schedule(self):
        if self.enabled and self.doc:
            self.generation += 1
            self.pending, self.error = True, ''
            self.timer.start()

    def flush(self):
        self.timer.stop()
        if not self.enabled or not self.doc or self.busy or not self.pending:
            return
        snapshot, generation = project_snapshot(self.doc, self.png_path), self.generation
        self.busy, self.pending, self.error = True, False, ''
        self.state_changed.emit()
        def completed(result, error):
            self.busy, self.error = False, error
            self.pending = bool(error) or self.generation != generation
            self.state_changed.emit()
            if self.pending and not error:
                self.flush()
        self.submit(lambda: save_project(self.path, snapshot), completed)

    def clear(self):
        if self.busy:
            raise RuntimeError('Wait for recovery saving to finish, then clear it.')
        self.timer.stop()
        self.pending, self.error = False, ''
        self.path.unlink(missing_ok=True)
