import os
from pathlib import Path

from deerflow.config.extensions_config import get_extensions_config
from deerflow.config.tenant_context import get_current_tenant_id
from deerflow.database.user_config_store import load_user_skill_records

from .parser import parse_skill_file
from .types import Skill


def get_skills_root_path() -> Path:
    """
    Get the root path of the skills directory.

    Returns:
        Path to the skills directory (deer-flow/skills)
    """
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
    skills_dir = backend_dir.parent / "skills"
    return skills_dir


def _load_public_skills(skills_path: Path) -> list[Skill]:
    skills: list[Skill] = []
    category_path = skills_path / "public"
    if not category_path.exists() or not category_path.is_dir():
        return skills

    for current_root, dir_names, file_names in os.walk(category_path, followlinks=True):
        dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
        if "SKILL.md" not in file_names:
            continue

        skill_file = Path(current_root) / "SKILL.md"
        relative_path = skill_file.parent.relative_to(category_path)
        skill = parse_skill_file(skill_file, category="public", relative_path=relative_path)
        if skill:
            skills.append(skill)
    return skills


def _parse_tenant_custom_skill(skills_path: Path, record: dict) -> Skill | None:
    install_dir = record.get("install_dir")
    relative_path = str(record.get("relative_path") or record.get("name") or "").strip()

    skill_dir: Path | None = None
    if isinstance(install_dir, str) and install_dir.strip():
        skill_dir = Path(install_dir)
    elif relative_path:
        skill_dir = skills_path / "custom" / relative_path

    if skill_dir is None:
        return None

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    relative = Path(relative_path or skill_dir.name)
    parsed = parse_skill_file(skill_file, category="custom", relative_path=relative)
    if parsed is None:
        return None

    parsed.enabled = bool(record.get("enabled", True))
    return parsed


def load_skills(skills_path: Path | None = None, use_config: bool = True, enabled_only: bool = False) -> list[Skill]:
    """
    Load all skills from the skills directory.

    Scans both public and custom skill directories, parsing SKILL.md files
    to extract metadata. The enabled state is determined by the skills_state_config.json file.

    Args:
        skills_path: Optional custom path to skills directory.
                     If not provided and use_config is True, uses path from config.
                     Otherwise defaults to deer-flow/skills
        use_config: Whether to load skills path from config (default: True)
        enabled_only: If True, only return enabled skills (default: False)

    Returns:
        List of Skill objects, sorted by name
    """
    if skills_path is None:
        if use_config:
            try:
                from deerflow.config import get_app_config

                config = get_app_config()
                skills_path = config.skills.get_skills_path()
            except Exception:
                skills_path = get_skills_root_path()
        else:
            skills_path = get_skills_root_path()

    if not skills_path.exists():
        return []

    skills = _load_public_skills(skills_path)
    current_tenant_id = get_current_tenant_id()

    if use_config and not current_tenant_id:
        # The standalone harness/client has no tenant database context.  In
        # that mode the file-backed extensions config remains the source of
        # truth for public skill enablement.
        extensions_config = get_extensions_config()
        for skill in skills:
            skill.enabled = extensions_config.is_skill_enabled(skill.name, skill.category)

    if current_tenant_id:
        shared_owner_id = f"__tenant_shared_skill__:{current_tenant_id}"
        records = load_user_skill_records(shared_owner_id, tenant_id=current_tenant_id)
        skills_by_id = {(s.name, s.category): s for s in skills}
        skills_by_name = {s.name: s for s in skills}

        for record in records:
            name = str(record.get("name") or "").strip()
            category = str(record.get("category") or "custom").strip() or "custom"
            if not name:
                continue

            existing = skills_by_name.get(name)
            if existing is not None and existing.category == "public" and category != "public":
                # Unqualified legacy names retain the public default. A custom
                # same-name registration is a different resource, not a toggle.
                continue

            if existing is not None:
                existing.enabled = bool(record.get("enabled", True))
                continue

            key = (name, category)
            if key in skills_by_id:
                skills_by_id[key].enabled = bool(record.get("enabled", True))
                continue

            if category != "custom":
                continue

            parsed = _parse_tenant_custom_skill(skills_path, record)
            if parsed is None:
                continue
            skills.append(parsed)
            skills_by_id[(parsed.name, parsed.category)] = parsed
            skills_by_name[parsed.name] = parsed

    if enabled_only:
        skills = [skill for skill in skills if skill.enabled]

    skills.sort(key=lambda s: s.name)

    return skills
