# BeastSnip 2.1.2 verification

24 October 2026. Linux development host, Python 3.12.14, PySide6 6.10.2, Tesseract 5.5.0 and official PowerShell 7.5.4. Native Windows taskbar/Shell appearance, input, capture and PowerShell 5.1 execution still require the Windows checks below.

## Multi-monitor installation repair

- Reproduced both reported 2.1.1 failures before the fix by running the drag-selection and cancellation tests with a simulated additional `LEN G25-10` at `(2560, 0, 1920, 1080)`, scale 1. Both raised the exact reported mapping error.
- The cause was inconsistent test data: a synthetic single-monitor Windows inventory was paired with the installer's actual Qt screen inventory. The fixture now supplies both inventories together while retaining a real QScreen for the actual overlay widget. An unused virtual-desktop mock was removed.
- All four capture-coordinate tests pass with the same simulated additional screen. A permanent regression keeps this extra screen outside the synthetic session. Another exercises both region overlays and the full frozen-pixel bounds for the reported secondary-screen layout with reversed native enumeration.
- Production monitor matching was not weakened. Existing duplicate-name, mixed-DPI, negative-origin and ambiguous-match rejection tests remain enabled. No self-tests are skipped to permit installation; the separate native Windows monitor/capture validation still runs before activation.

## Application and UI

- **102 Python tests passed from the extracted delivery payload**, with no failures or skips in the development environment. These use actual Qt widgets, mouse/keyboard events, background workers, generated pixels, PNG/project files, SQLite and local OCR. Native Windows calls are substituted where necessary.
- All previous capture geometry, annotation, opaque redaction, crop/undo, clipboard/export, history, OCR, readable OCR sidebar, autosave/retry, migration, Quick Capture, recovery, library, scrolling and Update Centre coverage remains enabled.
- New tools draw actual editable Brush, Line and Rounded Box annotations. Shift constraints, separate tool defaults, persisted preferences and new shortcuts are exercised.
- Real flattened pixels distinguish dashed from solid lines, soft shape fills from solid fills, smoothing from angular freehand, and 50% opacity from opaque output. A redaction with drawing opacity set to 5% remains black at every interior pixel.
- The real colour palette and style popover change a selected annotation without losing selection. Changes are undoable and update the same auto-saved PNG.
- An eraser drag removes several annotations in one undo step. A test allows an intermediate PNG write before the next deletion and verifies the final PNG still contains the latest state. Original image pixels remain intact; undo/redo restores/removes annotations.
- Styled projects preserve all new properties, rendered pixels and undo/redo. A fixture created by the actual published 2.1.0 encoder verifies format-1 loading with legacy opacity/smoothing. New saves use format 2; old apps reject it instead of silently losing styles.
- Version History contains all nine releases, newest first, with separate dates and sections. Search, current-version selection, All Releases, Copy Notes and no-results behaviour are exercised with real widgets. The selected current release includes the monitor-installation repair. The bundled JSON is generated from CHANGELOG.md.
- The corrected gear is rendered and its pixel bounds checked for horizontal/vertical centring. The width field is checked against font metrics and usable text width, including the complete `px` unit.
- The 2.1.1 baseline included 26 drawing/workspace/OCR UI tests with Qt's Windows style at 150% scale and the eight drawing/history tests at 200%. The style panel stays within the available screen height and scrolls as needed; 900 × 600 header/footer/context actions remain inside the window. This repair changes no drawing or layout code.
- Existing 2.1.1 drawing, colour, style, laptop and version-history previews use generated sample pixels and isolated storage. No private desktop screenshot is used; those historical previews are retained unchanged.
- Startup smoke tests construct the real UI, exercise editing/crop/undo and load the application/window icon. On Windows, smoke startup fails if assigning BeastSnip's explicit application ID fails.

## Taskbar and update checks

