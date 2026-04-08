from __future__ import annotations

import tkinter as tk
from ctypes import WINFUNCTYPE, Structure, byref, c_int, c_longlong, c_size_t, c_void_p, cast, pointer, sizeof
from ctypes.wintypes import DWORD, HWND, LPARAM, UINT, WPARAM
from typing import Callable

from blur_desktop_apps import windows


user32 = windows.user32


GWL_EXSTYLE = -20
GWLP_WNDPROC = -4
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080
SWP_NOOWNERZORDER = 0x0200
SWP_NOZORDER = 0x0004
WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1


WindowProc = WINFUNCTYPE(c_longlong, HWND, UINT, WPARAM, LPARAM)
user32.CallWindowProcW.argtypes = [c_void_p, HWND, UINT, WPARAM, LPARAM]
user32.CallWindowProcW.restype = c_longlong


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
    def __init__(
        self,
        root: tk.Tk,
        target_hwnd: int,
        title: str,
        blur_strength: int = 60,
        click_through: bool = False,
        on_reveal_requested: Callable[[int], None] | None = None,
    ) -> None:
        self.root = root
        self.target_hwnd = target_hwnd
        self.title = title
        self.visible = False
        self.blur_strength = _clamp_strength(blur_strength)
        self.click_through = click_through
        self.on_reveal_requested = on_reveal_requested
        self._original_wnd_proc: int | None = None
        self._subclass_wnd_proc: WindowProc | None = None

        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg="#101010")

        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)

        self.content = tk.Frame(self.window, bg="#101010")
        self.content.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

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

        self.center_title = tk.Label(
            self.content,
            text="Privacy Blur Enabled",
            bg="#101010",
            fg="#f5f5f5",
            font=("Segoe UI", 20, "bold"),
        )
        self.center_title.grid(row=0, column=0, pady=(42, 8))

        self.center_subtitle = tk.Label(
            self.content,
            text="Click anywhere on this cover to reveal the app.",
            bg="#101010",
            fg="#d6d6d6",
            font=("Segoe UI", 12),
        )
        self.center_subtitle.grid(row=1, column=0, sticky="n")

        self._bind_reveal_handlers()

        self.window.update_idletasks()
        self.hwnd = _get_tk_frame_handle(self.window)
        self._install_window_proc_hook()
        self._configure_window_style()
        self.set_click_through(self.click_through)
        self.set_blur_strength(self.blur_strength)

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
            self._get_insert_after_handle(),
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
        self._restore_window_proc_hook()
        self.window.destroy()

    def set_blur_strength(self, blur_strength: int) -> None:
        self.blur_strength = _clamp_strength(blur_strength)
        theme = _build_strength_theme(self.blur_strength)
        self.window.attributes("-alpha", theme.window_alpha)
        self.window.configure(bg=theme.background)
        self.content.configure(bg=theme.background)
        self.badge.configure(bg=theme.background)
        self.center_title.configure(bg=theme.background, fg=theme.title_color)
        self.center_subtitle.configure(bg=theme.background, fg=theme.subtitle_color)
        self._apply_blur(theme.accent_alpha, theme.accent_color)

    def set_click_through(self, click_through: bool) -> None:
        self.click_through = bool(click_through)
        self._configure_window_style()
        if self.click_through:
            self._unbind_reveal_handlers()
            self.center_subtitle.configure(text="Clicks pass through to the app while the blur stays on.")
            for widget in (self.window, self.content, self.badge, self.center_title, self.center_subtitle):
                widget.configure(cursor="arrow")
        else:
            self._bind_reveal_handlers()
            self.center_subtitle.configure(text="Click anywhere on this cover to reveal the app.")

    def _configure_window_style(self) -> None:
        get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_window_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        ex_style = get_window_long(self.hwnd, GWL_EXSTYLE)
        ex_style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        if self.click_through:
            ex_style |= WS_EX_TRANSPARENT
        else:
            ex_style &= ~WS_EX_TRANSPARENT
        set_window_long(self.hwnd, GWL_EXSTYLE, ex_style)
        user32.SetWindowPos(
            self.hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_FRAMECHANGED,
        )

    def _apply_blur(self, accent_alpha: int, accent_color: tuple[int, int, int]) -> None:
        accent = ACCENT_POLICY(
            AccentState=ACCENT_ENABLE_ACRYLICBLURBEHIND,
            AccentFlags=2,
            GradientColor=_rgba_to_abgr(accent_alpha, *accent_color),
            AnimationId=0,
        )
        data = WINDOWCOMPOSITIONATTRIBDATA(
            Attribute=WCA_ACCENT_POLICY,
            Data=cast(pointer(accent), c_void_p),
            SizeOfData=sizeof(accent),
        )

        if not getattr(user32, "SetWindowCompositionAttribute", None):
            return

        if not user32.SetWindowCompositionAttribute(self.hwnd, byref(data)):
            accent.AccentState = ACCENT_ENABLE_BLURBEHIND
            user32.SetWindowCompositionAttribute(self.hwnd, byref(data))

    def _install_window_proc_hook(self) -> None:
        get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_window_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        self._original_wnd_proc = int(get_window_long(self.hwnd, GWLP_WNDPROC))

        @WindowProc
        def subclass_wnd_proc(hwnd: HWND, msg: int, w_param: int, l_param: int) -> int:
            if msg == WM_NCHITTEST and self.click_through:
                return HTTRANSPARENT
            return int(user32.CallWindowProcW(self._original_wnd_proc, hwnd, msg, w_param, l_param))

        self._subclass_wnd_proc = subclass_wnd_proc
        set_window_long(self.hwnd, GWLP_WNDPROC, cast(self._subclass_wnd_proc, c_void_p).value)

    def _restore_window_proc_hook(self) -> None:
        if self._original_wnd_proc is None or not windows.is_window(self.hwnd):
            return

        set_window_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        set_window_long(self.hwnd, GWLP_WNDPROC, self._original_wnd_proc)
        self._original_wnd_proc = None
        self._subclass_wnd_proc = None

    def _bind_reveal_handlers(self) -> None:
        widgets = [self.window, self.content, self.badge, self.center_title, self.center_subtitle]
        for widget in widgets:
            widget.bind("<Button-1>", self._handle_click)
            widget.configure(cursor="hand2")

    def _unbind_reveal_handlers(self) -> None:
        for widget in (self.window, self.content, self.badge, self.center_title, self.center_subtitle):
            widget.unbind("<Button-1>")

    def _handle_click(self, _event: tk.Event) -> str | None:
        if self.on_reveal_requested is not None:
            self.on_reveal_requested(self.target_hwnd)
        return "break"

    def _get_insert_after_handle(self) -> HWND:
        window_above_target = windows.get_window_above(self.target_hwnd)
        if window_above_target == self.hwnd:
            window_above_target = windows.get_window_above(self.hwnd)
        if window_above_target:
            return HWND(window_above_target)
        return HWND(0)


