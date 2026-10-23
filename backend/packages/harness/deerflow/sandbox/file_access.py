"""Descriptor-based reads: directories are authority, symlinks never are."""

import os
import stat
from pathlib import Path, PurePosixPath


def owned_path(path, roots):
    requested = PurePosixPath("/" + str(path).lstrip("/"))
    if ".." in str(path).split("/") or "\\" in str(path):
        raise PermissionError("File path unavailable")
    for name, root in roots.items():
        root = Path(root)
        virtual = PurePosixPath("/mnt/user-data") / name
        if requested.is_relative_to(virtual):
            relative = requested.relative_to(virtual)
        elif Path(str(requested)).is_relative_to(root):
            relative = Path(str(requested)).relative_to(root)
        else:
            continue
        return root / str(relative), str(virtual / str(relative))
    raise PermissionError("File is outside the current thread")


def read_owned_file(path):
    """Read held regular-file descriptors without following any path alias.

    Walk from /, retaining every ancestor. Compare the path and descriptor
    identities after reading so replacement cannot publish stale/mixed bytes.
    """
    path = Path(path)
    opened = []
    chain = []
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        opened.append(fd)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            chain.append((fd, part, child))
            opened.append(child)
            fd = child
        member = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        opened.append(member)
        before = os.fstat(member)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise PermissionError("File is not an independently owned regular file")
        chunks = []
        while chunk := os.read(member, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(member)

        def identity(info):
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

        if identity(before) != identity(after) or identity(os.stat(path.name, dir_fd=fd, follow_symlinks=False)) != identity(after):
            raise PermissionError("File changed during access")
        for parent, name, child in chain:
            current, held = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(child)
            if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise PermissionError("File ancestor changed during access")
        return b"".join(chunks)
    finally:
        for fd in reversed(opened):
            os.close(fd)


def read_standalone_file(runtime, path):
    roots = {key.removesuffix("_path"): value for key, value in ((runtime.state or {}).get("thread_data") or {}).items()}
    actual, _ = owned_path(path, roots)
    return read_owned_file(actual)


def mutate_owned_file(path, operation):
    """Write/replace through held ancestors without following aliases."""
    path = Path(path)
    opened = []
    chain = []
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        opened.append(fd)
        for part in path.parts[1:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, mode=0o700, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            chain.append((fd, part, child))
            opened.append(child)
            fd = child
        if operation[0] == "create":
            return _publish_owned_bytes(path, operation[1], fd, chain)
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        if operation[0] == "write":
            flags |= os.O_CREAT
        member = os.open(path.name, flags, 0o600, dir_fd=fd)
        opened.append(member)
        info = os.fstat(member)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PermissionError("File is not independently owned")
        for parent, name, child in chain:
            current, held = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(child)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise PermissionError("File ancestor changed")
        if operation[0] == "write":
            _, content, append = operation
            if append:
                os.lseek(member, 0, os.SEEK_END)
            else:
                os.ftruncate(member, 0)
        else:
            _, old, new, replace_all = operation
            chunks = []
            while chunk := os.read(member, 1024 * 1024):
                chunks.append(chunk)
            content = b"".join(chunks).decode("utf-8")
            if not content:
                return "OK"
            if old not in content:
                return "Error: String to replace not found in current file"
            content = content.replace(old, new) if replace_all else content.replace(old, new, 1)
            os.ftruncate(member, 0)
            os.lseek(member, 0, os.SEEK_SET)
        data = memoryview(content.encode("utf-8"))
        while data:
            data = data[os.write(member, data) :]
        os.fsync(member)
        current, held = os.stat(path.name, dir_fd=fd, follow_symlinks=False), os.fstat(member)
        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise PermissionError("File replaced during mutation; inspect outputs")
        for parent, name, child in chain:
            current, held = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(child)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise PermissionError("File ancestor replaced during mutation; inspect outputs")
        return "OK"
    finally:
        for fd in reversed(opened):
            os.close(fd)

def _publish_owned_bytes(path, content, directory, chain):
    """Publish a complete binary file exclusively through held original ancestors."""
    import uuid

    from deerflow.skills.install_receipts import publish_no_replace

    if not isinstance(content, bytes):
        raise TypeError("Binary output required")

    def check_chain():
        for parent, name, child in chain:
            current, held = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(child)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise PermissionError("Output ancestor changed; inspect outputs")

    check_chain()
    stage = ".prismos-stage-output-" + uuid.uuid4().hex
    member = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    original = os.fstat(member)
    published = False
    try:
        data = memoryview(content)
        while data:
            written = os.write(member, data)
            if written <= 0:
                raise OSError("Output write did not progress")
            data = data[written:]
        os.fsync(member)
        current = os.stat(stage, dir_fd=directory, follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_nlink, current.st_size) != (original.st_dev, original.st_ino, 1, len(content)):
            raise PermissionError("Staged output changed")
        check_chain()
        publish_no_replace(path.with_name(stage), path, parent_descriptor=directory)
        published = True
        current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_nlink, current.st_size) != (original.st_dev, original.st_ino, 1, len(content)):
            raise PermissionError("Published output changed; inspect outputs")
        check_chain()
        return "OK"
    finally:
        os.close(member)
        if not published:
            try:
                current = os.stat(stage, dir_fd=directory, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (original.st_dev, original.st_ino):
                    os.unlink(stage, dir_fd=directory)
                    os.fsync(directory)
            except FileNotFoundError:
                pass
