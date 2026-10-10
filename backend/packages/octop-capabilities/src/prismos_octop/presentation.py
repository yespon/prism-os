"""Bounded, read-only presentation data; never import the upstream router."""

from __future__ import annotations

import ast
import hashlib
from functools import lru_cache
from xml.etree import ElementTree

from .catalog import DATA, Locale, provenance

AXES = ("EI", "SN", "TF", "JP")


@lru_cache(maxsize=1)
def _questions() -> tuple[dict, ...]:
    provenance()
    tree = ast.parse((DATA / "personality/mbti-source.py.txt").read_text())
    declarations = [node for node in tree.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_QUESTIONS"]
    if len(declarations) != 1 or not isinstance(declarations[0].value, ast.List):
        raise ValueError("Invalid questionnaire declaration")
    questions = []
    keys = {"id", "dimension", "a_pole", "b_pole"} | {f"{field}_{locale}" for field in ("question", "option_a", "option_b") for locale in ("zh", "en")}
    for item in declarations[0].value.elts:
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name) or item.func.id != "TestQuestion" or item.args:
            raise ValueError("Invalid questionnaire item")
        value = {kw.arg: ast.literal_eval(kw.value) for kw in item.keywords}
        if len(value) != len(item.keywords) or set(value) != keys or type(value["id"]) is not int:
            raise ValueError("Invalid questionnaire fields")
        if any(not isinstance(value[key], str) or not value[key] for key in keys - {"id"}):
            raise ValueError("Invalid questionnaire text")
        if value["dimension"] not in AXES or value["a_pole"] + value["b_pole"] != value["dimension"]:
            raise ValueError("Invalid questionnaire dimension")
        questions.append(value)
    if [q["id"] for q in questions] != list(range(1, 29)) or any(sum(q["dimension"] == axis for q in questions) != 7 for axis in AXES):
        raise ValueError("Incomplete questionnaire")
    return tuple(questions)


def questionnaire(locale: Locale = "zh") -> list[dict]:
    return [{"id": q["id"], "question": q[f"question_{locale}"], "option_a": q[f"option_a_{locale}"], "option_b": q[f"option_b_{locale}"]} for q in _questions()]


def score_answers(answers: dict[str, str]) -> dict:
    questions = {str(q["id"]): q for q in _questions()}
    if not 20 <= len(answers) <= 28 or set(answers) - questions.keys() or any(choice.upper() not in ("A", "B") for choice in answers.values()):
        raise ValueError("Provide 20–28 valid questionnaire answers")
    counts = {axis: dict.fromkeys(axis, 0) for axis in AXES}
    for key, choice in answers.items():
        question = questions[key]
        counts[question["dimension"]][question["a_pole"] if choice.upper() == "A" else question["b_pole"]] += 1
    code, dimensions = "", {}
    for axis in AXES:
        a, b = (counts[axis][pole] for pole in axis)
        dominant = axis[0] if a >= b else axis[1]
        total = a + b
        percentage = max(50, min(85, round(50 + max(a, b) / total * 35))) if total else 50
        code += dominant
        dimensions[axis] = [dominant, percentage]
    return {"code": code, "dimensions": dimensions, "answered": len(answers), "automatic_apply": False}


@lru_cache(maxsize=1)
def _avatars() -> dict[str, tuple[bytes, str]]:
    provenance()
    result = {}
    for kind in ("experts", "personas"):
        for path in sorted((DATA / "avatars" / kind).glob("*.svg")):
            data = path.read_bytes()
            # SVG is served as an image, with CSP. Fail closed on active/external content.
            root = ElementTree.fromstring(data)
            allowed = {
                "svg",
                "g",
                "path",
                "circle",
                "ellipse",
                "rect",
                "line",
                "polyline",
                "polygon",
                "defs",
                "linearGradient",
                "radialGradient",
                "stop",
                "clipPath",
                "mask",
                "title",
                "desc",
                "text",
                "tspan",
                "use",
                "filter",
                "feGaussianBlur",
                "feOffset",
                "feBlend",
                "feColorMatrix",
                "feComposite",
                "feFlood",
                "feMerge",
                "feMergeNode",
            }
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1] not in allowed:
                    raise ValueError("Unsupported avatar element")
                for key, value in node.attrib.items():
                    name = key.rsplit("}", 1)[-1].lower()
                    if name.startswith("on") or name == "style" or (name == "href" and not value.startswith("#")) or ("url(" in value.lower() and not value.startswith("url(#")):
                        raise ValueError("Active avatar content")
            if root.tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError("Invalid avatar root")
            result[f"{kind}:{path.stem}"] = (data, hashlib.sha256(data).hexdigest())
    return result


def list_avatars() -> list[dict]:
    return [{"id": key, "label": key.split(":", 1)[1], "kind": key.split(":", 1)[0], "sha256": value[1]} for key, value in _avatars().items()]


def avatar(avatar_id: str) -> tuple[bytes, str]:
    try:
        return _avatars()[avatar_id]
    except KeyError:
        raise ValueError("Unknown avatar") from None