class OverlayManager:
    def __init__(self, root: tk.Tk, on_reveal_requested: Callable[[int], None] | None = None) -> None:
        self.root = root
        self.enabled = True
        self.blur_strength = 60
        self.click_through_enabled = False
        self.target_titles: dict[int, str] = {}
        self.overlays: dict[int, WindowOverlay] = {}
        self.on_reveal_requested = on_reveal_requested
        self.temporarily_revealed_hwnd: int | None = None
        self.reveal_became_foreground = False

    def sync_targets(self, targets: dict[int, str]) -> None:
        current = set(self.target_titles)
        requested = set(targets)

        for hwnd in current - requested:
            self.remove_target(hwnd)

        for hwnd in requested:
            self.target_titles[hwnd] = targets[hwnd]

        for hwnd in requested - current:
            if windows.is_window(hwnd) and windows.is_window_visible(hwnd) and not windows.is_window_minimized(hwnd):
                self.overlays[hwnd] = self._create_overlay(hwnd, targets[hwnd])

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            for overlay in self.overlays.values():
                overlay.hide()

    def set_blur_strength(self, blur_strength: int) -> None:
        self.blur_strength = _clamp_strength(blur_strength)
        for overlay in self.overlays.values():
            overlay.set_blur_strength(self.blur_strength)

    def set_click_through(self, enabled: bool) -> None:
        self.click_through_enabled = bool(enabled)
        if self.click_through_enabled:
            self.temporarily_revealed_hwnd = None
            self.reveal_became_foreground = False
        for overlay in self.overlays.values():
            overlay.set_click_through(self.click_through_enabled)

    def reveal_temporarily(self, hwnd: int) -> None:
        if hwnd not in self.overlays:
            return
        self.temporarily_revealed_hwnd = hwnd
        self.reveal_became_foreground = False
        self.overlays[hwnd].hide()

    def toggle(self) -> bool:
        self.set_enabled(not self.enabled)
        return self.enabled

    def update(self) -> list[int]:
        stale: list[int] = []
        foreground = windows.get_foreground_window()

        if self.temporarily_revealed_hwnd is not None:
            if self.temporarily_revealed_hwnd not in self.target_titles:
                self.temporarily_revealed_hwnd = None
                self.reveal_became_foreground = False
            elif foreground == self.temporarily_revealed_hwnd:
                self.reveal_became_foreground = True
            elif self.reveal_became_foreground and foreground not in (0, self.temporarily_revealed_hwnd):
                self.temporarily_revealed_hwnd = None
                self.reveal_became_foreground = False

        for hwnd in list(self.target_titles):
            if not windows.is_window(hwnd):
                stale.append(hwnd)
                self.remove_target(hwnd)
                continue

            is_visible = windows.is_window_visible(hwnd)
            is_minimized = windows.is_window_minimized(hwnd)

            if self.temporarily_revealed_hwnd == hwnd and (not is_visible or is_minimized):
                self.temporarily_revealed_hwnd = None
                self.reveal_became_foreground = False

            if not self.enabled:
                overlay = self.overlays.get(hwnd)
                if overlay is not None:
                    overlay.hide()
                continue

            if not is_visible or is_minimized:
                self._destroy_overlay(hwnd)
                continue

            if self.temporarily_revealed_hwnd == hwnd:
                overlay = self.overlays.get(hwnd)
                if overlay is not None:
                    overlay.hide()
                continue

            if foreground == hwnd and not self.click_through_enabled:
                overlay = self.overlays.get(hwnd)
                if overlay is not None:
                    overlay.hide()
                continue

            overlay = self._ensure_overlay(hwnd)
            rect = windows.get_window_rect(hwnd)
            if rect is None:
                overlay.hide()
                continue

            overlay.show_over(rect)

        return stale

    def remove_target(self, hwnd: int) -> None:
        self._destroy_overlay(hwnd)
        self.target_titles.pop(hwnd, None)
        if self.temporarily_revealed_hwnd == hwnd:
            self.temporarily_revealed_hwnd = None
            self.reveal_became_foreground = False

    def clear(self) -> None:
        for hwnd in list(self.target_titles):
            self.remove_target(hwnd)

    def _create_overlay(self, hwnd: int, title: str) -> WindowOverlay:
        return WindowOverlay(
            self.root,
            hwnd,
            title,
            blur_strength=self.blur_strength,
            click_through=self.click_through_enabled,
            on_reveal_requested=self.on_reveal_requested,
        )

    def _ensure_overlay(self, hwnd: int) -> WindowOverlay:
        overlay = self.overlays.get(hwnd)
        if overlay is not None:
            return overlay

        overlay = self._create_overlay(hwnd, self.target_titles[hwnd])
        self.overlays[hwnd] = overlay
        return overlay

    def _destroy_overlay(self, hwnd: int) -> None:
        overlay = self.overlays.get(hwnd)
        if overlay is None:
            return

        overlay.destroy()
        self.overlays.pop(hwnd, None)


