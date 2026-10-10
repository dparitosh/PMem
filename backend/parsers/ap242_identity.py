"""AP242 representation identification shared by parser consumers."""


def is_ap242(file_schema: str | None, namespace: str | None, content: bytes) -> bool:
    # Parser metadata identifies the representation; comments and labels do not.
    marker = (file_schema or "").lower() + " " + (namespace or "").lower()
    return any(value in marker for value in ("ap242", "managed_model_based_3d_engineering", "10303/-4442"))
