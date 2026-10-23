"""Bounded Office input and original current-file authority, without shell execution."""

import hashlib
import io
import zipfile
from xml.etree import ElementTree as ET

from deerflow.runtime import current_file_access

MAX_BYTES = 16 * 1024 * 1024


def check_office_package(data, main, content_type):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise ValueError("Office package size unavailable")
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        members = package.infolist()
        if len(members) > 512 or len({x.filename for x in members}) != len(members) or sum(x.file_size for x in members) > 32 * 1024 * 1024:
            raise ValueError("Office package size unavailable")
        parts = set()
        expected_type = False
        for member in members:
            name = member.filename
            if name.startswith("/") or ".." in name.split("/") or ":" in name or "\\" in name or name.lower().endswith((".bin", ".vba", ".exe")):
                raise ValueError("Office member unavailable")
            parts.add(name)
            if not name.lower().endswith((".xml", ".rels")):
                continue
            body = package.read(member)
            declarations = body.replace(b"\x00", b"").upper()
            if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
                raise ValueError("Office XML declarations unavailable")
            count = depth = 0
            for event, node in ET.iterparse(io.BytesIO(body), events=("start", "end")):
                if event == "start":
                    count += 1
                    depth += 1
                    if count > 100_000 or depth > 100:
                        raise ValueError("Office XML structure limit exceeded")
                    if node.get("TargetMode") == "External":
                        raise ValueError("External Office relationship unavailable")
                    if name == "[Content_Types].xml" and node.get("PartName") == "/" + main and node.get("ContentType") == content_type:
                        expected_type = True
                else:
                    depth -= 1
                    node.clear()
        if not expected_type or not {main, "[Content_Types].xml", "_rels/.rels"}.issubset(parts):
            raise ValueError("Office main document unavailable")


def owned_office_operation(runtime, action, extension, source_path, output_path, create, inspect, edit, *, source_extension=None):
    try:
        if action not in {"create", "inspect", "edit"}:
            raise ValueError("Office action unavailable")
        source = None
        if action != "create":
            if not source_path.lower().endswith(source_extension or extension):
                raise ValueError("Office source extension unavailable")
            source = current_file_access(runtime, "read_bytes", source_path)
            if source is None or len(source) > MAX_BYTES:
                raise PermissionError("Current source unavailable")
        if action == "inspect":
            result = inspect(source)
            current_file_access(runtime, "read_bytes", source_path)
            return {"status": "ok", "document": result}
        if not output_path.startswith("/mnt/user-data/outputs/") or not output_path.lower().endswith(extension) or output_path == source_path:
            raise ValueError("New owned output required")
        result = create() if action == "create" else edit(source)
        if not isinstance(result, bytes) or len(result) > MAX_BYTES:
            raise ValueError("Office output size unavailable")
        if source is not None:
            current_file_access(runtime, "read_bytes", source_path)
        if current_file_access(runtime, ("create", result), output_path) != "OK":
            raise PermissionError("Current output unavailable")
        current_file_access(runtime, "present", output_path)
        return {"status": "ok", "file": output_path, "sha256": hashlib.sha256(result).hexdigest(), "bytes": len(result)}
    except Exception:
        return {"status": "unavailable", "inspection_required": True, "retry": False}
