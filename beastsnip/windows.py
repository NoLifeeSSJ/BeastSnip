"""Small ctypes boundary. All native rectangles are physical desktop pixels."""
import ctypes
from ctypes import wintypes as W
import os
import re
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPoint, QRect, QTimer, Signal
from PySide6.QtGui import QImage


IS_WINDOWS = os.name == "nt"


def enable_dpi_awareness():
    if IS_WINDOWS:
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (OSError, AttributeError):
            # Qt6 itself requests per-monitor DPI awareness; old Windows fallback.
            pass


if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetForegroundWindow.restype = W.HWND
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    user32.IsWindow.argtypes = [W.HWND]
    user32.IsWindowVisible.argtypes = [W.HWND]
    user32.IsIconic.argtypes = [W.HWND]
    user32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    user32.GetDC.argtypes, user32.GetDC.restype = [W.HWND], W.HDC
    user32.ReleaseDC.argtypes = [W.HWND, W.HDC]
    gdi32.CreateCompatibleDC.argtypes, gdi32.CreateCompatibleDC.restype = [W.HDC], W.HDC
    gdi32.CreateCompatibleBitmap.argtypes, gdi32.CreateCompatibleBitmap.restype = [W.HDC, ctypes.c_int, ctypes.c_int], W.HBITMAP
    gdi32.SelectObject.argtypes, gdi32.SelectObject.restype = [W.HDC, W.HANDLE], W.HANDLE
    gdi32.DeleteObject.argtypes = [W.HANDLE]
    gdi32.DeleteDC.argtypes = [W.HDC]
    gdi32.BitBlt.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HDC, ctypes.c_int, ctypes.c_int, W.DWORD]


def require_windows():
    if not IS_WINDOWS:
        raise RuntimeError("Desktop capture and global hotkeys require Windows 11. Image editing can still be used here.")


def cursor_position():
    point = W.POINT()
    if not user32.GetPhysicalCursorPos(ctypes.byref(point)):
        raise OSError("Windows could not read the pointer position.")
    return QPoint(point.x, point.y)


def escape_pressed():
    require_windows()
    return bool(user32.GetAsyncKeyState(0x1B) & 0x8000)


def window_at_point(point):
    require_windows()
    user32.WindowFromPoint.argtypes, user32.WindowFromPoint.restype = [W.POINT], W.HWND
    user32.GetAncestor.argtypes, user32.GetAncestor.restype = [W.HWND, W.UINT], W.HWND
    hwnd = user32.WindowFromPoint(W.POINT(point.x(), point.y()))
    root = user32.GetAncestor(hwnd, 2) if hwnd else None
    if not root:
        raise RuntimeError('There is no visible window under the selected area.')
    return root


def scroll_at(point, notches=-3):
    require_windows()
    target = window_at_point(point)
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(target, ctypes.byref(pid))
    if pid.value == os.getpid():
        raise RuntimeError('Select content in another application for scrolling capture.')
    user32.SetForegroundWindow.argtypes = [W.HWND]
    if user32.GetForegroundWindow() != target and not user32.SetForegroundWindow(target):
        raise RuntimeError('Windows could not focus the target. Use manual scrolling mode instead.')
    user32.SetPhysicalCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    if not user32.SetPhysicalCursorPos(point.x(), point.y()):
        raise OSError('Windows could not position the pointer for scrolling.')
    class MouseInput(ctypes.Structure):
        _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('mouseData', W.DWORD), ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]
    class KeyboardInput(ctypes.Structure):
        _fields_ = [('vk', W.WORD), ('scan', W.WORD), ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]
    class HardwareInput(ctypes.Structure):
        _fields_ = [('message', W.DWORD), ('low', W.WORD), ('high', W.WORD)]
    class InputData(ctypes.Union):
        _fields_ = [('mouse', MouseInput), ('keyboard', KeyboardInput), ('hardware', HardwareInput)]
    class Input(ctypes.Structure):
        _fields_ = [('type', W.DWORD), ('data', InputData)]
    value = Input(0, InputData(mouse=MouseInput(0, 0, (120 * notches) & 0xFFFFFFFF, 0x0800, 0, 0)))
    user32.SendInput.argtypes, user32.SendInput.restype = [W.UINT, ctypes.POINTER(Input), ctypes.c_int], W.UINT
    if user32.SendInput(1, ctypes.byref(value), ctypes.sizeof(value)) != 1:
        raise OSError('Windows blocked automatic scrolling. Use manual scrolling mode instead.')


