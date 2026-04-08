from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from blur_desktop_apps.hotkeys import GlobalHotkeyManager, MOD_ALT, MOD_CONTROL
from blur_desktop_apps.overlay import OverlayManager
from blur_desktop_apps.windows import (
    activate_window,
    WindowInfo,
    get_foreground_window,
    get_window_info,
    get_window_title,
    list_visible_windows,
    set_dpi_awareness,
)


APP_BG = "#edf2f7"
HEADER_BG = "#0f172a"
HEADER_ACCENT = "#38bdf8"
CARD_BG = "#ffffff"
CARD_BORDER = "#d7dee8"
TEXT_PRIMARY = "#0f172a"
TEXT_SECONDARY = "#52606d"
TEXT_MUTED = "#728197"
ACCENT = "#0f766e"
ACCENT_HOVER = "#115e59"
ACCENT_LIGHT = "#dff6f3"
WARNING = "#b45309"
WARNING_LIGHT = "#fff4d6"
STATUS_BLUE = "#1d4ed8"
STATUS_BLUE_LIGHT = "#dbeafe"
SUCCESS = "#047857"
SUCCESS_LIGHT = "#d1fae5"
OFF_TEXT = "#9a3412"
OFF_LIGHT = "#ffedd5"
BUTTON_TEXT = "#ffffff"
LIST_SELECT = "#0f766e"
LIST_SELECT_TEXT = "#ffffff"
SURFACE_SOFT = "#f8fafc"


