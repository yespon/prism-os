import base64
import mimetypes
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.runtime import current_file_access


@tool("view_image", parse_docstring=True)
def view_image_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    image_path: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Read an image file.

    Use this tool to read an image file and make it available for display.

    When to use the view_image tool:
    - When you need to view an image file.

    When NOT to use the view_image tool:
    - For non-image files (use present_files instead)
    - For multiple files at once (use present_files instead)

    Args:
        image_path: Absolute path to the image file. Common formats supported: jpg, jpeg, png, webp.
    """
    path = Path(image_path)
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    try:
        if not path.is_absolute() or path.suffix.lower() not in valid_extensions:
            raise ValueError("An absolute supported image path is required")
        image_data = current_file_access(runtime, "read_bytes", image_path)
        if image_data is None:
            # Standalone harnesses have no host database. Constrain them to
            # their thread directories too; arbitrary host images are unsafe.
            from deerflow.sandbox.file_access import read_standalone_file

            image_data = read_standalone_file(runtime, image_path)
        image_base64 = base64.b64encode(image_data).decode("utf-8")
        mime_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
    except Exception:
        return Command(update={"messages": [ToolMessage("Error: Current image access unavailable", tool_call_id=tool_call_id)]})

    # Update viewed_images in state
    # The merge_viewed_images reducer will handle merging with existing images
    new_viewed_images = {image_path: {"base64": image_base64, "mime_type": mime_type}}

    return Command(
        update={"viewed_images": new_viewed_images, "messages": [ToolMessage("Successfully read image", tool_call_id=tool_call_id)]},
    )
