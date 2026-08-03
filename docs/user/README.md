# Photo Intelligence — User Guide

Photo Intelligence is a local AI photo library manager. Everything — your
photos, the database, and AI analysis — stays on your machine; nothing is
uploaded anywhere. v1 runs on Windows only.

## Installing

Run the installer produced by `packaging/inno/core.iss`
(`PhotoIntelligenceSetup-<version>.exe`). It installs the app, adds a Start
Menu entry, and optionally a desktop icon. No separate Python install is
needed — the installer bundles everything the app needs to run.

[ExifTool](https://exiftool.org/) is required for reading photo metadata.
The current build expects it on `PATH`; bundling it into the installer is
tracked as a known gap (see the Limitations section below).

## First run

On first launch, the onboarding wizard asks you to pick one or more library
roots (folders containing your photos). Scanning starts immediately in the
background; you can browse and search photos as they're indexed rather than
waiting for the scan to finish. AI models (captioning, tagging, embeddings)
download in the background the first time each capability is enabled —
nothing blocks on a model download unless you're actively using that
capability.

## Features

- **Browse** — a virtualized photo grid (fast even with a large library) and
  a detail view per photo with metadata and AI results.
- **Search** — natural-language search (CLIP text encoder), similar-image
  search from a reference photo, and metadata filters (date range, camera,
  rating, GPS bounding box). Results combine ranking across text/semantic
  matches when more than one mode applies.
- **Smart filters** — one-click built-in filters for screenshots, blurry
  photos, duplicates, and photos already in a duplicate group.
- **Collections** — manual collections plus rule-based smart collections
  that auto-update as your library changes.
- **Duplicate review** — review detected duplicate groups, see the
  recommended keeper (highest resolution, then earliest capture time), and
  act on the group via a collection or export. v1 does not delete files.
- **Batch operations** — multi-select photos to add to a collection, export
  XMP sidecars, or copy to a folder. All additive: v1 never modifies or
  deletes an original file.
- **XMP export** — write ratings/tags/captions as XMP sidecars, either with
  the default preset or a Lightroom-compatible keyword hierarchy, without
  ever touching the original photo file.
- **Problems view** — failed AI analysis jobs are grouped by error reason
  with retry and ignore actions, instead of silently disappearing.
- **Plugin management** — see which AI capabilities (captioning, tagging,
  embeddings, quality, duplicate detection) are available and enable/disable
  them.
- **Diagnostics bundle** — from Settings, generate a zip of logs, redacted
  config, versions, and capability status to attach to a bug report. File
  paths are included only if you explicitly opt in, since paths are
  personal data.

## Settings

Settings resolve in layers: built-in default < `config.toml` < environment
variable < explicit override. Available from the Settings page: library
roots, GPU execution provider override (CUDA → DirectML → CPU is the
default auto-selection), thumbnail cache cap, and the diagnostics bundle
action described above.

## Limitations (v1)

These are deliberate v1 scope decisions (see the SDD's MVP Scope Overlay),
not bugs:

- **Windows only.** Cross-platform packaging is planned for v1.1.
- **No delete/trash integration.** Nothing in v1 removes an original file;
  file deletion, undo, and a recycle-bin integration are v2 work.
- **No OCR.** Text-in-photo search (e.g. finding receipts by their printed
  text) is deferred to v1.1.
- **No connectors.** Syncing with Immich, PhotoPrism, digiKam, or Lightroom
  is v1.1/v2 work; XMP export is v1's interoperability path today.
- **No live filesystem watching.** New/changed photos are picked up by an
  on-demand or on-startup rescan, not instantly as files change on disk.
- **Captioning runs on CPU only** and is intentionally opt-in — it's the
  slowest of the AI capabilities per photo.
