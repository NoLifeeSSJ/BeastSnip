# Verification record

Updated to 1.0.3 on 21 October 2026 in Linux with Python 3.12.14 and PySide6 6.10.2. The user confirmed that OCR works on Windows 1.0.2 and reported a cramped result box. Version 1.0.3 replaces that box with a resizable sidebar and expanded reader. Native Windows integration checks remain separate from the automated UI layout checks below.

## Checks actually performed

- Python compilation and imports: passed.
- `pip check`: passed; no broken dependencies.
- Real Qt UI offscreen startup: passed; window/editor construction, annotation, crop, undo/redo, pixel dimensions, event loop and clean exit exercised.
- **46 automated tests executed, 46 passed, 0 failures, 0 skipped** in the development environment:
  - All annotation tools render real pixels.
  - Opaque redaction across every pixel inside a rectangle; reverse-direction drawing.
  - PNG flattening strips source text metadata; original pixels remain only in the in-memory editable model.
  - JPEG transparency becomes a white background; nested atomic output creation.
  - Crop bounds, undo/redo, editable-object restoration, object move/delete and branched undo dirty state.
  - Crop through real Qt mouse events after zoom uses image coordinates.
  - Negative desktop coordinates and 150% overlay mapping (simulated monitor geometry).
  - Reverse capture drag selects expected frozen-image dimensions; cancel closes overlays and produces no capture (mocked native capture).
  - History persistence across reopen, title/tags/OCR search and rename.
  - Updating one history item replaces flattened pixels, thumbnail and OCR and removes its previous materialised PNG.
  - Concurrent history materialisation/update cannot retain an old unredacted convenience PNG.
  - Missing convenience PNG recovery; deletion preserves separate exports; clear history.
  - History save via the UI's worker and queued completion.
  - Shortcut grammar and missing OCR messages.
  - Actual **Tesseract 5.5.0** OCR on a generated text image; a fully redacted image produces no recovered text.
  - Reported `NE160QDM-NM9` friendly name maps to its native capture ID at 150% DPI; duplicate friendly names, reversed display enumeration and negative origins remain accurate.
  - The monitor selector stores GDI IDs independently of labels; full-monitor capture and region overlays use the corrected mapping.
  - OCR discovery in per-user Programs and registry/custom paths; explicit language folders override a broken environment prefix.
  - Missing-language detection happens before an image is submitted; failed English checksums preserve existing files.
  - OCR repair preserves unrelated/unknown settings and makes a backup; failed recognition does not overwrite settings.
- Actual OCR repair ran against the local Tesseract runtime. A fresh app-managed English language file was downloaded from pinned official commit `87416418657359cb625c412a48b6e1d6d41c29bd`, verified against SHA256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`, and passed real recognition and opaque-image checks.
- Eight new OCR UI tests passed at normal scale and again with `QT_SCALE_FACTOR=1.5`: full-height layout, a 900 × 600 laptop window, long-path wrapping, chosen panel width, text copy/edit/undo, synchronised expanded-view edits and reading controls, independent wrapping when returning from the expanded view, modal reader behaviour, and clearing stale text after redaction/new images.
- A sample helpdesk image was recognised by real local Tesseract and displayed in the new sidebar and expanded reader for visual inspection. No user screenshot was used for the generated previews.
- Original SVG rendered to a 7-size Windows ICO (16–256 px) and PNG: passed.
- Real home/editor screenshots rendered and visually inspected for layout, toolbar and redaction.
- PowerShell scripts parsed with official PowerShell 7.5.4 on Linux: passed. Its downloaded runtime archive was checked against the publisher's SHA256 manifest before use. This checks syntax, not Windows PowerShell 5.1 runtime behaviour or COM/winget.
- Standalone installer executed through its real SHA256 check, ZIP extraction, parameter forwarding and temporary-file cleanup in PowerShell: passed. Only the extracted Windows installation step was stubbed for this Linux check; COM shortcuts, Python installation and winget were not executed.
- Updated setup and updater wrappers passed extraction, required OCR forwarding, failure propagation and cleanup checks. OCR PowerShell installation/reinstallation/failure branches passed with native executables and winget stubbed. These are script control-flow checks, not a claim that winget or Windows capture ran here.
- **33 PowerShell assertions passed** for process classification, update control flow and cache cleanup: default refusal without opt-in, closure of only the target install, unrelated Python/other installs preserved, paths with spaces/apostrophes, repeatability, PID reuse, denied termination, a process still running after the close attempt and deleting only generated package bytecode. Win32 process operations were mocked; cache files were checked on disk. The tests are included in `tests/test_updater.ps1` and run by the installer.
- A stale import was reproduced using equal-length version source with a fixed ZIP timestamp: Python continued importing `1.0.1` after the source became `1.0.2`. Running the shipped PowerShell cleanup made a fresh Python process import `1.0.2`. The probe path contained a space and apostrophe.
- Real local OCR repair was run twice: recognition/redaction checks passed both times, unrelated/unknown settings were preserved, distinct settings backups were created, and no history directory or screenshot file was created.
- Source ZIP files passed ZIP CRC and path checks; its bytes match the embedded payload and delivery SHA256 checksums. Tests and UI startup also passed when run from the extracted payload.

## Checks still required on a Windows 11 laptop

These have **not** been executed in Linux. No Windows integration result is claimed.

1. Run the standalone setup command in a regular Windows PowerShell 5.1 window. Verify Python detection/install, venv creation, dependencies, startup check, desktop shortcut target and icon. Also test a redirected/OneDrive desktop, paths containing spaces and rerunning setup.
2. Launch → capture a region → annotate → redact → crop → undo/redo → copy → save → Save to History → reopen history → pin → quit. Verify clipboard pixels and both PNG/JPEG exports in another application.
3. Capture a selected monitor and a previously active external window; verify the documented visible-pixel behaviour and cancellation by Escape/right-click.
4. Region capture on one display, then monitors placed left/above the primary, with 100%, 125%, 150% and 200% scaling; drag across boundaries and in reverse directions. Compare selection dimensions and exported pixel positions. Confirm BeastSnip and its overlay/pins never appear in captures. Simulated geometry tests do not replace this check.
5. Check delays 0/3/5/10, monitor disconnect/reconnect, default/custom global shortcuts, conflict feedback and two launches restoring the existing instance. Check foreground targeting after taskbar/tray use.
6. Pin drag, resize/aspect ratio, opacity and close while the main window is minimised. Check tray close explanation, configurable quit-on-close, unsaved-edit warning and clean hotkey/tray cleanup on quit.
7. Verify the 1.0.3 sidebar/divider and expanded reader on Windows at the laptop's actual DPI setting. Check text editing/copying and resize/maximise. OCR full-image/area on Windows with and without Tesseract and with a missing language. Redact sensitive text before extracting; verify OCR never receives the original. While OCR runs, edit the image and confirm stale output is discarded.
8. Force unavailable clipboard, unwritable save/history folders, deleted materialised images and a cancelled file dialog. Confirm readable messages and preserved previous data.
9. Build with Build.ps1; it should run its packaged startup check. Then test the entire `dist\BeastSnip` directory on a Windows account without Python. A Windows executable has not been built in this Linux environment.

Installation requires package-download access. Normal app use and OCR are local. Optional OCR installation may need a publisher-installer UAC approval. Per-user app operation does not require administrator rights.