- Python sets `NoLifeeSSJ.BeastSnip.Desktop` before QApplication or windows are created. The application-wide ICO is set before constructing dialogs/windows. An isolated native-boundary test checks the ID argument and HRESULT failure handling; this does not prove physical taskbar rendering.
- The updater writes matching application ID, relaunch command/name/icon properties into the desktop shortcut through Windows IPropertyStore, commits, reads back the ID and notifies the Shell about that shortcut. It does not restart Explorer or delete icon caches.
- The actual C# interop compiles under PowerShell 7.5.4. Four checks verify shared application identity and the managed PROPERTYKEY/64-bit PROPVARIANT layouts. Native Shell calls cannot execute on Linux.
- 36 existing updater assertions and 42 real-file transaction assertions remain enabled. They cover process identity, targeted closure, legacy/versioned runtimes, bytecode cleanup, staged activation, repeated rollback, interrupted activation, settings bytes, path validation and preserving user files.
- The actual Install.ps1 pipeline passed **97 assertions** in a temporary filesystem fixture. Failure injection covers dependencies, self-tests, OCR, native capture validation, folder configuration, version verification, startup, shortcut creation and shortcut taskbar-property creation. Failed runs retain or restore the old package/settings/runtime/shortcut, preserve user PNGs and private recovery, and never print completion. Success installs the new runtime pointer. Python/native/COM/Shell operations are substituted; filesystem operations are real.
- The candidate's shell interop compilation/layout check runs before live activation. Shortcut/Shell property failure after activation invokes the same automatic rollback as other final-check failures.
- PowerShell syntax, standalone wrapper hash/extraction/argument forwarding/error cleanup, source ZIP CRC/path/source agreement, embedded payloads, manifest and SHA256 checksums are verified for the published package. Versioned historical updater downloads are retained unchanged.

## Rollback and data boundaries

A separately tested candidate uses a runtime created at its permanent path. Same-volume activation moves are journalled before modification. Post-activation startup/version/icon and shortcut checks must pass before commitment. Failure restores the previous source, runtime pointer, settings and shortcut; an interrupted activation is repaired by the next updater. Backups and old runtimes are retained.

Screenshot/history/project/recovery files are outside application replacement. Rollback does not uninstall publisher-managed Python/Tesseract or downloaded languages. CLI `-CloseRunningApp` may discard unsaved work, so save first. In-app updating waits for PNG/recovery saves and locks editing.

Projects and private recovery retain original pixels beneath redactions; flattened PNG/JPEG, clipboard, pins and OCR use rendered pixels. The annotation eraser intentionally removes whole annotations and can reveal their source pixels, like Delete or Undo.

## Native Windows checks still required

1. Run the single 2.1.2 updater in Windows PowerShell 5.1 on the multi-monitor rig that rejected 2.1.1. Verify the complete candidate suite, actual icon loading/application ID, native capture/OCR on all monitors, new runtime pointer, post-activation checks, shortcut and title version. Test spaces/apostrophes and redirected/OneDrive desktops.
2. Quit and restart through the refreshed BeastSnip shortcut. Verify the running taskbar logo/group, application name, pin/relaunch and dialog icons. Replace an old pinned Python shortcut if it persists. Confirm unrelated Python apps retain their identity. Check the actual IPropertyStore write/readback on Windows.
3. Browse all nine versions offline; search, resize and copy notes. Open history from the app menu, Update Centre and action search.
4. Draw with all original and new tools. Check palette, hex/custom colour, size units, preview, opacity, dash/dot/caps, smoothing, shape fills and arrowheads. Verify selected edits, Shift constraints, preferences after restart, erase/undo, PNG autosave and project/recovery round trips.
5. Verify readability and popup placement at real 100%, 125%, 150% and 200% display scaling, including short windows and multiple monitors. Confirm colour/style popovers disappear before capture.
6. Retest region/window/monitor captures, mixed DPI, negative origins, hotkeys, delays, tray/single-instance behaviour, OCR/sidebar/expanded reader, clipboard/export, pins and screenshot-library actions. Cloud geometry tests do not replace native capture checks.
7. Retest Quick Capture and scrolling capture against visible browser/document content. Exclude sticky headers; exercise ambiguous overlap, slow content, covered/moved windows, frame limits, Esc, Finish and Cancel. Windows can block automated input to elevated windows; manual scrolling remains available.
8. Simulate final-check/shortcut-property failure on Windows and verify automatic rollback and restored launch. Test interruption followed by rerunning the updater. Do not manually delete active runtimes/backups during installation.
9. Build.ps1 must be run on Windows to validate the packaged executable; Linux cannot perform that build. The source updater does not replace a separately packaged executable.
