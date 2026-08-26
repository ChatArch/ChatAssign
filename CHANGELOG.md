# Changelog

## Unreleased

## 0.1.0 - 2026-08-26

### Added

- Promote the VoiceNote assignment prototype into an installable ChatAssign service package.
- Add confirmation-gated assignment APIs, ChatEvent voice/Zulip policy boundaries, ChatBoard task/run handoff, and static Web assets.
- Add `chatassign serve` for user-level service deployment from the published package.

### Changed

- Keep ChatAssign state under its ChatArch-owned home instead of the main Playground.

### Fixed

- Require explicit confirmation intent before creating ChatBoard tasks or starting runs.