def monitor_rectangles():
    require_windows()
    class MONITORINFOEX(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD), ("szDevice", W.WCHAR * 32)]
    callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, ctypes.POINTER(W.RECT), W.LPARAM)
    user32.GetMonitorInfoW.argtypes = [W.HANDLE, ctypes.POINTER(MONITORINFOEX)]
    result = []
    def callback(handle, dc, rect, data):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.rcMonitor
            result.append((info.szDevice, QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True
    user32.EnumDisplayMonitors.argtypes = [W.HDC, ctypes.c_void_p, callback_type, W.LPARAM]
    if not user32.EnumDisplayMonitors(None, None, callback_type(callback), 0) or not result:
        raise OSError("Windows could not enumerate the displays.")
    return result


@dataclass(frozen=True)
class DisplayMapping:
    screen: object
    device: str
    physical: QRect


def map_displays(screens, monitors):
    r"""Join Qt's screens to GDI devices without assuming their names agree.

    Qt can report an EDID name such as NE160QDM-NM9; GDI uses \\.\DISPLAY1.
    On Windows Qt retains native screen origins and scales screen dimensions.
    Require a unique device-name or origin/physical-size match, never list order.
    """
    result, used = [], set()
    for screen in screens:
        geometry = screen.geometry()
        ratio = screen.devicePixelRatio()
        def geometry_matches(rect):
            return (abs(rect.x() - geometry.x()) <= 2 and abs(rect.y() - geometry.y()) <= 2
                    and abs(rect.width() - geometry.width() * ratio) <= max(2, ratio)
                    and abs(rect.height() - geometry.height() * ratio) <= max(2, ratio))
        def key(name):
            return name.strip().casefold().removeprefix("\\\\.\\")
        candidates = [(device, rect) for device, rect in monitors
                      if device.casefold() not in used and key(device) == key(screen.name())]
        if len(candidates) != 1:
            candidates = [(device, rect) for device, rect in monitors
                          if device.casefold() not in used and geometry_matches(rect)]
        if len(candidates) != 1:
            raise RuntimeError(f"Cannot uniquely map display {screen.name()!r} at {geometry.x()},{geometry.y()} "
                               f"({geometry.width()} × {geometry.height()}, scale {ratio:g}). "
                               "The Windows display layout may be changing. Retry capture once the display layout has settled.")
        device, rect = candidates[0]
        used.add(device.casefold())
        result.append(DisplayMapping(screen, device, QRect(rect)))
    if not result:
        raise RuntimeError("Windows did not report any usable displays.")
    return result


def virtual_rect():
    monitors = monitor_rectangles()
    rect = QRect(monitors[0][1])
    for _, monitor in monitors[1:]:
        rect = rect.united(monitor)
    return rect


def grab_pixels(rect):
    """BitBlt visible desktop, including layered windows; no hidden-window claim."""
    require_windows()
    if rect.isEmpty():
        raise ValueError("The capture area is empty.")
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG),
                    ("biPlanes", W.WORD), ("biBitCount", W.WORD), ("biCompression", W.DWORD),
                    ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                    ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]
    dc, memory, bitmap, old = None, None, None, None
    try:
        dc = user32.GetDC(None)
        memory = gdi32.CreateCompatibleDC(dc)
        bitmap = gdi32.CreateCompatibleBitmap(dc, rect.width(), rect.height())
        if not all((dc, memory, bitmap)):
            raise OSError("Windows could not allocate the screenshot buffer.")
        old = gdi32.SelectObject(memory, bitmap)
        if not gdi32.BitBlt(memory, 0, 0, rect.width(), rect.height(), dc, rect.x(), rect.y(), 0x00CC0020 | 0x40000000):
            raise OSError("Windows could not copy the screen pixels.")
        gdi32.SelectObject(memory, old)
        old = None
        info = BITMAPINFOHEADER()
        info.biSize, info.biWidth, info.biHeight = ctypes.sizeof(info), rect.width(), -rect.height()
        info.biPlanes, info.biBitCount = 1, 32
        buffer = ctypes.create_string_buffer(rect.width() * rect.height() * 4)
        gdi32.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, ctypes.c_void_p, ctypes.c_void_p, W.UINT]
        if gdi32.GetDIBits(memory, bitmap, 0, rect.height(), buffer, ctypes.byref(info), 0) != rect.height():
            raise OSError("Windows could not read the screenshot pixels.")
        return QImage(buffer.raw, rect.width(), rect.height(), rect.width() * 4, QImage.Format.Format_RGB32).copy()
    finally:
        if old and memory:
            gdi32.SelectObject(memory, old)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        if dc:
            user32.ReleaseDC(None, dc)


