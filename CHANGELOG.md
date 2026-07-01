# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-07-01

Initial release.

### Added
- btop-styled TUI: 24-bit truecolor, braille graphs, gradient meter bars,
  rounded boxes, diff-based rendering, painted canvas.
- Host overview: per-core CPU bars + total CPU graph, load average,
  RAM/SWAP meters and history (from `/proc`).
- Container table: live CPU%/MEM% gradient meters, memory, network rate,
  PIDs, per-row braille CPU-history sparkline; sorting and filtering.
- Detail panel: CPU/MEM/NET braille graphs for the selected container.
- Full-width live logs panel across the bottom, plus a large scrollable
  full log view with wrap toggle and horizontal scroll (`l`).
- Container management: start/stop/restart/pause/kill/remove (confirmations
  for destructive actions).
- Explore: shell into a container (`s`), filesystem browser (`f`), and a
  network view with ASCII topology + copy-paste Mermaid diagram (`n`).
- Six themes (btop, gruvbox, dracula, nord, tokyo-night, matrix); live
  cycling with `t`, `--theme`, `--list-themes`; persisted to
  `~/.config/dtop/config`.
- Wide-character/emoji-aware, tab-safe rendering with per-panel clipping.
- CLI: `--selftest`, `--version`, `--help`.
