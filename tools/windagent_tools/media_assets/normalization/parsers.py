"""
Host-side, engine-free 3D asset parsers (VP3D Phase 7, Stage C).

Parses glTF (JSON), GLB (binary container) and OBJ into the neutral
``MeshSnapshot`` WITHOUT touching Blender. FBX/USD/BLEND are NOT parsed here —
they require a sandboxed Blender job (``AssetJobRunner``) and fail closed when
no job runner is available.

Security invariant: parsing is read-only; nothing is executed, no embedded
script/add-on is run (the static scan already rejected those payloads before
parse is reached).
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from typing import List, Optional

from windagent_core.domain.video_production.asset_normalization.enums import (
    AssetFormat,
    UnitSystem,
    UpAxis,
)
from windagent_core.domain.video_production.asset_normalization.errors import (
    MalformedAssetError,
    UnsupportedFormatError,
)

from windagent_tools.media_assets.normalization.snapshot import (
    AnimationRef,
    ArmatureRef,
    ImageRef,
    MaterialRef,
    MeshObject,
    MeshPart,
    MeshSnapshot,
)

GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = 0x4E4F534A  # b"JSON"
GLB_BIN_CHUNK = 0x004E4942  # b"BIN\0"

# Material extensions we understand. Anything else is flagged unsupported.
SUPPORTED_GLTF_MATERIAL_EXTENSIONS = (
    "KHR_materials_pbrSpecularGlossiness",
    "KHR_materials_emissive_strength",
    "KHR_materials_ior",
    "KHR_materials_transmission",
    "KHR_materials_sheen",
    "KHR_materials_clearcoat",
)

# MIME types we can normalize host-side (Pillow-capable).
SUPPORTED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}


def detect_format(data: bytes, declared_format: AssetFormat = AssetFormat.UNKNOWN) -> AssetFormat:
    """Detect the interchange format from magic bytes + declared hint."""
    if declared_format not in (AssetFormat.UNKNOWN,):
        return declared_format
    if data[:4] == GLB_MAGIC:
        return AssetFormat.GLB
    stripped = data.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        try:
            json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return AssetFormat.UNKNOWN
        return AssetFormat.GLTF
    if stripped.startswith(b"#") or b"v " in data[:4096]:
        return AssetFormat.OBJ
    return AssetFormat.UNKNOWN


def parse_asset(
    data: bytes,
    *,
    declared_format: AssetFormat = AssetFormat.UNKNOWN,
    base_dir: Optional[Path] = None,
) -> MeshSnapshot:
    fmt = detect_format(data, declared_format)
    if fmt is AssetFormat.GLB:
        return parse_glb(data, base_dir=base_dir)
    if fmt is AssetFormat.GLTF:
        return parse_gltf(data, base_dir=base_dir)
    if fmt is AssetFormat.OBJ:
        return parse_obj(data)
    raise UnsupportedFormatError(
        "asset format is not host-parseable (FBX/USD/BLEND require a sandboxed Blender job)",
        details={"detected": fmt.value},
    )


# ---------------------------------------------------------------------------
# glTF
# ---------------------------------------------------------------------------
def _image_bytes_from_uri(uri: str, base_dir: Optional[Path]) -> tuple[Optional[bytes], str]:
    """Resolve embedded (data:) or external texture bytes; never network."""
    if uri.startswith("data:"):
        try:
            header, payload = uri.split(",", 1)
            mime = header.split(";", 1)[0].replace("data:", "")
            if ";base64" in header:
                return base64.b64decode(payload), mime
            return payload.encode("utf-8"), mime
        except (ValueError, base64.binascii.Error) as exc:
            raise MalformedAssetError(f"malformed data URI in texture: {exc}") from exc
    if base_dir is not None:
        candidate = (base_dir / uri).resolve()
        if candidate.is_file():
            return candidate.read_bytes(), _mime_from_ext(candidate.suffix)
    return None, ""


def _mime_from_ext(ext: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext.lower(), "")


def parse_gltf(data: bytes, *, base_dir: Optional[Path] = None) -> MeshSnapshot:
    try:
        doc = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise MalformedAssetError(f"glTF JSON is invalid: {exc}") from exc
    if not isinstance(doc, dict) or "asset" not in doc:
        raise MalformedAssetError("glTF document is missing the asset header")

    meshes = doc.get("meshes") or []
    materials = doc.get("materials") or []
    images = doc.get("images") or []
    buffers = doc.get("buffers") or []
    buffer_views = doc.get("bufferViews") or []
    accessors = doc.get("accessors") or []
    skins = doc.get("skins") or []
    animations = doc.get("animations") or []
    nodes = doc.get("nodes") or []
    scenes = doc.get("scenes") or []

    images_by_index = {i: img for i, img in enumerate(images)}

    material_refs: List[MaterialRef] = []
    for mat in materials:
        name = str(mat.get("name", f"material_{len(material_refs)}"))
        pbr = mat.get("pbrMetallicRoughness") or {}
        used_ext = mat.get("extensions") or {}
        unsupported = next(
            (ext for ext in used_ext if ext not in SUPPORTED_GLTF_MATERIAL_EXTENSIONS),
            None,
        )
        if mat.get("extras", {}).get("windagent_normalized"):
            pass  # already normalized in a previous pass; recorded as-is

        def _tex(ref) -> Optional[str]:
            if not ref or "index" not in ref:
                return None
            return f"image_{ref['index']}"

        missing: List[str] = []
        for slot in ("baseColorTexture", "metallicRoughnessTexture", "normalTexture"):
            ref = pbr.get(slot) or mat.get(slot)
            if ref and "index" in ref:
                image = images_by_index.get(ref["index"])
                if image is None or (image.get("uri") or "").startswith("http"):
                    missing.append(slot)

        material_refs.append(
            MaterialRef(
                name=name,
                pbr=bool(pbr) or bool(unsupported),
                base_color_texture=_tex(pbr.get("baseColorTexture")),
                metallic_texture=_tex(pbr.get("metallicRoughnessTexture")),
                normal_texture=_tex(mat.get("normalTexture")),
                unsupported_extension=unsupported,
                missing_textures=missing,
            )
        )

    image_refs: List[ImageRef] = []
    for idx, image in enumerate(images):
        name = str(image.get("name", f"image_{idx}"))
        mime = str(image.get("mimeType", ""))
        uri = str(image.get("uri", ""))
        data_bytes, sniffed = _image_bytes_from_uri(uri, base_dir)
        if not data_bytes and "bufferView" in image:
            data_bytes = _extract_buffer_view(image["bufferView"], buffers, buffer_views)
        if not mime and sniffed:
            mime = sniffed
        image_refs.append(
            ImageRef(
                name=name,
                mime_type=mime,
                data=data_bytes,
                external_uri="" if data_bytes or uri.startswith("data:") else uri,
                color_space="sRGB",
            )
        )

    accessor_count = {i: (a.get("count", 0)) for i, a in enumerate(accessors)}
    objects: List[MeshObject] = []
    for mesh in meshes:
        name = str(mesh.get("name", f"mesh_{len(objects)}"))
        parts: List[MeshPart] = []
        for prim in mesh.get("primitives") or []:
            attributes = prim.get("attributes") or {}
            vertex_count = accessor_count.get(attributes.get("POSITION"), 0) if attributes.get("POSITION") is not None else 0
            indices = prim.get("indices")
            mode = int(prim.get("mode", 4))
            if indices is not None:
                indices_count = accessor_count.get(indices, 0)
                if mode == 4:
                    tri_count = indices_count // 3
                elif mode in (5, 6):  # strip/fan
                    tri_count = max(indices_count - 2, 0)
                else:
                    tri_count = 0
            else:
                tri_count = vertex_count // 3 if mode == 4 else 0
            parts.append(
                MeshPart(
                    name=f"{name}/prim_{len(parts)}",
                    triangle_count=tri_count,
                    vertex_count=vertex_count,
                    has_uv=bool(attributes.get("TEXCOORD_0") is not None),
                    has_normals=bool(attributes.get("NORMAL") is not None),
                    material_index=prim.get("material"),
                    mode=mode,
                )
            )
        objects.append(MeshObject(name=name, parts=parts))

    skin_nodes = {skin.get("skeleton") for skin in skins if skin.get("skeleton") is not None}
    for node_idx, node in enumerate(nodes):
        if node_idx in skin_nodes or node.get("skin") is not None:
            for obj in objects:
                if obj.name == str(node.get("name", "")) or len(objects) == 1:
                    obj = MeshObject(name=obj.name, parts=obj.parts, skinned=True)

    armatures = [ArmatureRef(name=str(skin.get("name", f"armature_{i}")), bones=len(skin.get("joints") or [])) for i, skin in enumerate(skins)]
    anims = [
        AnimationRef(name=str(anim.get("name", f"anim_{i}")), channels=len(anim.get("channels") or []))
        for i, anim in enumerate(animations)
    ]

    extras = doc.get("asset", {}).get("extras") or {}
    unit_hint = _unit_hint(extras)
    up_axis_hint = _up_axis_hint(extras)

    warnings: List[str] = []
    if not scenes and not nodes:
        warnings.append("glTF has no scene/nodes (geometry-only)")
    if not materials:
        warnings.append("glTF declares no materials (unshaded geometry)")

    return MeshSnapshot(
        format=AssetFormat.GLTF,
        objects=objects,
        materials=material_refs,
        images=image_refs,
        animations=anims,
        armatures=armatures,
        unit_hint=unit_hint,
        up_axis_hint=up_axis_hint,
        warnings=warnings,
    )


def _extract_buffer_view(view_index: int, buffers: list, buffer_views: list) -> Optional[bytes]:
    try:
        view = buffer_views[view_index]
        buffer = buffers[view["buffer"]]
        uri = buffer.get("uri", "")
        if uri.startswith("data:"):
            header, payload = uri.split(",", 1)
            raw = base64.b64decode(payload) if ";base64" in header else payload.encode("utf-8")
            offset = view.get("byteOffset", 0)
            length = view.get("byteLength", 0)
            return raw[offset : offset + length]
    except (IndexError, KeyError, ValueError, base64.binascii.Error):
        return None
    return None


def parse_glb(data: bytes, *, base_dir: Optional[Path] = None) -> MeshSnapshot:
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise MalformedAssetError("GLB magic header missing")
    try:
        version, total_length = struct.unpack_from("<II", data, 4)
    except struct.error as exc:
        raise MalformedAssetError(f"GLB header corrupt: {exc}") from exc
    if version != 2:
        raise MalformedAssetError(f"unsupported GLB version {version} (expected 2)")
    if total_length != len(data):
        raise MalformedAssetError(f"GLB length mismatch: header {total_length}, actual {len(data)}")

    json_data = b""
    offset = 12
    while offset < len(data) - 8:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + chunk_length > len(data):
            raise MalformedAssetError("GLB chunk overruns file")
        chunk = data[offset : offset + chunk_length]
        if chunk_type == GLB_JSON_CHUNK:
            json_data = chunk
            break
        offset += chunk_length
    if not json_data:
        raise MalformedAssetError("GLB contains no JSON chunk")

    # Re-scan for the BIN chunk to keep parsing self-contained.
    scan = 12
    bin_chunk = b""
    while scan < len(data) - 8:
        clen, ctype = struct.unpack_from("<II", data, scan)
        if ctype == GLB_BIN_CHUNK:
            bin_chunk = data[scan + 8 : scan + 8 + clen]
            break
        scan += 8 + clen

    snapshot = parse_gltf(json_data, base_dir=base_dir)
    # Patch embedded buffer images: GLB images reference bufferView into BIN.
    try:
        doc = json.loads(json_data.decode("utf-8"))
        images = doc.get("images") or []
        views = doc.get("bufferViews") or []
        new_images: List[ImageRef] = []
        for i, img in enumerate(images):
            existing = snapshot.images[i] if i < len(snapshot.images) else None
            if existing is None:
                break
            if existing.data is None and "bufferView" in img:
                try:
                    view = views[img["bufferView"]]
                    start = view.get("byteOffset", 0)
                    length = view.get("byteLength", 0)
                    new_images.append(
                        ImageRef(
                            name=existing.name,
                            mime_type=existing.mime_type or _mime_from_ext(".png"),
                            data=bin_chunk[start : start + length],
                            external_uri="",
                            color_space="sRGB",
                        )
                    )
                    continue
                except (IndexError, KeyError):
                    pass
            new_images.append(existing)
        snapshot = MeshSnapshot(
            format=snapshot.format,
            objects=snapshot.objects,
            materials=snapshot.materials,
            images=new_images,
            animations=snapshot.animations,
            armatures=snapshot.armatures,
            unit_hint=snapshot.unit_hint,
            up_axis_hint=snapshot.up_axis_hint,
            warnings=snapshot.warnings,
        )
    except (ValueError, KeyError):
        pass
    return snapshot


# ---------------------------------------------------------------------------
# OBJ
# ---------------------------------------------------------------------------
def parse_obj(data: bytes) -> MeshSnapshot:
    text = data.decode("utf-8", errors="replace")
    v_count = 0
    vt_count = 0
    vn_count = 0
    face_count = 0
    has_uv = False
    has_normals = False
    current_name = "obj"
    material_names: set[str] = set()
    objects: List[MeshObject] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        keyword = tokens[0]
        if keyword == "v":
            v_count += 1
        elif keyword == "vt":
            vt_count += 1
        elif keyword == "vn":
            vn_count += 1
        elif keyword == "f":
            face_count += 1
            for tok in tokens[1:]:
                comp = tok.split("/")
                if len(comp) > 1 and comp[1]:
                    has_uv = True
                if len(comp) > 2 and comp[2]:
                    has_normals = True
        elif keyword in ("o", "g"):
            current_name = tokens[1] if len(tokens) > 1 else current_name
        elif keyword == "usemtl" and len(tokens) > 1:
            material_names.add(tokens[1])

    part = MeshPart(
        name=current_name,
        triangle_count=face_count,
        vertex_count=v_count,
        has_uv=has_uv,
        has_normals=has_normals,
    )
    objects.append(MeshObject(name=current_name, parts=[part]))

    warnings: List[str] = []
    if not face_count:
        warnings.append("OBJ declares no faces")
    if vt_count and not has_uv:
        warnings.append("OBJ has vt data but faces use no UVs")
    if vn_count and not has_normals:
        warnings.append("OBJ has vn data but faces use no normals")

    return MeshSnapshot(
        format=AssetFormat.OBJ,
        objects=objects,
        materials=[
            MaterialRef(name=name, pbr=False, notes=["OBJ material (non-PBR by default)"])
            for name in sorted(material_names)
        ],
        unit_hint=UnitSystem.METERS,
        up_axis_hint=UpAxis.Z_UP,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# unit/axis hints
# ---------------------------------------------------------------------------
def _unit_hint(extras: dict) -> Optional[UnitSystem]:
    raw = str(extras.get("unit", "")).upper()
    try:
        return UnitSystem(raw)
    except ValueError:
        if extras.get("generator") and "blender" in str(extras.get("generator", "")).lower():
            return UnitSystem.METERS
        return None


def _up_axis_hint(extras: dict) -> Optional[UpAxis]:
    raw = str(extras.get("up_axis", "")).upper()
    try:
        return UpAxis(raw)
    except ValueError:
        if extras.get("generator") and "blender" in str(extras.get("generator", "")).lower():
            return UpAxis.Z_UP
        return None


__all__ = [
    "detect_format",
    "parse_asset",
    "parse_gltf",
    "parse_glb",
    "parse_obj",
]
