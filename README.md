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

## Shortcuts

- `Ctrl+Alt+B`: toggle privacy blur on and off
- `Ctrl+Alt+P`: show or hide the control panel
- `Ctrl+Alt+R`: refresh the list of open windows
- `Ctrl+Alt+Q`: quit the app

## Run

```powershell
python main.py
```
