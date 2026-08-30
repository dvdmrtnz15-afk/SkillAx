#!/usr/bin/env python3
"""Core raster and hashing primitives for the GeoCanon reference runtime."""
from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

EXPECTED_STAGES = (
    "verify_inputs",
    "segment_subjects",
    "photometric_relight",
    "contact_shadow",
    "occlusion_repair",
    "composite",
    "evaluate_integrity",
)
OBSERVATION_GATES = {
    "G_LOCATION_IDENTITY",
    "G_RIGHTS",
    "G_SPATIAL",
    "G_VIEW_CONE",
    "G_TEMPORAL",
    "G_SUBJECT_CANON",
    "G_PROVENANCE",
}
ALLOWED_STATUSES = {"PASS", "FAIL", "UNKNOWN"}


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    channels: int
    pixels: tuple[int, ...]

    def __post_init__(self) -> None:
        expected = self.width * self.height * self.channels
        if self.width < 1 or self.height < 1:
            raise ValueError("Raster dimensions must be positive")
        if self.channels not in (1, 3):
            raise ValueError("Raster channels must be 1 or 3")
        if len(self.pixels) != expected:
            raise ValueError(f"Raster has {len(self.pixels)} samples; expected {expected}")
        if any(sample < 0 or sample > 255 for sample in self.pixels):
            raise ValueError("Raster sample outside 0..255")

    def sample(self, x: int, y: int, channel: int = 0) -> int:
        return self.pixels[(y * self.width + x) * self.channels + channel]

    def rgb(self, x: int, y: int) -> tuple[int, int, int]:
        if self.channels != 3:
            raise ValueError("rgb() requires a three-channel raster")
        i = (y * self.width + x) * 3
        return (self.pixels[i], self.pixels[i + 1], self.pixels[i + 2])


class RuntimeContractError(ValueError):
    """Raised when a runtime request violates a fail-closed invariant."""


def canonical_hash(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _tokenize_netpbm(data: bytes) -> list[str]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Reference runtime accepts ASCII Netpbm only") from exc
    tokens: list[str] = []
    for line in text.splitlines():
        tokens.extend(line.split("#", 1)[0].split())
    return tokens


def read_netpbm(path: Path) -> Raster:
    tokens = _tokenize_netpbm(path.read_bytes())
    if len(tokens) < 4:
        raise ValueError(f"Invalid Netpbm header: {path}")
    magic = tokens[0]
    if magic not in {"P2", "P3"}:
        raise ValueError(f"Unsupported Netpbm format {magic!r}: {path}")
    try:
        width = int(tokens[1])
        height = int(tokens[2])
        max_value = int(tokens[3])
        samples = tuple(int(token) for token in tokens[4:])
    except ValueError as exc:
        raise ValueError(f"Non-integer Netpbm token: {path}") from exc
    if max_value != 255:
        raise ValueError(f"Reference runtime requires max value 255: {path}")
    return Raster(width, height, 3 if magic == "P3" else 1, samples)


def netpbm_bytes(raster: Raster) -> bytes:
    magic = "P3" if raster.channels == 3 else "P2"
    lines = [magic, f"{raster.width} {raster.height}", "255"]
    row_width = raster.width * raster.channels
    for start in range(0, len(raster.pixels), row_width):
        lines.append(" ".join(str(value) for value in raster.pixels[start : start + row_width]))
    return ("\n".join(lines) + "\n").encode("ascii")


def write_netpbm(path: Path, raster: Raster) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(netpbm_bytes(raster))


def safe_asset_path(base_dir: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise RuntimeContractError("Asset path must be a non-empty string")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise RuntimeContractError(f"Unsafe asset path: {relative}")
    base = base_dir.resolve()
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise RuntimeContractError(f"Asset escapes request directory: {relative}") from exc
    return candidate


def artifact_raster(
    artifact: object,
    base_dir: Path,
    *,
    channels: int,
    label: str,
) -> tuple[Path, Raster]:
    if not isinstance(artifact, dict):
        raise RuntimeContractError(f"{label} must be an object")
    path = safe_asset_path(base_dir, artifact.get("path"))
    if not path.is_file():
        raise RuntimeContractError(f"{label} asset not found: {path}")
    if artifact.get("content_hash") != hash_file(path):
        raise RuntimeContractError(f"{label} content_hash mismatch")
    raster = read_netpbm(path)
    if raster.channels != channels:
        expected = "P3 RGB" if channels == 3 else "P2 grayscale"
        raise RuntimeContractError(f"{label} must be {expected}")
    if artifact.get("width_px") != raster.width or artifact.get("height_px") != raster.height:
        raise RuntimeContractError(f"{label} declared dimensions do not match asset")
    media = "image/x-portable-pixmap" if channels == 3 else "image/x-portable-graymap"
    if artifact.get("media_type") != media:
        raise RuntimeContractError(f"{label} media_type must be {media}")
    return path, raster


def number_triplet(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise RuntimeContractError(f"{label} must contain exactly three numbers")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise RuntimeContractError(f"{label} must contain numbers")
    numbers = tuple(float(item) for item in value)
    if any(not math.isfinite(item) for item in numbers):
        raise RuntimeContractError(f"{label} contains non-finite value")
    return numbers  # type: ignore[return-value]


def integer(value: object, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeContractError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise RuntimeContractError(f"{label} must be >= {minimum}")
    return value


def bounded_float(value: object, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeContractError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise RuntimeContractError(f"{label} must be in [{minimum}, {maximum}]")
    return result


def mask_fraction(mask: Raster) -> float:
    if mask.channels != 1:
        raise ValueError("Mask must be grayscale")
    return sum(1 for value in mask.pixels if value > 0) / len(mask.pixels)


def immutable_pixel_hash(raster: Raster, mutable_mask: Raster) -> str:
    if raster.channels != 3 or mutable_mask.channels != 1:
        raise ValueError("immutable_pixel_hash requires RGB raster and grayscale mask")
    if (raster.width, raster.height) != (mutable_mask.width, mutable_mask.height):
        raise ValueError("Raster/mask dimensions differ")
    h = hashlib.sha256()
    h.update(struct.pack(">II", raster.width, raster.height))
    for y in range(raster.height):
        for x in range(raster.width):
            if mutable_mask.sample(x, y) == 0:
                h.update(bytes(raster.rgb(x, y)))
    return h.hexdigest()
