# BeastSnip

A local Windows 11 screenshot application written in Python 3.12 and PySide6. Dark interface, purple accents, editable annotations, opaque redaction, private history, offline OCR and pinned screenshots. No account, paid API, browser wrapper or remote image processing.

[Update v2.1.2](https://github.com/NoLifeeSSJ/BeastSnip/raw/refs/heads/main/delivery/Update-BeastSnip-2.1.2.ps1) · [First-time setup](https://github.com/NoLifeeSSJ/BeastSnip/raw/refs/heads/main/delivery/Setup-BeastSnip.ps1) · [Complete source ZIP](https://github.com/NoLifeeSSJ/BeastSnip/raw/refs/heads/main/delivery/BeastSnip-source.zip) · [SHA256 checksums](https://github.com/NoLifeeSSJ/BeastSnip/blob/main/delivery/SHA256SUMS.txt)

## BeastSnip 2.1.2: multi-monitor installation repair

Fixed two capture self-tests that combined one fake Windows display with every real Qt display on the computer. On a multi-monitor rig this could reject a connected screen such as `LEN G25-10` and stop the 2.1.1 installer. Both inventories are now isolated consistently, with regression tests for the reported second-screen layout. The actual Windows capture checks still run; no tests are bypassed. Run the single updater below even if 2.1.1 never finished installing. All drawing, history, OCR, recovery and screenshot features are retained.

![BeastSnip 2.1.1 drawing workspace](https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/main/delivery/BeastSnip-2.1.1-drawing.png)

## BeastSnip 2.1.1: drawing and clarity

- **Version History:** BeastSnip menu → Version History, Update Centre → Version History, or Ctrl+K → Version History. Browse each release separately, search all notes, show all releases, or copy the displayed notes. The complete history is bundled locally and works without Internet access. [Read the Markdown changelog](CHANGELOG.md).
- **Cleaner drawing controls:** Colour opens a compact palette with hex entry and an advanced picker. The swatch shows the actual colour. Pixel fields size themselves to keep “px” visible; labels blend into the drawing bar.
- **More tools:** Brush (G), Line (L), Rounded Box (U), and annotation Eraser (E), alongside every original tool. Eraser removes complete annotations rather than image pixels; a drag is one undo step. Redactions remain fully opaque regardless of drawing opacity.
- **More styles:** open Style for solid/dashed/dotted lines, round/square ends, opacity, smooth freehand strokes, shape fills and arrowheads at one or both ends. Options adapt to the tool, with a live preview. Shift constrains shapes to equal sides and lines/arrows to 45-degree angles.
- **Styles stay with you:** each tool remembers its defaults across switches and restarts. Select an existing annotation to edit its properties; selection remains in place and each change supports Undo. PNG auto-save, recovery and editable projects retain the result.
- **Icon fixes:** the settings gear is centred and symmetric. BeastSnip uses its own Windows application ID and global icon, and the refreshed desktop shortcut stores matching taskbar and relaunch properties. Restart through the refreshed shortcut. An old Python shortcut already pinned to your taskbar may need to be unpinned and replaced with the BeastSnip shortcut.

New `.beastsnip` files use project format 2 to preserve new styles; 2.1.1 opens earlier format-1 projects without changing their drawing appearance. Older app versions reject format 2 instead of silently dropping styles. Keep a flattened PNG for sharing.

![Version history, separated by release](https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/main/delivery/BeastSnip-2.1.1-history.png)

## BeastSnip 2.1

- **Quick Capture:** enable **Quick** beside New Snip to save a sequence without opening or replacing the editor. Each snip is saved in Screenshots; a small preview offers Open, Copy and Pin. The global capture shortcut and tray actions use the same mode. Turn Quick off to return to normal editing. Quick Capture always saves PNGs, including when ordinary auto-save is off. Failed captures stay in memory with Retry; the last three successful previews are retained, and all saved PNGs remain in the library.
- **Editable projects and recovery:** use More → Save Editable Project (**Ctrl+Shift+P**) to keep annotations, original pixels, OCR and up to ten undo/redo states in a `.beastsnip` file. Open a project from the BeastSnip menu, Open, or drag and drop. Automatic private recovery saves after a short pause; Restore Session brings back the last session after restart or a crash. An un-restored older session is preserved when starting new work. Preferences can turn recovery off and clear automatic recovery data.
- **Update Centre:** open the BeastSnip menu → Update Centre, or find it with Ctrl+K. Check releases, read notes, then install a verified updater. Update checks happen only when requested. The app finishes recovery/PNG saves before an in-app update and the updater opens visibly in PowerShell.
- **Screenshots library:** favourites, Today / Last 7 days / Last 30 days filters, Ctrl/Shift multi-select, rename, bulk export and deletion with Undo. Deleted PNGs move to `.BeastSnipTrash` inside the Screenshots folder; they are retained locally for recovery. Export avoids overwriting existing names. Large libraries show the newest 120 matches, with Load More. Date filters use file modification time, so editing a PNG updates its date.
- **Capture magnifier:** a zoomed view of frozen desktop pixels follows the selection cursor. Press **M** to toggle it, or change the default in Preferences.
- **Scrolling capture:** New Snip arrow → Scrolling Capture. Select the scrolling content inside one visible window, excluding toolbars and sticky headers. Automatic mode scrolls downward; manual mode uses Add Frame after you scroll. Esc pauses; Finish saves the joined image; Cancel discards it. It stops on ambiguous overlap, moved/covered windows or size limits instead of guessing. Best with static vertical pages/documents; animations, repeated patterns, sticky content and some nested scrolling areas may require smaller manual steps. Limits: 40 million pixels, 32,000 pixels high, automatic frame limit 2–40. Windows may block automated input to elevated apps; manual scrolling remains available.

**Editable projects and private recovery contain the original pixels, including beneath redactions.** Share flattened PNG/JPEG exports when originals should not be included. Recovery lives on this computer and is on by default; disabling it clears automatic recovery files. PNG export, clipboard images, pinning and OCR continue to use flattened pixels.

![Quick Capture preview](https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/main/delivery/BeastSnip-2.1-quick.png)

## The workspace

The native app now has a compact header and a grouped tool rail. The BeastSnip logo opens navigation, folders, preferences, shortcuts and app information. **Library** and **Editor** let you switch views without discarding the current session.

- **New Snip** captures a region. Its arrow opens active-window/monitor capture, monitor selection and the same 0/3/5/10 second delay options.
- The left rail keeps every tool visible and grouped: Navigate, Annotate and Finish. Colour, stroke and text size appear when relevant, including when an annotation is selected.
- The footer prioritises **Copy Image**, **Save**, **Extract Text**, and **More**. More contains Save As, Save to History, Pin on Screen and text/focus options. The Extract Text arrow includes OCR Area.
- **Ctrl+K** searches actions and tools. **Ctrl+V** pastes an image when you are not typing text. **F1** opens a shortcut guide. **Ctrl+Shift+F** gives the image more space in Focus mode.
- The **Screenshots** tab shows auto-saved PNGs, loads thumbnails in the background, and supports filename search, copy/open, refresh and folder access. **Saved History** retains title/tag/OCR search, rename, delete, clear, and explicitly stored OCR text.
- Preferences are grouped into Captures & storage, Workspace, and Offline OCR. The OCR sidebar and expanded reader remain resizable, editable and copyable, with text-size and line-wrap controls.

### Automatic saving

**New captures save automatically to `C:\SnipsV1\Screenshots`.** That folder name is intentionally separate from the existing app installation at `C:\SnipV1`. The update creates and checks the folder, backs up settings, and enables auto-save for installations migrating from 1.x. Subsequent updates preserve an existing custom Screenshots folder or explicit auto-save-off choice.

Each capture receives a unique timestamped PNG. Image edits, crop, redaction, undo and redo update that same file after a short pause. Writes run in order, in the background, using atomic file replacement. The save indicator distinguishes pending, successful and failed saves. Failures show a persistent banner; **Save** or **Retry save** retries. Changing Preferences can supply a writable directory for an initial failed save. Existing open captures that have already saved keep their original path; folder preferences apply to new captures.

Pasting an image creates a new auto-saved capture when enabled. Opening an external image does not overwrite that source: use Save to create a PNG in Screenshots or Save As to export elsewhere. Reopening a PNG from your Screenshots folder resumes auto-saving edits to it when auto-save is enabled. PNG captures are flattened; editable objects/undo are retained separately by session recovery and explicit projects. PNG auto-save does not store OCR text; Save to History does.

The initial capture is written **before editing**. Edits replace its current PNG, but earlier clipboard copies, separate exports, saved history entries, pins and file/OS backups remain independent. Turn off auto-save, automatic history, Quick Capture and editable recovery in Preferences before capturing if the initial pixels must not be stored. Auto-copy and automatic history remain off by default.

![BeastSnip 2.1 screenshot library](https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/main/delivery/BeastSnip-2.1-library.png)

## Update an existing installation (2.1.2)

Save any open capture first. Paste this into PowerShell to download and run the single, self-contained updater:

```powershell
$beastUpdate = Join-Path $env:TEMP 'Update-BeastSnip-2.1.2.ps1'
Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/NoLifeeSSJ/BeastSnip/v2.1.2/delivery/Update-BeastSnip-2.1.2.ps1' -OutFile $beastUpdate
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$beastUpdate" -InstallDir "C:\SnipV1" -CloseRunningApp -Launch
```

You can also [download Update-BeastSnip-2.1.2.ps1](https://github.com/NoLifeeSSJ/BeastSnip/raw/refs/tags/v2.1.2/delivery/Update-BeastSnip-2.1.2.ps1) and run it with the same arguments. This script updates the application to version 2.1.2, backs up replaced application files, refreshes dependencies and the icon/desktop shortcut, installs or repairs Tesseract, prepares missing OCR languages and saves verified OCR paths. Your saved capture history, export folder, language selection, hotkey and other preferences are retained.

**`-CloseRunningApp` explicitly closes BeastSnip in the target installation, including when it is hidden in the tray. Unsaved in-memory captures/edits will be discarded, so save them first.** Other Python programs and other BeastSnip installations are not targeted. The updater rechecks process identity before stopping it. Without this switch it stops immediately with instructions if BeastSnip is running; it no longer waits silently for two minutes. You can instead use tray → Quit BeastSnip and omit the close switch.

The script displays **eight stages** and prints **`UPDATE COMPLETE - BeastSnip 2.1.2`** only after the required checks pass. It prepares source and dependencies separately, runs the UI smoke check and tests, then closes the target installation and snapshots rollback data. OCR repair, native capture and folder checks run before application activation. Post-activation version/startup checks and shortcut refresh must also succeed. Generated package bytecode is cleared to prevent stale imports.

Each new Python environment is created at its permanent location under `C:\SnipV1\.beastsnip-runtimes`; it is never moved afterward. `runtime.json` selects the active environment. Existing `.venv` installations remain a supported fallback and are retained. If activation or final checks fail, the previous source, runtime pointer, settings and desktop shortcut are restored automatically; an optional relaunch opens the previous version. Failures before activation leave the live application files in place. Incomplete activation journals are repaired on the next updater run. Backups and old runtimes are retained under `.beastsnip-backups` and `.beastsnip-runtimes`; do not delete the active runtime.

Screenshots, history, editable projects and recovery journals are outside application replacement. Third-party Python/Tesseract installations and downloaded language files are not uninstalled by rollback. Logs are saved to `%LOCALAPPDATA%\BeastSnip\update-logs`; failures show the log path. The title bar confirms the running version. This update also retains the 2.0.1 fix for Windows' 396-pixel OCR viewport: layout checks use font metrics and readable space instead of a hardcoded pixel minimum.

The monitor fix separates Qt's friendly model name (for example `NE160QDM-NM9`) from GDI's capture identifier (`\\.\DISPLAY1`). Region overlays use a unique device-name or position/DPI match; list order is never used as a guess. Friendly and duplicate model names no longer make a connected monitor appear disconnected. A real display-layout change refreshes the selector and asks for a retry.

OCR repair checks PATH, per-user installation folders, Program Files and Windows installer registry metadata. It validates the executable, installs it through `winget` if missing, repairs an unstartable runtime once, and prepares language files from the official Tesseract repository at a pinned commit. Downloaded English data is SHA256-verified. App-managed language files live under `%LOCALAPPDATA%\BeastSnip\ocr\tessdata`; original system language files are not overwritten. The repair merges only `ocr_path` and `ocr_data_dir` into settings and backs up the previous JSON before writing it. No images or OCR text are sent online.

Before reporting completion, the updater recognises a generated test image, verifies that opaque pixels yield no OCR text, maps your actual connected displays and checks native capture buffers in memory. It writes no diagnostic screenshot files. If any required check fails it stops with the specific error; it does not claim the repair passed. Downloading Python, the OCR runtime or language files needs Internet access. Tesseract's publisher installer may show a UAC prompt; accept it to finish installing that runtime. Normal use remains local and needs no elevation.

To repair OCR again after an update, without reinstalling the app:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\SnipV1\Repair-OCR.ps1"
```

## Install with one PowerShell command

Download [Setup-BeastSnip.ps1](https://github.com/NoLifeeSSJ/BeastSnip/raw/refs/heads/main/delivery/Setup-BeastSnip.ps1) into your Downloads folder. Open a regular PowerShell window and paste:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$HOME\Downloads\Setup-BeastSnip.ps1" -InstallDir "C:\SnipV1" -InstallOCR -Launch
```

This command extracts the complete project, locates 64-bit Python 3.12–3.14 (preferring 3.12), installs Python 3.12 for your user through `winget` if none is found, creates a separate Python runtime under `C:\SnipV1\.beastsnip-runtimes`, installs the pinned dependencies, checks imports and real UI startup, runs the self-tests and creates **BeastSnip.lnk on your desktop**, using the included multi-resolution purple BeastSnip icon. `-Launch` opens the app after setup. Re-running setup uses the same candidate checks and reversible activation as the updater.

`-InstallOCR` installs/configures and tests the local Tesseract runtime using the Windows Package Manager and the OCR repair helper. That publisher's installer may request elevation. If OCR repair fails, setup reports the error and restores the previous settings; the candidate is not activated. Omit `-InstallOCR` to skip that optional installation. The update script always includes OCR repair. Setup needs Internet access for Python, packages and optional Tesseract/language files; normal operation and OCR do not.

No machine-wide execution policy or Windows security setting is changed. `-ExecutionPolicy Bypass` applies only to this installer process. Python installation requires the Windows **App Installer** (`winget`); if unavailable, install 64-bit Python 3.12 from <https://www.python.org/downloads/windows/> and rerun setup. Include the Python launcher in the Python installer. Standard app use needs no administrator access. If your Windows policy blocks creating `C:\SnipV1`, supply `-InstallDir "$env:LOCALAPPDATA\BeastSnipApp"`.

### Install from the source ZIP or repository

Extract the source ZIP into a folder you own. In PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install.ps1" -InstallDir "C:\SnipV1" -InstallOCR -Launch
```

Installing with `Install.ps1` copies only application files, tools and tests. It leaves separately saved screenshots, history and the source repository intact. Replaced application files are backed up, not silently discarded. Close BeastSnip before updating. If setup reports a busy file, quit using the tray menu and rerun setup.

### Launch later

Double-click **BeastSnip** on the desktop or `C:\SnipV1\Launch.cmd`. From PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\SnipV1\Launch.ps1"
```

For diagnostics, add `-Console`. No virtual environment activation is needed. Launching a second copy brings the existing window forward; it does not register a second hotkey.

## Capture

- **New Snip** or **Ctrl+Alt+S** hides BeastSnip and its pins, waits for the selected delay, freezes the desktop and displays an overlay on each monitor. Drag in any direction. The border and dimension label use physical image pixels. Escape or right-click cancels. A successful capture opens in the editor.
- Open the arrow beside **New Snip**, choose a monitor, then **Capture selected monitor**. The same choice is used by the tray action.
- **Active Window** captures the previously focused external window. BeastSnip remembers external foreground changes before it takes focus, ignores its own windows and ignores the taskbar/desktop. Switch to your target window and use the tray action for the clearest target selection.
- Delay is immediate, 3, 5 or 10 seconds and applies to each capture mode. Open menus or position your desktop while waiting.
- Global shortcuts can use Ctrl, Alt, Shift and Win with a letter, digit or F1–F24. Change the shortcut in Settings if Windows reports a conflict. The capture menu and tray capture remain available.

The implementation uses Windows GDI `BitBlt` and **visible desktop pixels**. Active-window capture uses DWM window bounds; it cannot recover obscured or minimised window contents. Other windows covering the target appear in the screenshot. Protected video, secure desktops/UAC prompts and some hardware surfaces cannot be captured reliably. Multi-monitor capture uses a native physical-pixel desktop rectangle, including negative coordinates, with an individual Qt overlay mapped to each display's scale. Areas between disjoint monitors are whatever Windows returns for those desktop pixels. Real mixed-DPI and multi-monitor validation is still required on Windows; see `VERIFICATION.md`.

Finish any modal Settings/file/message dialog before using a capture hotkey. Captures keep the previous editing session until a successful selection replaces it. Unsaved changes require confirmation before replacement. The overlay uses the frozen image and is never recaptured into itself.

## Editor

The screenshot takes most of the window. Tool buttons have tooltips; the selected tool is purple. The tool rail groups tools vertically and scrolls when needed. Context controls show only the options relevant to the active tool or selected annotation.

| Tool | Use |
| --- | --- |
| Select | Select, drag or delete an annotation; double-click a text label to edit its text |
| Pan | Drag the view; middle mouse also pans |
| Pen / Brush / Highlight | Freehand objects with smoothing, line patterns, stroke ends and opacity; Highlight uses translucent ink |
| Line | Straight lines; Shift snaps to 45-degree angles |
| Rounded Box | Rounded rectangle with outline, solid fill or soft fill |
| Eraser | Erase whole annotations; dragging groups the deletion into one undo step, leaving source pixels intact |
| Arrow / Box / Fill / Ellipse | Drag from one corner/end to another |
| Text | Add a multiline label, with adjustable font size |
| Step | Click to add the next numbered marker |
| Redact | Draw a solid opaque black block |
| Crop | Drag the kept area; crop flattens objects into pixels; Undo restores the editable objects |

Colour, Size, Text px and Style apply to new annotations and to the selected annotation when applicable. Change the controls before drawing, or select an object and change them. Style includes pattern, stroke ends, opacity, smoothing, fill and arrowheads where relevant; Reset This Tool restores its defaults. Export uses full image resolution, independently of zoom, scrolling and window size.

Use Undo, Redo and Delete in the contextual bar, zoom/Fit/1:1 below the image, and the following shortcuts:

| Shortcut | Action |
| --- | --- |
| Ctrl+C | Copy the current flattened image (inside the OCR text field it copies selected text) |
| Ctrl+S | Save current image to Screenshots |
| Ctrl+Shift+S | Save As (PNG/JPEG) |
| Ctrl+K | Find an action or tool |
| Ctrl+V | Paste image, or paste text inside the OCR field |
| Ctrl+O | Open image |
| Ctrl+Shift+F | Toggle Focus mode |
| F1 / F5 | Keyboard guide / Refresh library |
| Ctrl+Z | Undo |
| Ctrl+Y / Ctrl+Shift+Z | Redo |
| Delete | Delete the selected annotation |
| Escape | Cancel the current drawing/selection and return to Select |
| Ctrl+mouse wheel | Zoom |
| Middle mouse drag | Pan |

1:1 means one image pixel per physical display pixel. The displayed zoom percentage is measured against logical Qt view units, so 1:1 on a 150% display shows approximately 67%. Undo retains up to 35 editing states in memory. Library navigation keeps the current session in memory; **Editor** in the header returns to it.

**Copy Image**, **Save As**, **Save to History**, **Pin on Screen** and OCR always use the current flattened image. PNG preserves transparency; JPEG uses a white background and the quality in Settings (default 92). Filenames default to `BeastSnip_YYYY-MM-DD_HH-MM-SS.png`. Open existing PNG, JPEG, BMP or WebP images with Open or drag and drop one onto the window.

### Privacy and redaction

An editable session retains the original and undo states in memory and, when enabled, in private recovery files. Explicit editable projects also contain originals and recent undo/redo states. Redaction becomes a solid black block when copied, saved, pinned or sent to OCR. Exported images have no editable layers, source image text or embedded original. The editor redraws into a fresh image before encoding. Crop flattens the current view and can itself be undone while the app remains open.

**Redaction does not erase earlier exports, clipboard contents, pinned images, screenshots held by other programs, file backups or OS memory/pagefile copies.** Delete or replace earlier copies yourself. Copying alone does not mark a session saved. Successful auto-save or an explicit save keeps its pixels; unsaved edits/text still trigger a discard warning. Exporting an image does not save its OCR text; use Save to History for that.

Automatic history and automatic clipboard copy are both **off by default**. BeastSnip saves new captures as PNGs in the Screenshots folder by default; it does not use temporary screenshot files. OCR sends PNG bytes directly to the local Tesseract process through stdin, so it needs no temporary screenshot file. Disable auto-save, automatic history, Quick Capture and editable recovery if the initial unredacted capture must never be saved. Auto-save explicitly saves the initial capture before editing; recovery/projects retain its editable source. Saving that item again replaces its pixels, thumbnail and OCR text.

## Local OCR

Choose **Extract Text** for the full flattened image, or **OCR Area**, then drag a rectangle. OCR runs in a worker, leaves the UI responsive and has a 90-second timeout. Extracted text is editable and selectable; Copy Text copies it. A blank result is reported as no readable text, not invented output. Editing/redacting the image invalidates previous OCR; stale results from an image edited during processing are discarded.

Install Tesseract manually if necessary:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
```

Set **Tesseract executable** in Preferences → Offline OCR if it was not found automatically, typically `C:\Program Files\Tesseract-OCR\tesseract.exe`. English uses `eng.traineddata` in the runtime's `tessdata` folder. Select other languages in the Tesseract installer, or obtain their trained data from the official project at <https://github.com/tesseract-ocr/tessdata_fast>. Use Settings language `eng`, `deu` or `eng+deu`, matching the installed files. Validate with:

```powershell
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs
```

Installing Tesseract language files is separate from installing the Python application. Missing runtime/languages produce an actionable error; the rest of the app keeps working. Images and OCR text are never uploaded by BeastSnip.

The new update/repair script handles this runtime/language configuration automatically. Preferences → Offline OCR also exposes **Language files folder** for an explicit `tessdata` directory. An explicit directory avoids interference from a stale system `TESSDATA_PREFIX`; language availability is checked before image bytes are sent to Tesseract.

## Gallery, pinning and tray

**Save to History** explicitly stores a flattened image, its thumbnail, timestamp, size, title, tags and any text you extracted. Saving the same open item again updates it. Reopening starts a new editing session from the flattened pixels; it cannot recover old annotation objects or hidden originals. Search matches titles, tags and explicitly saved OCR text. Select a thumbnail to open, copy, rename, tag, open its folder or delete it. Clear History asks for confirmation.

SQLite is the authoritative image store, keeping pixels and metadata in one transaction. **Open Folder** explicitly materialises a flattened convenience PNG; deleting that PNG does not break the gallery, and it can be recreated. Updating history removes the old convenience PNG, replaces the stored pixels and regenerates the thumbnail. Missing/damaged records show an error. Deleting removes the record, its stored image and thumbnail, saved OCR and any convenience PNG for that item. **Separately exported files and clipboard copies remain.** Secure-delete is enabled for the database; this is not a guarantee of forensic erasure from SSDs, backups or snapshots.

**Pin on Screen** opens an independent always-on-top window containing flattened pixels. Drag its image or title bar, resize it (image aspect ratio is preserved with letterboxing), adjust opacity with the slider and close it with the visible Close button or window control. Pins remain while the main window is minimised; all pins close when you quit the app. Capturing temporarily hides BeastSnip's pins.

The tray menu has region, window and monitor capture, gallery, settings and **Quit BeastSnip**. Closing the main window defaults to minimising to tray with an explanation the first time. Change this in Settings to quit on close. If no system tray is available, closing quits instead. Quit waits for an in-progress save/OCR to finish and asks about unsaved edits.

## Storage

- **Auto-saved PNGs:** `C:\SnipsV1\Screenshots` by default; configurable in Preferences. Image edits update the same PNG.

| Item | Default location |
| --- | --- |
| App source, runtime pointer, candidate runtimes and rollback backups | `C:\SnipV1` |
| Private editable session recovery | `%LOCALAPPDATA%\BeastSnip\recovery` |
| Screenshot favourites | `%LOCALAPPDATA%\BeastSnip\library.sqlite3` |
| Verified updater downloads and status | `%LOCALAPPDATA%\BeastSnip\updates` |
| Settings | `%LOCALAPPDATA%\BeastSnip\settings.json` |
| Rotating local logs | `%LOCALAPPDATA%\BeastSnip\beastsnip.log` (1 MB × 3) |
| History database | `%LOCALAPPDATA%\BeastSnip\history\history.sqlite3` |
| Materialised history PNGs | Same history folder, only after Open Folder |
| Suggested export folder | `%USERPROFILE%\Pictures\BeastSnip` |

Settings can select export and history folders. Selecting a different history folder opens a separate gallery; it does not silently move or delete existing history. Settings, history and logs are per-user; the Screenshots folder has its own configurable location. Logs contain error types/status, never screenshot pixels or OCR text. `BEASTSNIP_DATA_DIR` isolates settings/history/logs and the default Screenshots folder for tests. No secret keys or accounts are needed.

## Build a Windows executable

On Windows, after installation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\SnipV1\Build.ps1"
```

This installs the pinned PyInstaller build dependencies, creates a windowed application with the icon/resources and runs its startup smoke check. Output: `C:\SnipV1\dist\BeastSnip\BeastSnip.exe`. Distribute the **entire** `dist\BeastSnip` directory, including `_internal`, not just the executable. The executable no longer requires a separate Python installation. Tesseract and language files remain optional separate dependencies. Resource paths resolve from the Python package both from source and in PyInstaller's bundle. PyInstaller cannot build Windows executables on Linux; that build is not claimed as verified here.

## Development and tests

Logical boundaries: `ui.py` (icons/action search), `autosave.py` (serial capture writes), `windows.py` (ctypes/hotkey/foreground tracking), `capture.py` (frozen overlays), `document.py` (annotations/rendering/undo/crop/export), `editor.py`, `storage.py` (SQLite), `ocr.py` (local process worker), `dialogs.py`, `app.py` (UI/lifecycle), and `config.py` (per-user settings/atomic writes).

```powershell
Set-Location C:\SnipV1
. .\tools\Install-Transaction.ps1
$beastPython = Get-BeastSnipPython -InstallDir (Get-Location).Path
& $beastPython -m unittest discover -s tests -v
& $beastPython -m beastsnip --smoke-test
& .\tests\test_updater.ps1
& .\tests\test_transactions.ps1
& .\tests\test_shell_identity.ps1
```

Tesseract integration tests run only when `tesseract` is on PATH; other tests do not require OCR. `--smoke-test` starts the real UI, annotates, crops, undoes/redoes, checks rendered dimensions and exits. It does not register a hotkey, capture your desktop or prove Windows capture works. Use an isolated `BEASTSNIP_DATA_DIR` when testing. `tools/render_preview.py` renders the actual UI with generated sample images, real OCR and isolated temporary storage. `tools/make_icon.py` regenerates the ICO/PNG from the included original SVG; `tools/make_history.py` generates the offline history from CHANGELOG.md; `tools/make_installer.py` refreshes that history and regenerates the self-contained installer and source ZIP. `tools/render_211_preview.py` renders the 2.1.1 drawing/colour/style/history previews. See **VERIFICATION.md** for actual results and the outstanding Windows checklist.

For Linux/offscreen development (editing and automated tests only):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen BEASTSNIP_DATA_DIR=/tmp/beastsnip-check .venv/bin/python -m beastsnip --smoke-test
```

## Troubleshooting

- **Auto-save failure:** the capture stays open and unsaved. Check the folder/drive, free space and permissions. Choose a writable Screenshots folder in Preferences, then Retry save. Save As can also export the current pixels. A failed PNG save never reports success.
- **Python taskbar icon:** restart using the updated BeastSnip shortcut. Replace an old pinned Python shortcut by pinning BeastSnip; no Explorer restart or icon-cache deletion is needed.
- **Find a relocated control:** press Ctrl+K, or open More / the New Snip arrow. All original tools and actions remain available.

- **Shortcut does nothing:** run `Launch.ps1 -Console`; check the per-user log; rerun Install.ps1 if imports/dependencies are missing.
- **Shortcut conflict:** choose another valid shortcut in Settings; close the other app holding the shortcut if needed.
- **No active window:** switch to the target app, then use the BeastSnip tray capture action. A minimised window must be restored first.
- **Black/incorrect capture:** protected content and the secure desktop are unsupported. Check the Windows checklist on the actual multi-monitor layout; report monitor scaling and arrangement if a display cannot be mapped.
- **Clipboard busy:** close competing clipboard tools and retry. BeastSnip checks that an image of the expected size is returned after copying.
- **OCR unavailable:** select the full `tesseract.exe` path and verify language files with `--list-langs`.
- **Locked or unwritable history:** choose a writable local history folder, ensure another program isn't locking the database, and check free disk space. Keep live SQLite history out of unreliable network-sync locations.
- **App stays running when closed:** this is the configurable tray behaviour. Use tray → Quit BeastSnip.

Scrolling capture uses visible pixels; it does not fetch pages or documents from their source. Screen recording, AI tools and cloud sharing are outside this release.
