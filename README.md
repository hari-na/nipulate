# nipulate

*The laptop is on the TV. The remote is already in your hand.*

Your phone becomes a remote for a Windows laptop: play, pause and skip from the couch, steer the cursor with a trackpad, and type with the phone's own keyboard. No app to install, just a QR code.

## Features

- **Media keys first:** big play/pause, next and previous buttons that work system-wide, including YouTube, Netflix and Spotify in Chrome or Edge. Volume up, down and mute, with the current level shown on the phone. Hold a volume button to keep going.
- **YouTube row:** back 10s, forward 10s, fullscreen, captions, next video and Esc, sent as YouTube's keyboard shortcuts.
- **Trackpad:** pointer acceleration (slow is precise, a flick crosses the screen), tap to click, two-finger tap to right-click, hold then move to drag, and two-finger scrolling in either direction.
- **Keyboard:** the phone's own keyboard, in any language, emoji included. A drawer has Esc, Tab, arrows, Enter, Backspace, the Windows key, Alt+Tab, copy, paste and close tab.
- **Lock the PC** from the phone, behind a confirm.
- **Nothing to pair:** any phone on your Wi-Fi opens the remote by scanning the QR code or typing the address.
- **Made for a dark room:** portrait, one-handed, dark theme, big targets.

## Requirements

- Windows 10 or 11
- [Python 3.10 or newer](https://www.python.org/downloads/)
- A phone on the same Wi-Fi network as the PC

## Install

```bat
git clone https://github.com/hari-na/nipulate.git
cd nipulate
scripts\setup.bat
```

`setup.bat` creates a Python environment, installs nipulate and offers to create a **nipulate** desktop shortcut.

## Use

1. Double-click the **nipulate** desktop shortcut. The server starts in the background, with no window to keep open, and the PC page opens with a big QR code. (Or run `scripts\run.bat` to run it in a console window with the log in front of you.)
2. The first time, Windows asks to let Python through the firewall. Allow it on **Private networks**.
3. Scan the QR code with your phone's camera to open the remote. Bookmark it or add it to the Home Screen for next time.
4. Control the PC from the couch. Several phones can be connected at once.
5. Press **Stop** on the PC page to shut nipulate down. Closing the page doesn't stop it; double-click the shortcut again to get the page back.

The PC page is always at `http://localhost:8787/pc` on the PC. When nipulate is started from the shortcut, its log is also written to `%APPDATA%\nipulate\nipulate.log`.

### Controls

| Gesture | Does |
|---|---|
| Tap the trackpad | Left click |
| Two-finger tap | Right click |
| Hold a finger still, then move | Drag (the trackpad turns amber while dragging) |
| Two fingers up or down | Scroll (sideways works too) |
| Hold volume or an arrow key | Repeats |

The YouTube row sends keystrokes to whatever window has focus, so click the video's browser tab first. The media and volume buttons work no matter what has focus.

Pointer speed and scroll direction ("natural" like a phone, or "traditional" like a mouse wheel) are in the settings button at the top right.

### Phone tips

- **iPhone:** for full screen, tap Share, then **Add to Home Screen**.
- **Android:** in Chrome, use **Add to Home screen** or **Install app**.
- Set the phone's auto-lock to a few minutes if you pause between episodes.

## Security

nipulate is open to every device on your Wi-Fi: there's no pairing, so anyone on the network who opens the address can control this PC's keyboard and mouse. It's meant for a **trusted home network**. Don't run it on public or shared Wi-Fi.

What it does protect against:

- **Other websites:** a web page can't drive nipulate, even one you open on the PC or the phone. The phone connection only accepts nipulate's own page (the Origin check), reached by an IP address or a local name, never through a public domain pointed at your PC (the Host check, which blocks DNS rebinding).
- The PC page, its QR code and Stop only answer the PC itself.
- Typed text is never logged, only how many characters were typed.
- nipulate can't run programs or commands, only press keys and move the mouse.

Keep in mind:

- Traffic between the phone and the PC isn't encrypted, so someone on the same Wi-Fi could watch what you type.
- Windows doesn't let injected input reach apps running as administrator, UAC prompts or the lock screen. Running nipulate as administrator reaches admin apps; UAC prompts and the lock screen need the PC's own keyboard.

## Troubleshooting

- **The phone can't load the page:** it must be on the same Wi-Fi as the PC (not a guest network), the PC's network profile must be **Private**, and Python must be allowed through the firewall (Windows Security, Firewall, Allow an app). If the PC has a VPN on, the address in the QR code may be the VPN's; turn the VPN off or use the PC's Wi-Fi address.
- **The YouTube buttons do nothing:** click the YouTube tab on the PC first (tap the trackpad over the video), so it has keyboard focus.
- **The pointer feels too slow or too fast:** change Pointer speed in the phone's settings. nipulate does its own acceleration and positions the cursor directly, so Windows' "Enhance pointer precision" and pointer speed settings don't affect it.
- **Clicks don't reach an app:** it's probably running as administrator (see Security).
- **Old buttons after an update:** close the phone tab or Home Screen app completely and reopen it.

## Command line

```
nipulate [--port 8787] [--fake] [-v] [--log PATH]
```

| Option | |
|---|---|
| `--port` | Port to serve on (default 8787, so it can run next to [seidr-pad](https://github.com/hari-na/seidr-pad) on 8777) |
| `--fake` | Don't send input to Windows; for trying the phone page safely, and on other systems |
| `-v` | Also log every click and key (never typed text) |
| `--log` | Write the log to a file instead of the console (the desktop shortcut uses `%APPDATA%\nipulate\nipulate.log`) |

## How it works

```
Phone browser (remote page: HTML/CSS/JS, no build step)
   |  WebSocket over Wi-Fi
nipulate server (Python, aiohttp)
   |  ctypes -> user32.SendInput / LockWorkStation
Windows
```

`SendInput` is the same path a USB mouse and keyboard take into Windows, so no driver is needed. The phone sends finger movement once per animation frame; the server applies its acceleration curve and moves the cursor to an exact pixel with an absolute move, which keeps Windows' own pointer acceleration from stacking on top. Text is typed as Unicode characters (`KEYEVENTF_UNICODE`), so any language works regardless of the PC's keyboard layout. The volume level comes from Windows' Core Audio API through [pycaw](https://github.com/AndreMiras/pycaw).

When a phone disconnects, loses focus or locks the PC, any held mouse button is released, so nothing stays stuck down.

### Project layout

```
nipulate/
  cli.py        command line entry point
  server.py     web server, phone and PC-page WebSockets
  hub.py        connected phones, input dispatch, logging
  input.py      input backends (SendInput and a fake one for testing)
  _win32.py     ctypes bindings for SendInput, the cursor and the volume
  pointer.py    pointer acceleration and scroll scaling
  protocol.py   message format and validation
  device.py     User-Agent to "iPhone Safari" style labels
  launcher.py   desktop shortcut: start the server in the background, open the PC page
  static/       phone remote and PC page
scripts/        Windows setup, run and shortcut scripts
tests/          pytest suite
```

## Development

```bat
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest
.venv\Scripts\ruff check .
```

`nipulate --fake` runs without touching the mouse or keyboard, and on any OS. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
