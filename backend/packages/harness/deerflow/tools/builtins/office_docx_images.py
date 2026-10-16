"""Independent inline PNG/JPEG insertion using explicit owned image bytes."""

import hashlib
import io
import math
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps

from .office_docx import CT, REL, R, W, _package, _parts, _serialize, _text, _xml

WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
for prefix, namespace in [("wp", WP), ("a", A), ("pic", PIC)]:
    ET.register_namespace(prefix, namespace)


def _image(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 4 * 1024 * 1024:
        raise ValueError("Document image size unavailable")
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {"PNG", "JPEG"} or getattr(image, "n_frames", 1) != 1 or not 1 <= image.width <= 8192 or not 1 <= image.height <= 8192 or image.width * image.height > 16_000_000:
            raise ValueError("Static bounded PNG/JPEG required")
        image.load()
        oriented = ImageOps.exif_transpose(image)
        normalized = oriented.convert("RGBA" if oriented.mode in {"RGBA", "LA", "P"} else "RGB")
        normalized.info.clear()
        output = io.BytesIO()
        normalized.save(output, format="PNG")
        result = output.getvalue()
        if len(result) > 4 * 1024 * 1024:
            raise ValueError("Document normalized image size unavailable")
        return result, normalized.width, normalized.height


def add_docx_images(data, images):
    """Append bounded inline images before the final section; preserve other parts."""
    if not isinstance(images, list) or not 1 <= len(images) <= 16:
        raise ValueError("Document image list unavailable")
    parts = _parts(data)
    root = _xml(parts["word/document.xml"])
    body = root.find(f"{{{W}}}body")
    if body is None:
        raise ValueError("Document body unavailable")
    types = _xml(parts["[Content_Types].xml"])
    relname = "word/_rels/document.xml.rels"
    relationships = _xml(parts[relname]) if relname in parts else ET.Element(f"{{{REL}}}Relationships")
    ids = {node.get("Id") for node in relationships}
    doc_ids = {int(node.get("id")) for node in root.iter(f"{{{WP}}}docPr") if (node.get("id") or "").isdigit()}
    next_id = max(doc_ids, default=0) + 1
    if next_id + len(images) > 0xFFFFFFFF:
        raise ValueError("Document drawing identifiers unavailable")
    if not any(node.get("Extension", "").lower() == "png" for node in types):
        ET.SubElement(types, f"{{{CT}}}Default", Extension="png", ContentType="image/png")
    elif any(node.get("Extension", "").lower() == "png" and node.get("ContentType") != "image/png" for node in types):
        raise ValueError("Document PNG content type unavailable")
    total = 0
    for index, item in enumerate(images):
        if not isinstance(item, dict) or set(item) - {"data", "width_inches", "alt"} or "data" not in item:
            raise ValueError("Document image schema unavailable")
        image, width, height = _image(item["data"])
        total += len(image)
        if total > 8 * 1024 * 1024:
            raise ValueError("Document image total limit exceeded")
        inches = item.get("width_inches", 5.5)
        if type(inches) not in {int, float} or not math.isfinite(inches) or not 0.1 <= inches <= 6.2:
            raise ValueError("Document image width unavailable")
        cx, cy = round(inches * 914400), round(inches * height / width * 914400)
        if cy > 9 * 914400:
            raise ValueError("Document image height unavailable")
        alt = _text(item.get("alt", ""))
        if len(alt) > 2000:
            raise ValueError("Document image description unavailable")
        name = "prismos-" + hashlib.sha256(image).hexdigest() + ".png"
        partname = "word/media/" + name
        if partname in parts and parts[partname] != image:
            raise ValueError("Document image identity collision")
        parts[partname] = image
        rid = "prismosImage" + str(next_id + index)
        while rid in ids:
            rid += "x"
        ids.add(rid)
        ET.SubElement(relationships, f"{{{REL}}}Relationship", Id=rid, Type=R + "/image", Target="media/" + name)
        paragraph = ET.Element(f"{{{W}}}p")
        drawing = ET.SubElement(ET.SubElement(paragraph, f"{{{W}}}r"), f"{{{W}}}drawing")
        inline = ET.SubElement(drawing, f"{{{WP}}}inline", distT="0", distB="0", distL="0", distR="0")
        ET.SubElement(inline, f"{{{WP}}}extent", cx=str(cx), cy=str(cy))
        ET.SubElement(inline, f"{{{WP}}}docPr", id=str(next_id + index), name=name, descr=alt)
        ET.SubElement(ET.SubElement(inline, f"{{{WP}}}cNvGraphicFramePr"), f"{{{A}}}graphicFrameLocks", noChangeAspect="1")
        graphic_data = ET.SubElement(ET.SubElement(inline, f"{{{A}}}graphic"), f"{{{A}}}graphicData", uri=PIC)
        picture = ET.SubElement(graphic_data, f"{{{PIC}}}pic")
        properties = ET.SubElement(picture, f"{{{PIC}}}nvPicPr")
        ET.SubElement(properties, f"{{{PIC}}}cNvPr", id="0", name=name)
        ET.SubElement(properties, f"{{{PIC}}}cNvPicPr")
        fill = ET.SubElement(picture, f"{{{PIC}}}blipFill")
        ET.SubElement(fill, f"{{{A}}}blip", {f"{{{R}}}embed": rid})
        ET.SubElement(ET.SubElement(fill, f"{{{A}}}stretch"), f"{{{A}}}fillRect")
        shape = ET.SubElement(picture, f"{{{PIC}}}spPr")
        transform = ET.SubElement(shape, f"{{{A}}}xfrm")
        ET.SubElement(transform, f"{{{A}}}off", x="0", y="0")
        ET.SubElement(transform, f"{{{A}}}ext", cx=str(cx), cy=str(cy))
        ET.SubElement(ET.SubElement(shape, f"{{{A}}}prstGeom", prst="rect"), f"{{{A}}}avLst")
        section = body.find(f"{{{W}}}sectPr")
        body.insert(list(body).index(section) if section is not None else len(body), paragraph)
    parts.update({"word/document.xml": _serialize(root), relname: _serialize(relationships), "[Content_Types].xml": _serialize(types)})
    return _package(parts)