class BlurDesktopApp:
    def __init__(self) -> None:
        set_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("Blur Desktop Apps")
        self.root.geometry("1160x760")
        self.root.minsize(1080, 680)
        self.root.configure(bg=APP_BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.update_idletasks()
        self.root_hwnd = self._get_tk_frame_handle(self.root)

        self.available_windows: list[WindowInfo] = []
        self.protected_windows: dict[int, WindowInfo] = {}
        self.overlay_manager = OverlayManager(self.root, on_reveal_requested=self.reveal_window_from_overlay)
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

        self.blur_strength_var = tk.IntVar(value=60)
        self.status_var = tk.StringVar(value="Choose the windows you want to protect.")
        self.privacy_var = tk.StringVar(value="Privacy mode is ON")
        self.blur_strength_label_var = tk.StringVar(value="Blur degree: 60%")
        self.hotkeys_var = tk.StringVar(
            value="Shortcuts: Ctrl+Alt+S protect active app, Ctrl+Alt+B toggle blur, Ctrl+Alt+P hide panel"
        )
        self.available_count_var = tk.StringVar(value="0 open apps")
        self.protected_count_var = tk.StringVar(value="0 protected")

        self.style = ttk.Style()
        self._configure_styles()

        self.available_list = self._create_listbox(self.root)
        self.protected_list = self._create_listbox(self.root)
        self.privacy_badge: tk.Label | None = None
        self.status_badge: tk.Label | None = None

        self._build_layout()
        self.overlay_manager.set_blur_strength(self.blur_strength_var.get())
        self._update_privacy_indicator(self.overlay_manager.enabled)
        self.refresh_window_list()
        self.hotkeys.start()
        self.root.after(self.poll_interval_ms, self.poll_overlays)
        self.root.after(120, self.poll_hotkeys)
        self.root.after(400, self._update_hotkey_status)
        self.root.after(self.list_refresh_interval_ms, self.auto_refresh_window_list)

    def run(self) -> None:
        self.root.mainloop()

    def _configure_styles(self) -> None:
        self.style.theme_use("clam")
        self.style.configure("App.TFrame", background=APP_BG)
        self.style.configure("Surface.TFrame", background=CARD_BG)
        self.style.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 13, "bold"))
        self.style.configure("CardBody.TLabel", background=CARD_BG, foreground=TEXT_SECONDARY, font=("Segoe UI", 10))
        self.style.configure("CardHint.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        self.style.configure("SectionValue.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))
        self.style.configure("SliderHint.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        self.style.configure("StatusText.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=("Segoe UI", 11))
        self.style.configure("StatusSubtle.TLabel", background=CARD_BG, foreground=TEXT_SECONDARY, font=("Segoe UI", 10))
        self.style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground=BUTTON_TEXT,
            borderwidth=0,
            focusthickness=0,
            focuscolor=ACCENT,
            font=("Segoe UI", 10, "bold"),
            padding=(14, 10),
        )
        self.style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)])
        self.style.configure(
            "Soft.TButton",
            background="#ffffff",
            foreground=TEXT_PRIMARY,
            borderwidth=1,
            relief="solid",
            focusthickness=0,
            padding=(12, 10),
            font=("Segoe UI", 10, "bold"),
        )
        self.style.map("Soft.TButton", background=[("active", SURFACE_SOFT), ("pressed", SURFACE_SOFT)])
        self.style.configure(
            "Warn.TButton",
            background="#ffffff",
            foreground=WARNING,
            borderwidth=1,
            relief="solid",
            focusthickness=0,
            padding=(12, 10),
            font=("Segoe UI", 10, "bold"),
        )
        self.style.map("Warn.TButton", background=[("active", WARNING_LIGHT), ("pressed", WARNING_LIGHT)])

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = tk.Frame(self.root, bg=HEADER_BG, padx=28, pady=22)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        title_block = tk.Frame(header, bg=HEADER_BG)
        title_block.grid(row=0, column=0, sticky="w")

        tk.Label(
            title_block,
            text="Blur Desktop Apps",
            bg=HEADER_BG,
            fg="#f8fafc",
            font=("Segoe UI", 22, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            title_block,
            text="Professional privacy control for the exact windows you choose.",
            bg=HEADER_BG,
            fg="#cbd5e1",
            font=("Segoe UI", 11),
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        header_meta = tk.Frame(header, bg=HEADER_BG)
        header_meta.grid(row=0, column=1, sticky="e")

        self.privacy_badge = tk.Label(
            header_meta,
            text=self.privacy_var.get(),
            bg=SUCCESS_LIGHT,
            fg=SUCCESS,
            padx=14,
            pady=7,
            font=("Segoe UI", 10, "bold"),
        )
        self.privacy_badge.grid(row=0, column=0, sticky="e")
        tk.Label(
            header_meta,
            textvariable=self.hotkeys_var,
            bg=HEADER_BG,
            fg=HEADER_ACCENT,
            font=("Segoe UI", 10, "bold"),
            anchor="e",
            justify="right",
        ).grid(row=1, column=0, sticky="e", pady=(10, 0))

        body = ttk.Frame(self.root, style="App.TFrame", padding=(24, 22, 24, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=0)

        available_card = self._create_card(body)
        available_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        available_card.columnconfigure(0, weight=1)
        available_card.rowconfigure(1, weight=1)
        self._build_window_card(
            card=available_card,
            title="Open Windows",
            subtitle="Choose any window on your desktop that should be protected.",
            count_var=self.available_count_var,
            listbox=self.available_list,
            on_double_click=self.add_selected_windows,
            tip_text="Double-click an item to add it to the protected list.",
        )

        controls_card = self._create_card(body, width=288)
        controls_card.grid(row=0, column=1, sticky="ns", padx=12)
        controls_card.grid_propagate(False)
        controls_card.columnconfigure(0, weight=1)
        self._build_controls_card(controls_card)

        protected_card = self._create_card(body)
        protected_card.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        protected_card.columnconfigure(0, weight=1)
        protected_card.rowconfigure(1, weight=1)
        self._build_window_card(
            card=protected_card,
            title="Protected Windows",
            subtitle="These windows receive the privacy overlay whenever they move to the background.",
            count_var=self.protected_count_var,
            listbox=self.protected_list,
            on_double_click=self.remove_selected_windows,
            tip_text="Double-click an item to remove it from protection.",
        )

        footer = self._create_card(body, padding=18)
        footer.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        footer.columnconfigure(1, weight=1)

        self.status_badge = tk.Label(
            footer,
            text="Status",
            bg=STATUS_BLUE_LIGHT,
            fg=STATUS_BLUE,
            padx=12,
            pady=7,
            font=("Segoe UI", 10, "bold"),
        )
        self.status_badge.grid(row=0, column=0, sticky="w", padx=(0, 14))

        ttk.Label(footer, textvariable=self.status_var, style="StatusText.TLabel", wraplength=760, justify="left").grid(
            row=0,
            column=1,
            sticky="w",
        )
        ttk.Label(
            footer,
            text="Tip: click a blurred cover to reveal that app, then click another app to blur it again.",
            style="StatusSubtle.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))

    def _build_window_card(
        self,
        *,
        card: tk.Frame,
        title: str,
        subtitle: str,
        count_var: tk.StringVar,
        listbox: tk.Listbox,
        on_double_click,
        tip_text: str,
    ) -> None:
        header = tk.Frame(card, bg=CARD_BG)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self._create_chip(header, count_var).grid(row=0, column=1, sticky="e")
        ttk.Label(header, text=subtitle, style="CardBody.TLabel", wraplength=320, justify="left").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )

        list_shell = tk.Frame(card, bg=SURFACE_SOFT, highlightbackground=CARD_BORDER, highlightthickness=1, bd=0)
        list_shell.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        list_shell.columnconfigure(0, weight=1)
        list_shell.rowconfigure(0, weight=1)

        scroll = ttk.Scrollbar(list_shell, orient="vertical", command=listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(in_=list_shell, row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        listbox.bind("<Double-Button-1>", lambda _event: on_double_click())

        ttk.Label(card, text=tip_text, style="CardHint.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 0))

    def _build_controls_card(self, card: tk.Frame) -> None:
        ttk.Label(card, text="Quick Actions", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            text="Control how protection behaves without digging through menus.",
            style="CardBody.TLabel",
            wraplength=228,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        ttk.Button(card, text="Pick Active App", style="Accent.TButton", command=self.pick_foreground_window).grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(18, 10),
        )
        ttk.Button(card, text="Add Selected", style="Soft.TButton", command=self.add_selected_windows).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=6,
        )
        ttk.Button(card, text="Remove Selected", style="Soft.TButton", command=self.remove_selected_windows).grid(
            row=4,
            column=0,
            sticky="ew",
            pady=6,
        )

        divider = ttk.Separator(card, orient="horizontal")
        divider.grid(row=5, column=0, sticky="ew", pady=18)

        ttk.Label(card, text="Blur Control", style="CardTitle.TLabel").grid(row=6, column=0, sticky="w")
        ttk.Label(card, textvariable=self.blur_strength_label_var, style="SectionValue.TLabel").grid(
            row=7,
            column=0,
            sticky="w",
            pady=(10, 4),
        )

        slider_frame = tk.Frame(card, bg=CARD_BG)
        slider_frame.grid(row=8, column=0, sticky="ew", pady=(0, 6))
        slider_frame.columnconfigure(0, weight=1)

        blur_scale = tk.Scale(
            slider_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.blur_strength_var,
            command=self.on_blur_strength_changed,
            length=232,
            resolution=1,
            showvalue=True,
            sliderlength=24,
            width=18,
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            troughcolor="#d7dee8",
            activebackground=ACCENT,
            font=("Segoe UI", 9),
        )
        blur_scale.grid(row=0, column=0, sticky="ew")

        ttk.Label(card, text="0 = clear, 100 = very dark", style="SliderHint.TLabel").grid(
            row=9,
            column=0,
            sticky="w",
            pady=(0, 14),
        )

        ttk.Button(card, text="Enable Blur", style="Accent.TButton", command=lambda: self.set_privacy_mode(True)).grid(
            row=10,
            column=0,
            sticky="ew",
            pady=6,
        )
        ttk.Button(card, text="Disable Blur", style="Warn.TButton", command=lambda: self.set_privacy_mode(False)).grid(
            row=11,
            column=0,
            sticky="ew",
            pady=6,
        )
        ttk.Button(card, text="Refresh Windows", style="Soft.TButton", command=self.refresh_window_list).grid(
            row=12,
            column=0,
            sticky="ew",
            pady=(6, 18),
        )

        shortcuts_box = tk.Frame(card, bg=SURFACE_SOFT, highlightbackground=CARD_BORDER, highlightthickness=1, bd=0, padx=12, pady=12)
        shortcuts_box.grid(row=13, column=0, sticky="ew")
        ttk.Label(shortcuts_box, text="Keyboard Shortcuts", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(shortcuts_box, text="Ctrl+Alt+S  Protect active app", style="CardHint.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 2))
        ttk.Label(shortcuts_box, text="Ctrl+Alt+B  Toggle privacy mode", style="CardHint.TLabel").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(shortcuts_box, text="Ctrl+Alt+P  Show or hide panel", style="CardHint.TLabel").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(shortcuts_box, text="Ctrl+Alt+R  Refresh open windows", style="CardHint.TLabel").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(shortcuts_box, text="Ctrl+Alt+Q  Quit the app", style="CardHint.TLabel").grid(row=5, column=0, sticky="w", pady=2)

        ttk.Button(card, text="Quit", style="Warn.TButton", command=self.on_close).grid(row=14, column=0, sticky="ew", pady=(18, 0))

    def _create_card(self, parent: tk.Misc, *, width: int | None = None, padding: int = 20) -> tk.Frame:
        card = tk.Frame(parent, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1, bd=0, padx=padding, pady=padding)
        if width is not None:
            card.configure(width=width)
        return card

    def _create_chip(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Label:
        return tk.Label(
            parent,
            textvariable=variable,
            bg=ACCENT_LIGHT,
            fg=ACCENT,
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
        )

    def _create_listbox(self, parent: tk.Misc) -> tk.Listbox:
        return tk.Listbox(
            parent,
            selectmode=tk.EXTENDED,
            exportselection=False,
            font=("Segoe UI", 11),
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            activestyle="none",
            bg=SURFACE_SOFT,
            fg=TEXT_PRIMARY,
            selectbackground=LIST_SELECT,
            selectforeground=LIST_SELECT_TEXT,
        )

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
        self.available_windows = list_visible_windows(excluded_hwnds={self.root_hwnd})
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
        self._update_counts()
        self.status_var.set(f"Found {len(self.available_windows)} open windows.")

    def add_selected_windows(self) -> None:
        selected_indexes = list(self.available_list.curselection())
        if not selected_indexes:
            self.status_var.set("Choose an app from Open Windows or use Pick Active App.")
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
        self._update_privacy_indicator(enabled)
        self.status_var.set("Protected windows are blurred in the background." if enabled else "Blur overlays are temporarily disabled.")

    def toggle_privacy_mode(self) -> None:
        enabled = self.overlay_manager.toggle()
        self.overlay_manager.update()
        self.privacy_var.set("Privacy mode is ON" if enabled else "Privacy mode is OFF")
        self._update_privacy_indicator(enabled)
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
            self._update_counts()
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
        if foreground and foreground != self.root_hwnd:
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

        if window.hwnd == self.root_hwnd:
            return None

        return window

    def on_blur_strength_changed(self, _value: str) -> None:
        strength = int(round(float(_value)))
        self.blur_strength_var.set(strength)
        self.blur_strength_label_var.set(f"Blur degree: {strength}%")
        self.overlay_manager.set_blur_strength(strength)
        self.overlay_manager.update()
        self.status_var.set(f"Blur degree updated to {strength}%.")

    def reveal_window_from_overlay(self, hwnd: int) -> None:
        info = self.protected_windows.get(hwnd)
        windows_title = info.display_name if info is not None else "the protected app"
        self.overlay_manager.reveal_temporarily(hwnd)
        activated = activate_window(hwnd)
        self.overlay_manager.update()
        if activated:
            self.status_var.set(f"Revealed {windows_title}. Click another app to blur it again.")
        else:
            self.status_var.set(f"Revealed {windows_title}. If it does not focus automatically, click inside it once.")

    def _update_counts(self) -> None:
        self.available_count_var.set(f"{len(self.available_windows)} open")
        self.protected_count_var.set(f"{len(self.protected_windows)} protected")

    def _update_privacy_indicator(self, enabled: bool) -> None:
        if self.privacy_badge is None:
            return
        if enabled:
            self.privacy_badge.configure(text="Privacy mode is ON", bg=SUCCESS_LIGHT, fg=SUCCESS)
        else:
            self.privacy_badge.configure(text="Privacy mode is OFF", bg=OFF_LIGHT, fg=OFF_TEXT)

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

    @staticmethod
    def _get_tk_frame_handle(window: tk.Misc) -> int:
        try:
            return int(str(window.frame()), 16)
        except (AttributeError, TypeError, ValueError):
            return int(window.winfo_id())