def window_rectangle(hwnd):
    require_windows()
    if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        raise RuntimeError("No available external window. Switch to the window you want, then use the tray capture command.")
    rect = W.RECT()
    dwm = ctypes.WinDLL("dwmapi")
    dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, ctypes.c_void_p, W.DWORD]
    if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)):
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise OSError("Unable to read the active window bounds.")
    return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top).intersected(virtual_rect())


def parse_hotkey(text):
    parts = [part.strip().upper() for part in text.split("+")]
    modifiers = {"CTRL": 2, "ALT": 1, "SHIFT": 4, "WIN": 8}
    if len(parts) < 2 or any(part not in modifiers for part in parts[:-1]):
        raise ValueError("Use Ctrl, Alt, Shift or Win plus a letter, digit or F1–F24 (for example Ctrl+Alt+S).")
    mods = 0x4000  # MOD_NOREPEAT
    for part in parts[:-1]:
        mods |= modifiers[part]
    key = parts[-1]
    if len(set(parts[:-1])) != len(parts[:-1]):
        raise ValueError("Use each shortcut modifier only once.")
    if re.fullmatch(r"[A-Z0-9]", key):
        vk = ord(key)
    elif re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("The shortcut's final key must be a letter, digit or F1–F24.")
    return mods, vk


class WindowsIntegration(QObject, QAbstractNativeEventFilter):
    triggered = Signal()

    def __init__(self, app):
        QObject.__init__(self, app)
        QAbstractNativeEventFilter.__init__(self)
        self.app, self.last_external, self.registered = app, None, False
        self.hook = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.track_foreground)
        if IS_WINDOWS:
            app.installNativeEventFilter(self)
            self.track_foreground()
            # Foreground event hook remembers the prior external window even
            # when focus switches faster than the polling interval.
            self.callback_type = ctypes.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)
            self.foreground_callback = self.callback_type(lambda hook, event, hwnd, *args: self.remember(hwnd))
            user32.SetWinEventHook.argtypes = [W.DWORD, W.DWORD, W.HMODULE, self.callback_type, W.DWORD, W.DWORD, W.DWORD]
            user32.SetWinEventHook.restype = W.HANDLE
            self.hook = user32.SetWinEventHook(3, 3, None, self.foreground_callback, 0, 0, 0)
            self.timer.start(120)

    def remember(self, hwnd):
        if hwnd:
            pid = W.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != os.getpid() and user32.IsWindowVisible(hwnd):
                name = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, name, 256)
                if name.value in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "NotifyIconOverflowWindow", "#32768"):
                    return
                self.last_external = hwnd

    def track_foreground(self):
        if IS_WINDOWS:
            self.remember(user32.GetForegroundWindow())

    def register(self, text):
        mods, vk = parse_hotkey(text)
        if not IS_WINDOWS:
            return "Global shortcuts are available on Windows only."
        user32.UnregisterHotKey(None, 0xB517)
        self.registered = bool(user32.RegisterHotKey(None, 0xB517, mods, vk))
        if not self.registered:
            return f"{text} is unavailable or used by another app. Choose another shortcut in Settings. Capture buttons still work."
        return ""

    def nativeEventFilter(self, event_type, message):
        if IS_WINDOWS:
            msg = W.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == 0xB517:
                self.triggered.emit()
                return True, 0
        return False, 0

    def close(self):
        self.timer.stop()
        if IS_WINDOWS:
            user32.UnregisterHotKey(None, 0xB517)
            if self.hook:
                user32.UnhookWinEvent.argtypes = [W.HANDLE]
                user32.UnhookWinEvent(self.hook)
                self.hook = None
            self.app.removeNativeEventFilter(self)