def _rgba_to_abgr(alpha: int, red: int, green: int, blue: int) -> int:
    return ((alpha & 0xFF) << 24) | ((blue & 0xFF) << 16) | ((green & 0xFF) << 8) | (red & 0xFF)


def _clamp_strength(blur_strength: int) -> int:
    return max(0, min(100, int(blur_strength)))


class _StrengthTheme:
    def __init__(
        self,
        *,
        window_alpha: float,
        accent_alpha: int,
        background: str,
        title_color: str,
        subtitle_color: str,
        accent_color: tuple[int, int, int],
    ) -> None:
        self.window_alpha = window_alpha
        self.accent_alpha = accent_alpha
        self.background = background
        self.title_color = title_color
        self.subtitle_color = subtitle_color
        self.accent_color = accent_color


def _build_strength_theme(blur_strength: int) -> _StrengthTheme:
    strength = _clamp_strength(blur_strength)
    ratio = strength / 100
    window_alpha = 0.01 + (ratio * 0.985)
    accent_alpha = int(ratio * 255)
    shade = int(84 - (ratio * 84))
    subtitle_shade = int(238 - (ratio * 120))
    background = f"#{shade:02x}{shade:02x}{shade:02x}"
    title_color = "#f5f5f5"
    subtitle_color = f"#{subtitle_shade:02x}{subtitle_shade:02x}{subtitle_shade:02x}"
    accent_color = (shade, shade, shade)
    return _StrengthTheme(
        window_alpha=window_alpha,
        accent_alpha=accent_alpha,
        background=background,
        title_color=title_color,
        subtitle_color=subtitle_color,
        accent_color=accent_color,
    )


def _get_tk_frame_handle(window: tk.Misc) -> int:
    try:
        return int(str(window.frame()), 16)
    except (AttributeError, TypeError, ValueError):
        return int(window.winfo_id())
