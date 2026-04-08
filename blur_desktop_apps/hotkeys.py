from __future__ import annotations

import queue
import threading
from ctypes import byref, windll
from ctypes.wintypes import MSG


user32 = windll.user32
kernel32 = windll.kernel32


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class GlobalHotkeyManager:
    def __init__(self, bindings: dict[str, tuple[int, int]]) -> None:
        self.bindings = bindings
        self.events: queue.Queue[str] = queue.Queue()
        self.failed_actions: list[str] = []
        self._id_to_action: dict[int, str] = {}
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._message_loop, name="global-hotkeys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)

    def drain_events(self) -> list[str]:
        events: list[str] = []
        while True:
            try:
                events.append(self.events.get_nowait())
            except queue.Empty:
                return events

    def _message_loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        msg = MSG()
        user32.PeekMessageW(byref(msg), None, 0, 0, 0)

        for hotkey_id, (action, (modifiers, vk)) in enumerate(self.bindings.items(), start=1):
            if user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk):
                self._id_to_action[hotkey_id] = action
            else:
                self.failed_actions.append(action)

        try:
            while True:
                result = user32.GetMessageW(byref(msg), None, 0, 0)
                if result <= 0:
                    break
                if msg.message == WM_HOTKEY:
                    action = self._id_to_action.get(int(msg.wParam))
                    if action:
                        self.events.put(action)
        finally:
            for hotkey_id in list(self._id_to_action):
                user32.UnregisterHotKey(None, hotkey_id)
