from __future__ import annotations

from ctypes import WINFUNCTYPE, byref, c_int, c_longlong, c_uint, c_void_p, create_unicode_buffer, sizeof, windll
from ctypes.wintypes import BOOL, DWORD, HWND, LPARAM, RECT, UINT
from dataclasses import dataclass
from pathlib import Path


user32 = windll.user32
kernel32 = windll.kernel32

try:
    dwmapi = windll.dwmapi
except OSError:
    dwmapi = None


GWL_EXSTYLE = -20
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14
SW_RESTORE = 9
SW_SHOW = 5
GW_HWNDPREV = 3


EnumWindowsProc = WINFUNCTYPE(BOOL, HWND, LPARAM)


user32.EnumWindows.argtypes = [EnumWindowsProc, LPARAM]
user32.EnumWindows.restype = BOOL
user32.IsWindowVisible.argtypes = [HWND]
user32.IsWindowVisible.restype = BOOL
user32.IsWindow.argtypes = [HWND]
user32.IsWindow.restype = BOOL
user32.IsIconic.argtypes = [HWND]
user32.IsIconic.restype = BOOL
user32.GetForegroundWindow.restype = HWND
user32.GetWindowTextLengthW.argtypes = [HWND]
user32.GetWindowTextLengthW.restype = c_int
user32.GetWindowTextW.argtypes = [HWND, c_void_p, c_int]
user32.GetWindowTextW.restype = c_int
user32.GetClassNameW.argtypes = [HWND, c_void_p, c_int]
user32.GetClassNameW.restype = c_int
user32.GetWindowLongW.argtypes = [HWND, c_int]
user32.GetWindowLongW.restype = c_int
user32.GetWindowThreadProcessId.argtypes = [HWND, c_void_p]
user32.GetWindowThreadProcessId.restype = DWORD
user32.GetWindowRect.argtypes = [HWND, c_void_p]
user32.GetWindowRect.restype = BOOL
user32.GetWindow.argtypes = [HWND, UINT]
user32.GetWindow.restype = HWND
user32.SetWindowPos.argtypes = [HWND, HWND, c_int, c_int, c_int, c_int, UINT]
user32.SetWindowPos.restype = BOOL
user32.ShowWindow.argtypes = [HWND, c_int]
user32.ShowWindow.restype = BOOL
user32.BringWindowToTop.argtypes = [HWND]
user32.BringWindowToTop.restype = BOOL
user32.SetForegroundWindow.argtypes = [HWND]
user32.SetForegroundWindow.restype = BOOL

get_window_long_ptr = getattr(user32, "GetWindowLongPtrW", None)
if get_window_long_ptr is not None:
    get_window_long_ptr.argtypes = [HWND, c_int]
    get_window_long_ptr.restype = c_longlong

set_window_long_ptr = getattr(user32, "SetWindowLongPtrW", None)
if set_window_long_ptr is not None:
    set_window_long_ptr.argtypes = [HWND, c_int, c_longlong]
    set_window_long_ptr.restype = c_longlong


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    process_name: str
    class_name: str

    @property
    def display_name(self) -> str:
        title = self.title.strip() or "Untitled window"
        process = self.process_name or "unknown-process"
        return f"{title} [{process}]"


def set_dpi_awareness() -> None:
    try:
        windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass

    try:
        user32.SetProcessDPIAware()
    except OSError:
        pass


def list_visible_windows(excluded_hwnds: set[int] | None = None) -> list[WindowInfo]:
    windows: list[WindowInfo] = []
    excluded_hwnds = excluded_hwnds or set()

    @EnumWindowsProc
    def enum_windows_callback(hwnd: int, _lparam: int) -> bool:
        if hwnd in excluded_hwnds:
            return True

        if not user32.IsWindowVisible(hwnd):
            return True

        if _is_tool_window(hwnd) or _is_cloaked(hwnd):
            return True

        title = _get_window_text(hwnd).strip()
        if not title:
            return True

        windows.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                process_name=_get_process_name(hwnd),
                class_name=_get_class_name(hwnd),
            )
        )
        return True

    user32.EnumWindows(enum_windows_callback, 0)
    windows.sort(key=lambda item: item.display_name.lower())
    return windows


def get_window_info(hwnd: int) -> WindowInfo | None:
    if not is_window(hwnd):
        return None

    if not user32.IsWindowVisible(hwnd):
        return None

    if _is_tool_window(hwnd) or _is_cloaked(hwnd):
        return None

    title = _get_window_text(hwnd).strip()
    if not title:
        return None

    return WindowInfo(
        hwnd=hwnd,
        title=title,
        process_name=_get_process_name(hwnd),
        class_name=_get_class_name(hwnd),
    )


def is_window(hwnd: int) -> bool:
    return bool(user32.IsWindow(hwnd))


def get_foreground_window() -> int:
    return int(user32.GetForegroundWindow())


def get_window_title(hwnd: int) -> str:
    return _get_window_text(hwnd).strip()


def is_window_visible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def is_window_minimized(hwnd: int) -> bool:
    return bool(user32.IsIconic(hwnd))


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = RECT()
    if not user32.GetWindowRect(hwnd, byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def get_window_above(hwnd: int) -> int:
    above = user32.GetWindow(HWND(hwnd), GW_HWNDPREV)
    return int(above or 0)


def activate_window(hwnd: int) -> bool:
    if not is_window(hwnd):
        return False

    if is_window_minimized(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)

    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    return get_foreground_window() == hwnd


def _get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _get_class_name(hwnd: int) -> str:
    buffer = create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def _is_tool_window(hwnd: int) -> bool:
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    return bool(ex_style & WS_EX_TOOLWINDOW)


def _is_cloaked(hwnd: int) -> bool:
    if dwmapi is None:
        return False

    cloaked = DWORD()
    result = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, byref(cloaked), c_uint(sizeof(cloaked)))
    if result != 0:
        return False
    return bool(cloaked.value)


def _get_process_name(hwnd: int) -> str:
    process_id = DWORD()
    user32.GetWindowThreadProcessId(hwnd, byref(process_id))
    if process_id.value == 0:
        return ""

    process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process_handle:
        return ""

    try:
        buffer_size = DWORD(1024)
        buffer = create_unicode_buffer(buffer_size.value)
        if kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer, byref(buffer_size)):
            return Path(buffer.value).name
        return ""
    finally:
        kernel32.CloseHandle(process_handle)
