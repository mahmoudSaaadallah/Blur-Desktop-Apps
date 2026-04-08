from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from blur_desktop_apps.hotkeys import GlobalHotkeyManager, MOD_ALT, MOD_CONTROL
from blur_desktop_apps.overlay import OverlayManager
from blur_desktop_apps.windows import (
    WindowInfo,
    get_foreground_window,
    get_window_info,
    get_window_title,
    list_visible_windows,
    set_dpi_awareness,
)


class BlurDesktopApp:
    def __init__(self) -> None:
        set_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("Blur Desktop Apps")
        self.root.geometry("980x560")
        self.root.minsize(920, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.available_windows: list[WindowInfo] = []
        self.protected_windows: dict[int, WindowInfo] = {}
        self.overlay_manager = OverlayManager(self.root)
        self.poll_interval_ms = 180
        self.list_refresh_interval_ms = 3000
        self.pending_foreground_pick = False
        self.hotkeys = GlobalHotkeyManager(
            {
                "toggle_privacy": (MOD_CONTROL | MOD_ALT, ord("B")),
                "toggle_panel": (MOD_CONTROL | MOD_ALT, ord("P")),
                "refresh_windows": (MOD_CONTROL | MOD_ALT, ord("R")),
                "protect_foreground": (MOD_CONTROL | MOD_ALT, ord("S")),
                "quit_app": (MOD_CONTROL | MOD_ALT, ord("Q")),
            }
        )

        self.available_list = tk.Listbox(self.root, selectmode=tk.EXTENDED, exportselection=False)
        self.protected_list = tk.Listbox(self.root, selectmode=tk.EXTENDED, exportselection=False)
        self.status_var = tk.StringVar(value="Choose the windows you want to protect.")
        self.privacy_var = tk.StringVar(value="Privacy mode is ON")
        self.hotkeys_var = tk.StringVar(
            value="Shortcuts: Ctrl+Alt+S protect active app, Ctrl+Alt+B toggle blur, Ctrl+Alt+P show or hide panel"
        )

        self._build_layout()
        self.refresh_window_list()
        self.hotkeys.start()
        self.root.after(self.poll_interval_ms, self.poll_overlays)
        self.root.after(120, self.poll_hotkeys)
        self.root.after(400, self._update_hotkey_status)
        self.root.after(self.list_refresh_interval_ms, self.auto_refresh_window_list)

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        title = ttk.Label(
            self.root,
            text="Select the apps you want this tool to protect",
            font=("Segoe UI", 16, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))

        body = ttk.Frame(self.root, padding=(24, 8, 24, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(1, weight=1)

        ttk.Label(body, text="Open windows").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Protected windows").grid(row=0, column=2, sticky="w")

        available_frame = ttk.Frame(body)
        available_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        available_frame.columnconfigure(0, weight=1)
        available_frame.rowconfigure(0, weight=1)

        protected_frame = ttk.Frame(body)
        protected_frame.grid(row=1, column=2, sticky="nsew", pady=(8, 0))
        protected_frame.columnconfigure(0, weight=1)
        protected_frame.rowconfigure(0, weight=1)

        available_scroll = ttk.Scrollbar(available_frame, orient="vertical", command=self.available_list.yview)
        available_scroll.grid(row=0, column=1, sticky="ns")
        self.available_list.configure(yscrollcommand=available_scroll.set, font=("Segoe UI", 11))
        self.available_list.grid(row=0, column=0, sticky="nsew")
        self.available_list.bind("<Double-Button-1>", lambda _event: self.add_selected_windows())

        protected_scroll = ttk.Scrollbar(protected_frame, orient="vertical", command=self.protected_list.yview)
        protected_scroll.grid(row=0, column=1, sticky="ns")
        self.protected_list.configure(yscrollcommand=protected_scroll.set, font=("Segoe UI", 11))
        self.protected_list.grid(row=0, column=0, sticky="nsew")
        self.protected_list.bind("<Double-Button-1>", lambda _event: self.remove_selected_windows())

        controls = ttk.Frame(body, padding=(18, 0))
        controls.grid(row=1, column=1, sticky="ns")

        ttk.Button(controls, text="Add ->", command=self.add_selected_windows).grid(row=0, column=0, sticky="ew", pady=(12, 8))
        ttk.Button(controls, text="<- Remove", command=self.remove_selected_windows).grid(row=1, column=0, sticky="ew", pady=8)
        ttk.Button(controls, text="Pick Active App", command=self.pick_foreground_window).grid(row=2, column=0, sticky="ew", pady=(24, 8))
        ttk.Button(controls, text="Enable Blur", command=lambda: self.set_privacy_mode(True)).grid(row=3, column=0, sticky="ew", pady=8)
        ttk.Button(controls, text="Disable Blur", command=lambda: self.set_privacy_mode(False)).grid(row=4, column=0, sticky="ew", pady=8)
        ttk.Button(controls, text="Refresh", command=self.refresh_window_list).grid(row=5, column=0, sticky="ew", pady=8)
        ttk.Button(controls, text="Quit", command=self.on_close).grid(row=6, column=0, sticky="ew", pady=(24, 0))

        help_text = (
            "Double-click a window to add or remove it.\n"
            "Or use Pick Active App, switch to the target app, and it will be added automatically."
        )
        ttk.Label(
            self.root,
            text=help_text,
            justify="left",
            foreground="#555555",
            padding=(24, 0, 24, 8),
        ).grid(row=2, column=0, sticky="w")

        ttk.Label(self.root, textvariable=self.hotkeys_var, padding=(24, 0, 24, 4), foreground="#5c2d91").grid(row=3, column=0, sticky="w")
        ttk.Label(self.root, textvariable=self.privacy_var, padding=(24, 0, 24, 0), foreground="#006a52").grid(row=4, column=0, sticky="w")
        ttk.Label(self.root, textvariable=self.status_var, padding=(24, 0, 24, 18), foreground="#0b5cad").grid(row=5, column=0, sticky="w")

    def refresh_window_list(self) -> None:
        current_selection = set(self.protected_windows)
        selected_available_hwnds = {
            self.available_windows[index].hwnd
            for index in self.available_list.curselection()
            if index < len(self.available_windows)
        }
        protected_values = list(self.protected_windows.values())
        selected_protected_hwnds = {
            protected_values[index].hwnd
            for index in self.protected_list.curselection()
            if index < len(protected_values)
        }
        self.root.update_idletasks()
        self.available_windows = list_visible_windows(excluded_hwnds={self.root.winfo_id()})
        self.available_windows = [window for window in self.available_windows if window.hwnd not in current_selection]
        self.available_list.delete(0, tk.END)
        for index, window in enumerate(self.available_windows):
            self.available_list.insert(tk.END, window.display_name)
            if window.hwnd in selected_available_hwnds:
                self.available_list.selection_set(index)
        self._refresh_protected_list()
        protected_after_refresh = list(self.protected_windows.values())
        for index, window in enumerate(protected_after_refresh):
            if window.hwnd in selected_protected_hwnds:
                self.protected_list.selection_set(index)
        self.status_var.set(f"Found {len(self.available_windows)} open windows.")

    def add_selected_windows(self) -> None:
        selected_indexes = list(self.available_list.curselection())
        if not selected_indexes:
            self.status_var.set("Choose an app from Open windows or use Pick Active App.")
            return

        for index in selected_indexes:
            window = self.available_windows[index]
            self.protected_windows[window.hwnd] = window
        self.overlay_manager.sync_targets({hwnd: info.display_name for hwnd, info in self.protected_windows.items()})
        self.overlay_manager.update()
        self.refresh_window_list()
        self.status_var.set(f"Selected {len(self.protected_windows)} windows for privacy protection.")

    def remove_selected_windows(self) -> None:
        indexes = list(self.protected_list.curselection())
        if not indexes:
            self.status_var.set("Choose a protected window to remove it from the list.")
            return

        protected = list(self.protected_windows.values())
        for index in reversed(indexes):
            window = protected[index]
            self.protected_windows.pop(window.hwnd, None)
            self.overlay_manager.remove_target(window.hwnd)
        self.refresh_window_list()
        self.status_var.set(f"Selected {len(self.protected_windows)} windows for privacy protection.")

    def set_privacy_mode(self, enabled: bool) -> None:
        self.overlay_manager.set_enabled(enabled)
        self.overlay_manager.update()
        self.privacy_var.set("Privacy mode is ON" if enabled else "Privacy mode is OFF")
        self.status_var.set("Protected windows are blurred in the background." if enabled else "Blur overlays are temporarily disabled.")

    def toggle_privacy_mode(self) -> None:
        enabled = self.overlay_manager.toggle()
        self.overlay_manager.update()
        self.privacy_var.set("Privacy mode is ON" if enabled else "Privacy mode is OFF")
        self.status_var.set("Protected windows are blurred in the background." if enabled else "Blur overlays are temporarily disabled.")

    def poll_hotkeys(self) -> None:
        for action in self.hotkeys.drain_events():
            if action == "toggle_privacy":
                self.toggle_privacy_mode()
            elif action == "toggle_panel":
                self.toggle_control_panel()
            elif action == "refresh_windows":
                self.refresh_window_list()
            elif action == "protect_foreground":
                self.add_current_foreground_window()
            elif action == "quit_app":
                self.on_close()
                return
        self.root.after(120, self.poll_hotkeys)

    def poll_overlays(self) -> None:
        stale_hwnds = self.overlay_manager.update()
        if stale_hwnds:
            for hwnd in stale_hwnds:
                self.protected_windows.pop(hwnd, None)
            self._refresh_protected_list()
            self.status_var.set("Closed windows were removed from the protected list.")
        self.root.after(self.poll_interval_ms, self.poll_overlays)

    def on_close(self) -> None:
        self.overlay_manager.clear()
        self.hotkeys.stop()
        self.root.destroy()

    def pick_foreground_window(self) -> None:
        if self.pending_foreground_pick:
            self.status_var.set("Foreground app picking is already waiting for your target app.")
            return

        self.pending_foreground_pick = True
        self.status_var.set("Switch to the app you want to protect. It will be captured in 3 seconds.")
        self.root.withdraw()
        self.root.after(3000, self._finish_foreground_pick)

    def add_current_foreground_window(self) -> None:
        window = self._get_current_foreground_window()
        if window is None:
            self.status_var.set("No selectable foreground app was found. Bring the target app to the front and try again.")
            return

        if window.hwnd in self.protected_windows:
            self.status_var.set(f"{window.display_name} is already protected.")
            return

        self.protected_windows[window.hwnd] = window
        self.overlay_manager.sync_targets({hwnd: info.display_name for hwnd, info in self.protected_windows.items()})
        self.overlay_manager.update()
        self.refresh_window_list()
        self.status_var.set(f"Added {window.display_name} to the protected list.")

    def _refresh_protected_list(self) -> None:
        self.protected_list.delete(0, tk.END)
        protected = sorted(self.protected_windows.values(), key=lambda item: item.display_name.lower())
        self.protected_windows = {window.hwnd: window for window in protected}
        for window in protected:
            self.protected_list.insert(tk.END, window.display_name)

    def toggle_control_panel(self) -> None:
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
            self.status_var.set("Control panel is visible.")
            return

        foreground = get_foreground_window()
        if foreground and foreground != self.root.winfo_id():
            title = get_window_title(foreground)
            if title:
                self.status_var.set(f"Control panel hidden while you work in {title}.")
        self.root.withdraw()

    def _update_hotkey_status(self) -> None:
        if not self.hotkeys.failed_actions:
            return

        failed = ", ".join(self._format_action_name(action) for action in self.hotkeys.failed_actions)
        self.status_var.set(f"Some shortcuts were not registered because they are already in use: {failed}.")

    def auto_refresh_window_list(self) -> None:
        if self.root.winfo_exists() and self.root.state() != "withdrawn" and not self.pending_foreground_pick:
            self.refresh_window_list()
        self.root.after(self.list_refresh_interval_ms, self.auto_refresh_window_list)

    def _finish_foreground_pick(self) -> None:
        self.pending_foreground_pick = False
        self.add_current_foreground_window()
        if self.root.winfo_exists():
            self.root.deiconify()
            self.root.lift()

    def _get_current_foreground_window(self) -> WindowInfo | None:
        hwnd = get_foreground_window()
        if not hwnd:
            return None

        window = get_window_info(hwnd)
        if window is None:
            return None

        if window.title == self.root.title():
            return None

        return window

    @staticmethod
    def _format_action_name(action: str) -> str:
        labels = {
            "protect_foreground": "Ctrl+Alt+S",
            "toggle_privacy": "Ctrl+Alt+B",
            "toggle_panel": "Ctrl+Alt+P",
            "refresh_windows": "Ctrl+Alt+R",
            "quit_app": "Ctrl+Alt+Q",
        }
        return labels.get(action, action)
