_heic_available: bool | None = None


def is_heic_supported() -> bool:
    """Detect pillow-heif availability at startup (ADR-0012: HEIC is optional).

    When available, registers it as a Pillow plugin so `Image.open()` -- and
    therefore `raster_thumbnail.generate_thumbnail` -- handles .heic/.heif
    transparently, with no HEIC-specific code path needed elsewhere.
    Callers use this to show the "HEIC support not installed" affordance
    (SDD §16.4) instead of failing a scan when it's absent.
    """
    global _heic_available
    if _heic_available is not None:
        return _heic_available

    try:
        import pillow_heif
    except ImportError:
        _heic_available = False
        return False

    pillow_heif.register_heif_opener()
    _heic_available = True
    return True
