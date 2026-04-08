# Blur Desktop Apps

Windows-focused Python desktop utility for keeping selected app windows private on large screens.

This repository is being built around a simple workflow:

1. Pick the open windows you want to protect.
2. Keep working normally on your other apps.
3. Turn privacy mode on or off with shortcuts.

The app currently includes:

1. A Tk-based window picker so you can choose exactly which app windows should be protected.
2. Per-window privacy overlays that follow the selected app on screen.
3. Automatic unblur for the active protected window so you can still read and interact with it normally.
4. Global shortcuts so you can keep privacy mode under your fingers while coding.
5. Quick app picking from the current foreground window, so you can protect the app you are actively using.
6. Adjustable blur degree from `0%` up to `100% very dark`.
7. Click-to-reveal behavior so a blurred app can be temporarily uncovered with one click and blurred again when you move away.
8. Overlay z-order tracking so the privacy layer stays attached to its selected app instead of floating above unrelated windows.
9. A polished desktop-style control panel with clearer sections, counts, actions, and status feedback.
10. More reliable minimize-and-restore handling so protected windows keep their blur behavior after coming back.
11. Protected apps stay remembered while minimized, then receive a fresh blur layer when they return.
12. Optional click-through blur mode so you can interact with a protected app without uncovering it.

## Shortcuts

- `Ctrl+Alt+S`: protect the app that is currently active
- `Ctrl+Alt+B`: toggle privacy blur on and off
- `Ctrl+Alt+P`: show or hide the control panel
- `Ctrl+Alt+R`: refresh the list of open windows
- `Ctrl+Alt+Q`: quit the app

## Run

```powershell
python main.py
```
