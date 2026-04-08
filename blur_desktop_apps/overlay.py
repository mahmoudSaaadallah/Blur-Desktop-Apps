from __future__ import annotations

import tkinter as tk
from ctypes import POINTER, Structure, byref, c_int, c_size_t, c_void_p, pointer, sizeof, windll
from ctypes.wintypes import BOOL, DWORD, HWND, RECT

from blur_desktop_apps import windows


user32 = windll.user32


GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080
SWP_NOOWNERZORDER = 0x0200
SWP_NOZORDER = 0x0004

WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4


class ACCENT_POLICY(Structure):
    _fields_ = [
        ("AccentState", c_int),
        ("AccentFlags", c_int),
        ("GradientColor", DWORD),
        ("AnimationId", c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(Structure):
    _fields_ = [
        ("Attribute", c_int),
        ("Data", c_void_p),
        ("SizeOfData", c_size_t),
    ]


class WindowOverlay:
    def __init__(self, root: tk.Tk, target_hwnd: int, title: str) -> None:
        self.root = root
        self.target_hwnd = target_hwnd
        self.title = title
        self.visible = False

        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#101010")

        self.badge = tk.Label(
            self.window,
            text="Protected",
            bg="#101010",
            fg="#f5f5f5",
            padx=12,
            pady=6,
            font=("Segoe UI", 10, "bold"),
        )
        self.badge.place(relx=1.0, x=-18, y=18, anchor="ne")

        self.window.update_idletasks()
        self.hwnd = self.window.winfo_id()
        self._configure_window_style()
        self._apply_blur()

    def show_over(self, rect: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = rect
        width = max(0, right - left)
        height = max(0, bottom - top)
        if width <= 0 or height <= 0:
            self.hide()
            return

        self.window.geometry(f"{width}x{height}+{left}+{top}")
        self.window.deiconify()
        user32.SetWindowPos(
            self.hwnd,
            HWND(-1),
            left,
            top,
            width,
            height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_NOOWNERZORDER,
        )
        self.visible = True

    def hide(self) -> None:
        if not self.visible:
            self.window.withdraw()
            return

        user32.SetWindowPos(
            self.hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOACTIVATE | SWP_HIDEWINDOW | SWP_NOOWNERZORDER | SWP_NOZORDER,
        )
        self.window.withdraw()
        self.visible = False

    def destroy(self) -> None:
        self.window.destroy()

    def _configure_window_style(self) -> None:
        get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_window_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        ex_style = get_window_long(self.hwnd, GWL_EXSTYLE)
        ex_style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        set_window_long(self.hwnd, GWL_EXSTYLE, ex_style)

    def _apply_blur(self) -> None:
        accent = ACCENT_POLICY(
            AccentState=ACCENT_ENABLE_ACRYLICBLURBEHIND,
            AccentFlags=2,
            GradientColor=_rgba_to_abgr(220, 12, 12, 12),
            AnimationId=0,
        )
        data = WINDOWCOMPOSITIONATTRIBDATA(
            Attribute=WCA_ACCENT_POLICY,
            Data=c_void_p.from_buffer(pointer(accent)),
            SizeOfData=sizeof(accent),
        )

        if not getattr(user32, "SetWindowCompositionAttribute", None):
            accent.AccentState = ACCENT_ENABLE_BLURBEHIND
            return

        user32.SetWindowCompositionAttribute(self.hwnd, byref(data))


class OverlayManager:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.enabled = True
        self.overlays: dict[int, WindowOverlay] = {}

    def sync_targets(self, targets: dict[int, str]) -> None:
        current = set(self.overlays)
        requested = set(targets)

        for hwnd in current - requested:
            self.remove_target(hwnd)

        for hwnd in requested - current:
            self.overlays[hwnd] = WindowOverlay(self.root, hwnd, targets[hwnd])

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            for overlay in self.overlays.values():
                overlay.hide()

    def toggle(self) -> bool:
        self.set_enabled(not self.enabled)
        return self.enabled

    def update(self) -> list[int]:
        stale: list[int] = []
        foreground = windows.get_foreground_window()

        for hwnd, overlay in list(self.overlays.items()):
            if not windows.is_window(hwnd):
                stale.append(hwnd)
                overlay.destroy()
                self.overlays.pop(hwnd, None)
                continue

            if not self.enabled or not windows.is_window_visible(hwnd) or windows.is_window_minimized(hwnd):
                overlay.hide()
                continue

            rect = windows.get_window_rect(hwnd)
            if rect is None:
                overlay.hide()
                continue

            if foreground == hwnd:
                overlay.hide()
                continue

            overlay.show_over(rect)

        return stale

    def remove_target(self, hwnd: int) -> None:
        overlay = self.overlays.pop(hwnd, None)
        if overlay is not None:
            overlay.destroy()

    def clear(self) -> None:
        for hwnd in list(self.overlays):
            self.remove_target(hwnd)


def _rgba_to_abgr(alpha: int, red: int, green: int, blue: int) -> int:
    return ((alpha & 0xFF) << 24) | ((blue & 0xFF) << 16) | ((green & 0xFF) << 8) | (red & 0xFF)
