# Contributing

Thanks for helping. Bug reports, phone compatibility reports and pull requests are all welcome.

## Setup

```bat
git clone https://github.com/hari-na/nipulate.git
cd nipulate
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

On macOS or Linux, use `.venv/bin/...` instead. The server runs in `--fake` mode there, which is enough for work on the phone page, the PC page and the server logic.

## Running

```bat
.venv\Scripts
ipulate -v          :: real input (Windows)
.venv\Scripts
ipulate --fake -v   :: records input instead of sending it
```

Open `http://localhost:8787/pc` for the QR code and log, and open the phone page from a phone on the same Wi-Fi. A desktop browser works too: shrink the window to portrait phone size and open the address from the QR code (the part after `#k=` is the pairing key). `--config` points at a separate pairing file, so testing doesn't touch your real pairing.

## Checks

Run both before opening a pull request. CI runs them on Windows and Linux.

```bat
.venv\Scripts\pytest
.venv\Scriptsuff check .
```

## Guidelines

- **Keep the phone page dependency-free.** It's plain HTML, CSS and JavaScript served as-is. No build step.
- **Anything a phone sends is untrusted.** Validate it in `protocol.py`: clamp numbers, and add new keys as named actions in `KEYS`. Never accept raw virtual-key codes from the phone.
- **Nothing that runs programs or commands.** nipulate presses keys and moves the mouse, and that's the whole surface.
- **Never log typed text.** Log counts, not characters.
- **PC-only actions** (stop, reset pairing, anything showing the QR code) must use `_require_pc` in `server.py`.
- **Put phone-provided strings into pages with `textContent`,** never `innerHTML`.
- **Tests:** new server or hub behavior gets a test. `FakeBackend` stands in for Windows.
- **Testing real input:** check pointer movement with `GetCursorPos`, and test keys only against a page of your own that has focus.
- **Commits:** small and focused, with [Conventional Commits](https://www.conventionalcommits.org/) messages (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`).

## Reporting a bug

Please include the phone model and browser (or Home Screen app), Windows version, and the server log around the problem (`scriptsun.bat` shows it, as does the log on the PC page). The log never contains typed text or the pairing key, but don't include screenshots of the QR code.
