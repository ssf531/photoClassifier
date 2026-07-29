# Local AI Photo Intelligence Platform

Version: 2.1 (scope tiering added by `Architecture_Audit_v1.md`; product intent unchanged from 2.0)

## Vision

Build a cross-platform, offline-first AI Photo Intelligence Platform
rather than a traditional photo manager.

The application should analyse, understand, organise and search large
photo libraries while integrating with existing photo ecosystems such as
Lightroom, Immich, PhotoPrism and digiKam.

The implementation should recommend the most appropriate technologies
and architecture instead of being constrained to a predefined stack.

------------------------------------------------------------------------

# Design Principles

-   Cross-platform compatibility.
-   Offline-first.
-   Local AI only.
-   Modular architecture.
-   Plugin-based AI pipeline.
-   Technology agnostic.
-   Maintainable and testable.
-   Existing photos remain in their original location.
-   Never modify original files without explicit user confirmation.

------------------------------------------------------------------------

# Release Scope

This document describes the full product vision. Features are tiered by
release so that scope is explicit rather than inferred.

**v1 — Local Windows desktop application.**

Library scanning; metadata extraction; thumbnails; CLIP embeddings; AI
captions; tags derived from embeddings; duplicate detection;
sharpness/blur scoring; metadata, keyword, semantic, natural-language and
similar-image search; virtual and smart collections; built-in smart
filters; duplicate and recommendation review; XMP sidecar export;
copy-to-folder export.

**v1.1** — Immich connector; OCR; scene classification; cross-platform
packaging; live directory watching.

**v2** — File operations (move, rename, delete, archive) with staged
confirmation and undo; third-party plugin support with process isolation;
PhotoPrism, digiKam and Lightroom connectors; inbound synchronisation;
aesthetic scoring; landmark recognition; colour analysis; the
Photographer AI Assistant.

**Future** — Cloud inference; distributed indexing; remote workers; NAS
deployment; web interface; mobile companion.

A feature's tier may be brought forward, but no feature may be added to
v1 without a corresponding removal.

------------------------------------------------------------------------

# Data Architecture

The application is an AI index, not a photo storage system.

## Original Photos

Photos remain on the file system.

The application stores references only.

## AI Database

The local database stores:

-   File index
-   EXIF/IPTC/XMP metadata
-   AI-generated captions
-   AI-generated tags
-   Scene classification
-   Landmark detection
-   OCR
-   Embeddings
-   Quality analysis
-   Aesthetic scores
-   User ratings
-   Collections
-   Processing history

The database must not store original images.

## Cache

The application may cache:

-   Thumbnails
-   Preview images
-   Temporary AI outputs

------------------------------------------------------------------------

# AI Analysis

Support pluggable providers for:

-   Embeddings — **v1**
-   Caption generation — **v1**
-   Tag generation — **v1** (derived from embeddings; a dedicated tagging
    model is not required — see ADR-0006)
-   Duplicate detection — **v1**
-   Technical quality: sharpness, exposure — **v1**
-   OCR — **v1.1**
-   Scene classification — **v1.1**
-   Landmark recognition — **v2**
-   Colour analysis — **v2**
-   Aesthetic scoring and photography analysis — **v2**

Multiple providers and versions should coexist in all tiers.

------------------------------------------------------------------------

# Metadata Strategy

Separate data into:

1.  Original Metadata
    -   EXIF
    -   IPTC
    -   Existing XMP
2.  AI Analysis
    -   Caption
    -   Tags
    -   Embeddings
    -   Scores
    -   Scene
    -   OCR
3.  User Metadata
    -   Rating
    -   Notes
    -   Collections
    -   Favourite
4.  Export Metadata

Support exporting selected information (caption, tags, rating, keywords)
to XMP sidecars without modifying original RAW files.

------------------------------------------------------------------------

# Integration

Support an export/synchronisation layer.

Potential connectors:

-   XMP
-   Immich
-   PhotoPrism
-   Lightroom
-   digiKam

The AI database remains the source of truth.

------------------------------------------------------------------------

# AI Pipeline

Scan Folder

→ Read Metadata

→ Generate Thumbnail

→ Execute Enabled AI Modules

→ Store AI Results

→ Update Search Index

Each module can be enabled or disabled independently.

------------------------------------------------------------------------

# Optional Photographer AI Assistant (v2)

Feature toggle. Deferred from v1 in full. The AI result schema stores
these outputs without modification when the capability arrives, so no
schema change is required to add it later.

Functions:

-   Composition analysis
-   Lighting analysis
-   Technical quality
-   Long exposure detection
-   Aesthetic scoring
-   Improvement suggestions
-   Best shot selection

------------------------------------------------------------------------

# Photo Curation

The application should help users organise photos after AI analysis.

The system must never automatically move, rename or delete files.

All operations require user confirmation.

## Smart Filters

Examples:

-   Screenshots
-   Receipts
-   Daily snapshots
-   Memes
-   Downloads
-   Low quality
-   Blurry
-   Similar
-   Burst photos

## Virtual Collections

Collections exist only inside the database.

Examples:

-   Portfolio
-   Travel
-   Wallpapers
-   Daily Photos
-   Archive Candidates
-   Instagram
-   Review Later

Adding a photo to a collection must not move the file.

## File Operations

**v1 performs no destructive file operations.** The application does not
move, rename, or delete original files in v1. The only filesystem writes
v1 performs are additive:

-   XMP sidecar files (new files beside originals; originals untouched)
-   Copying selected photos into a user-chosen folder (new files; sources
    untouched)

**v2 introduces** move, rename, archive, and optional delete, each
requiring two-stage explicit user confirmation (accept the suggested set,
then confirm the operation with exact source and destination paths shown)
and each reversible through a logged undo. Operations support batch
execution.

This constraint is permanent for v1, not a scheduling convenience: the
application's guarantee is that a user's original files are exactly where
the user left them. See ADR-0007.

## AI Recommendations

Examples:

-   These 326 photos appear to be daily snapshots.
-   These 91 images are screenshots.
-   These 44 images are nearly identical.

Users decide whether to apply the recommendations.

------------------------------------------------------------------------

# Search

Support:

-   Metadata search
-   Tag search
-   Semantic search
-   Similar image search
-   Natural language search

------------------------------------------------------------------------

# Deliverables

The implementation should recommend:

-   Technology stack
-   Application architecture
-   Database technology
-   Search engine
-   AI inference framework
-   Plugin architecture

Include justification and trade-offs for all major decisions.
