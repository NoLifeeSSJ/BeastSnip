# Changelog

## 2.1.0 — 22 October 2026

- Added Quick Capture: save several snips without replacing the current editor session, with a small non-activating Open / Copy / Pin preview and retry for failed saves.
- Added editable .beastsnip projects and automatic private session recovery, including original pixels, annotations, extracted text and up to ten undo and ten redo states. Recovery can be disabled and cleared in Preferences.
- Added an Update Centre with explicit release checks, readable release notes, SHA256-verified updater downloads, installation progress and update-log access.
- Rebuilt installation around a separately tested candidate and Python runtime. Failed activation checks restore the previous application, runtime selection, settings and desktop shortcut; an interrupted activation is repaired on the next update attempt.
- Added Screenshots favourites, date filters, multi-select, rename, bulk PNG export, reversible deletion and Load More for larger libraries. Saved History and all existing tools remain available.
- Added a frozen-pixel magnifier beside the selection cursor, with physical coordinates and an M toggle.
- Added vertical scrolling capture with automatic scrolling, manual Add Frame, overlap validation, pause, Finish and Cancel. Uncertain alignment stops automatic scrolling and preserves the valid captured portion.
- Refined the compact capture header, library selection controls, recovery/save notices, action search and scrollable Preferences while preserving the readable OCR sidebar and expanded reader.
- Shipped the complete update as one self-contained PowerShell script, including dependencies, OCR repair, tests, rollback handling, icon and desktop-shortcut refresh. Existing screenshot folders, OCR preferences and history are retained.

## 2.0.1 — 21 October 2026

- Fixed an installer self-test that rejected a readable 396-pixel OCR text viewport on Windows because it assumed a 400-pixel minimum from the cloud environment.
- Replaced fixed sidebar viewport pixel thresholds with readable-line, usable-width and proportional-space checks based on the actual font metrics and layout.
- Added a regression test that accepts the reported 396-pixel viewport and rejects the old squashed 140-pixel presentation.
- Captured the deliberately triggered autosave failure log inside its test, so expected failure/retry coverage does not print a misleading error during a successful install.
- Shipped a versioned 2.0.1 updater that runs the full required checks and can finish an installation stopped by 2.0.0. The 2.0 workspace, OCR, autosave, history and existing preferences are retained.

## 2.0.0 — 21 October 2026

- Redesigned the native workspace around a compact header, a grouped icon tool rail, contextual editing controls, and focused copy/save actions. All twelve annotation/navigation tools remain available.
- Integrated the BeastSnip icon and wordmark into an app navigation menu, with Library / Editor navigation that keeps the current session intact.
- Grouped region, active-window, monitor and delayed capture in the New Snip split button. Tray capture and the global shortcut are retained.
- Added automatic PNG saving for new captures and pasted images in `C:\SnipsV1\Screenshots`. The existing installation remains at `C:\SnipV1`.
- Edits, crops, redactions, undo and redo update the same PNG with debounced, atomic, serial background writes. Older writes cannot finish after a newer edit and replace it. Save completion does not interrupt drawing.
- Added a persistent save status, failure banner and retry action. Failed saves keep the session unsaved. PNG auto-save does not store OCR text; Saved History still stores text explicitly.
- Added a Screenshots library with background thumbnail loading, filename search, open/copy actions, folder access and refresh, alongside the existing searchable Saved History.
- Added paste from clipboard, quick save, an action search (Ctrl+K), tool shortcuts, a keyboard guide (F1), and Focus mode (Ctrl+Shift+F).
- Grouped Preferences into Captures & storage, Workspace, and Offline OCR. Added auto-save controls and folder selection; preserved existing settings, languages, history, and the working OCR engine.
- Kept the resizable OCR sidebar, expanded reader, text size and wrapping controls. The helper text adapts to short windows.
- Added a one-time, backed-up settings migration with a real folder write check. Later custom folder choices and an explicit auto-save-off preference survive subsequent updates.
- Shipped a self-contained 2.0.0 PowerShell updater, matching source ZIP, checksums, tests, and reproducible UI previews.

## 1.0.3 — 21 October 2026

- OCR results open in a full-height sidebar instead of a shallow box below the image.
- Drag the purple divider to resize the text area; its width is kept when extracting again or reopening the panel in the same session.
- Expand Text opens a large, resizable, maximisable reader. Edits and reading controls stay in sync with the sidebar.
- Adjust text size from 10 to 24 pt and enable/disable line wrapping. Long paths wrap without clipping by default.
- Copy Text and keyboard editing work in both views. Redacting or changing the image clears stale OCR from both views.
- The PowerShell updater installs 1.0.3 while preserving history, preferences and the existing working OCR runtime.

## 1.0.2 — 21 October 2026

- Added explicit targeted app closure, visible update stages, transcript logs and installed-version verification.
- Cleared stale generated bytecode to ensure updated source loads.

## 1.0.1 — 21 October 2026

- Fixed friendly monitor names being compared with native Windows display IDs.
- Added OCR runtime discovery, language setup and local recognition checks.

## 1.0.0 — 21 October 2026

- Initial screenshot application, annotation editor, local history, offline OCR, pinning, tray integration and Windows setup scripts.
