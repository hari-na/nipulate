# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The desktop shortcut runs the server in the background with no console window, so closing a window can't stop it by accident. Stop it from the PC page. The log goes to `%APPDATA%\nipulate\nipulate.log`, without the QR code.

### Added

- `--log PATH` writes the log to a file.

## [0.1.0] - 2026-10-02

First public version.

### Added

- Phone remote page, portrait and dark: media keys, volume with the current level, a YouTube shortcut row, browser back, a trackpad, the phone's keyboard and a special-keys drawer.
- Trackpad gestures: tap to click, two-finger tap to right-click, hold then move to drag, two-finger scroll with a natural or traditional direction, and a pointer speed setting.
- Server-side pointer acceleration with absolute cursor moves, so Windows' pointer settings don't stack on top.
- Unicode typing through `SendInput`, so any language and emoji work. Typed text is never logged.
- Pairing: a 128-bit key in the QR code's URL fragment, a 6-digit code for phones that can't use the link, per-device rate limiting, and Reset pairing.
- Lock the PC from the phone, behind a confirm.
- PC page with the QR code, pairing code, paired phones, live log, Stop and Reset pairing, reachable only from the PC itself.
- Reconnect handling: heartbeat, automatic reconnects, held buttons released on disconnect, and older tabs told to step aside.
- Windows setup script, run script, desktop shortcut and launcher.
