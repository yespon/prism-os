"""Owned native Skill edits. No cross-store rollback guesses or execution grants."""

import hashlib
import os
import stat
import uuid
from pathlib import Path

from sqlalchemy import select, text

from deerflow.database import user_config_service as service
from deerflow.database.models import TenantSkill
from deerflow.skills.loader import _load_public_skills
from deerflow.skills.resource_identity import public_resource_id, registered_resource_id, resource_directory


class SkillMutationRejected(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


class SkillMutationUnknown(Exception):
    def __init__(self, resource_id: str):
        self.resource_id = resource_id
        super().__init__("Skill edit outcome requires inspection; owned contents were preserved")


class OwnedMarkdown:
    """Directory/file descriptors keep aliases and replacement files out of edits."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.fd = None
        self.file_info = None
        self.temporary = None
        self.written = False
        if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
            raise SkillMutationRejected(409, "Safe Skill editing is unavailable on this filesystem")
        try:
            self.fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.identity = os.fstat(self.fd)
            self.check_directory()
            file_fd = os.open("SKILL.md", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
            with os.fdopen(file_fd, "rb") as file:
                self.file_info = os.fstat(file.fileno())
                if not stat.S_ISREG(self.file_info.st_mode):
                    raise SkillMutationRejected(409, "Skill main file is not a regular owned file")
                self.original = file.read()
        except (OSError, UnicodeError):
            self.close()
            raise SkillMutationRejected(409, "Skill files cannot be verified; contents were preserved") from None
        except BaseException:
            self.close()
            raise

    def check_directory(self):
        current = self.directory.lstat()
        if self.directory.resolve() != self.directory or stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != (self.identity.st_dev, self.identity.st_ino):
            raise SkillMutationRejected(409, "Skill directory changed; contents were preserved")

    def prepare(self, content: str):
        self.temporary = ".prismos-edit-" + uuid.uuid4().hex
        fd = os.open(self.temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, self.file_info.st_mode & 0o777, dir_fd=self.fd)
        with os.fdopen(fd, "wb") as file:
            file.write(content.encode("utf-8"))
            file.flush()
            os.fsync(file.fileno())

    def publish(self):
        self.check_directory()
        fd = os.open("SKILL.md", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        with os.fdopen(fd, "rb") as file:
            current = os.fstat(file.fileno())
            if (current.st_dev, current.st_ino) != (self.file_info.st_dev, self.file_info.st_ino) or hashlib.sha256(file.read()).digest() != hashlib.sha256(self.original).digest():
                raise SkillMutationRejected(409, "Skill main file changed; contents were preserved")
        os.replace(self.temporary, "SKILL.md", src_dir_fd=self.fd, dst_dir_fd=self.fd)
        self.temporary = None
        self.written = True
        os.fsync(self.fd)

    def close(self):
        if self.fd is not None:
            try:
                if self.temporary:
                    os.unlink(self.temporary, dir_fd=self.fd)
            finally:
                os.close(self.fd)
                self.fd = None


async def patch_owned_skill(root: Path, tenant: str, actor: str, shared: bool, name: str, body, *, split, render, normalize) -> str:
    owner = f"__tenant_shared_skill__:{tenant}" if shared else actor
    if not actor:
        raise SkillMutationRejected(401, "Current user identity is required")
    if body.category is not None and body.category.strip() == "public":
        raise SkillMutationRejected(403, "Public source files cannot be edited through tenant resource management")
    resource_id = body.expected_resource_id
    markdown = None
    mutated = False
    try:
        async with service.get_session_factory()() as session:
            async with session.begin():
                if session.get_bind().dialect.name == "sqlite":
                    await session.execute(text("BEGIN IMMEDIATE"))
                result = await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == owner, TenantSkill.name == name).with_for_update())
                row = result.scalars().first()
                if row is None:
                    raise SkillMutationRejected(404, "Current owned Skill not found")
                resource_id = registered_resource_id(row)
                if body.expected_resource_id is not None and body.expected_resource_id != resource_id:
                    raise SkillMutationRejected(409, "Skill instance changed; inspect the current resource")
                if row.category == "public":
                    raise SkillMutationRejected(403, "Public source files are read-only here; use the original tenant enablement control")
                try:
                    directory = resource_directory(root, tenant, actor, {"name": row.name, "scope": "tenant" if shared else "personal", "install_dir": row.install_dir, "relative_path": row.relative_path})
                except ValueError:
                    raise SkillMutationRejected(409, "Skill location cannot be verified; contents were preserved") from None
                markdown = OwnedMarkdown(directory)
                if body.expected_file_sha256 is not None and hashlib.sha256(markdown.original).hexdigest() != body.expected_file_sha256:
                    raise SkillMutationRejected(409, "Skill contents changed; inspect the current resource")
                try:
                    frontmatter, instructions = split(markdown.original.decode("utf-8"))
                    if frontmatter.get("name") != row.name:
                        raise ValueError("Skill name differs from registration")
                    if body.description is not None or body.instructions is not None:
                        description = normalize(body.description) if body.description is not None else str(frontmatter.get("description") or row.name)
                        content = render(
                            row.name,
                            description,
                            body.instructions if body.instructions is not None else instructions,
                            created_by=frontmatter.get("created_by") if shared else actor,
                            version=int(frontmatter.get("version", 1)) + 1,
                            changelog=body.changelog or "Updated",
                            usage_count=int(frontmatter.get("usage_count", 0)),
                            references=frontmatter.get("references"),
                        )
                        markdown.prepare(content)
                except (ValueError, TypeError, UnicodeError):
                    raise SkillMutationRejected(409, "Skill format or edit content cannot be verified") from None
                # Permission, instance, location and format are validated before
                # changing either file bytes or the original native row.
                if markdown.temporary:
                    markdown.publish()
                    mutated = True
                if body.enabled is not None:
                    row.enabled = body.enabled
                if body.category is not None and body.category.strip():
                    row.category = body.category.strip()
                session.add(row)
                mutated = True
            # A timeout here can occur after commit; never delete/restore files.
        if any(getattr(body, field) is not None for field in ("bound_tools", "prompt_template", "strategy")):
            fields = {key: getattr(body, key) for key in ("bound_tools", "prompt_template", "strategy")}
            if shared:
                await service.update_tenant_shared_skill_settings(tenant, name, **fields)
            else:
                await service.update_tenant_personal_skill_settings(tenant, actor, name, **fields)
        return resource_id
    except SkillMutationRejected:
        if mutated or (markdown is not None and markdown.written):
            raise SkillMutationUnknown(resource_id) from None
        raise
    except Exception:
        if mutated or (markdown is not None and markdown.written):
            raise SkillMutationUnknown(resource_id) from None
        raise
    finally:
        if markdown is not None:
            markdown.close()


async def set_shared_enablement(root: Path, tenant: str, actor: str, name: str, enabled: bool, expected_resource_id: str | None = None) -> tuple[str, str]:
    """Toggle the existing tenant row or a verified public tenant override.

    Public and custom rows share the original owner/name unique key. A public
    selector cannot convert or modify a colliding custom row. No new registry.
    """
    if not actor:
        raise SkillMutationRejected(401, "Current user identity is required")
    owner = f"__tenant_shared_skill__:{tenant}"
    mutated = False
    resource_id = expected_resource_id
    try:
        async with service.get_session_factory()() as session:
            async with session.begin():
                if session.get_bind().dialect.name == "sqlite":
                    await session.execute(text("BEGIN IMMEDIATE"))
                result = await session.exec(select(TenantSkill).where(TenantSkill.tenant_id == tenant, TenantSkill.user_id == owner, TenantSkill.name == name).with_for_update())
                row = result.scalars().first()
                wants_public = bool(expected_resource_id and expected_resource_id.startswith("public:"))
                if row is not None and row.category != "public":
                    resource_id = registered_resource_id(row)
                    if wants_public or (expected_resource_id is not None and expected_resource_id != resource_id):
                        raise SkillMutationRejected(409, "Skill instance or scope changed; inspect current resources")
                    try:
                        directory = resource_directory(root, tenant, actor, {"name": row.name, "scope": "tenant", "install_dir": row.install_dir, "relative_path": row.relative_path})
                    except ValueError:
                        raise SkillMutationRejected(409, "Skill location cannot be verified; contents were preserved") from None
                    if enabled and not (directory / "SKILL.md").is_file():
                        raise SkillMutationRejected(409, "Skill main file is unavailable; enablement was preserved")
                    scope = "tenant"
                else:
                    if expected_resource_id is not None and not wants_public:
                        raise SkillMutationRejected(409, "Selected registered Skill is no longer current")
                    candidates = [skill for skill in _load_public_skills(root) if skill.name == name and (expected_resource_id is None or public_resource_id(skill.skill_path) == expected_resource_id)]
                    if not candidates:
                        raise SkillMutationRejected(404, "Current public or shared Skill not found")
                    if len(candidates) != 1:
                        raise SkillMutationRejected(409, "Public Skill name is ambiguous; select its concrete source")
                    public = candidates[0]
                    resource_id = public_resource_id(public.skill_path)
                    try:
                        directory = resource_directory(root, tenant, actor, {"scope": "global", "install_dir": str(public.skill_dir)})
                    except ValueError:
                        raise SkillMutationRejected(409, "Public Skill location cannot be verified") from None
                    if not (directory / "SKILL.md").is_file():
                        raise SkillMutationRejected(409, "Public Skill main file is unavailable")
                    if row is None:
                        row = TenantSkill(tenant_id=tenant, user_id=owner, name=name, category="public", relative_path=public.skill_path, install_dir=str(directory), enabled=enabled)
                    elif (row.install_dir and Path(row.install_dir).absolute() != directory) or (row.relative_path and row.relative_path != public.skill_path):
                        raise SkillMutationRejected(409, "Public override location differs from the selected source")
                    scope = "global"
                row.enabled = enabled
                session.add(row)
                mutated = True
        return scope, resource_id
    except SkillMutationRejected:
        raise
    except Exception:
        if mutated:
            raise SkillMutationUnknown(resource_id) from None
        raise
