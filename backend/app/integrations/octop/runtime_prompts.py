"""Local runtime facts for imported experts; never mutate source or grant tools."""

OFFICE_ADAPTER_VERSION = "1"
OFFICE_RUNTIME = """
<prismos-office-runtime version="1">
The current host supplies independent native Office tools. For this expert,
these runtime facts replace references to the excluded bundled docx/xlsx/pptx/pdf
Skill packages in the imported persona. Do not search for or execute their scripts.
Use read_file for an authorized uploaded text brief. Use office_docx, office_xlsx,
office_pptx or office_pdf for the matching format, following its actual schema.
Create a new owned /mnt/user-data/outputs/ filename; never overwrite an existing
artifact. Use present_files after success so the user can download the result.
DOCX supports basic creation/inspection/text replacement and owned inline images;
XLSX supports basic creation/inspection/edits and supported charts; PPTX supports
basic creation/inspection/text/chart edits and owned images; PDF supports basic
creation/inspection/page selection/merge/render and authorized fonts.
Advanced layout, formula calculation, OCR/forms and full desktop rendering remain
pending. If a requested operation is unavailable, explain that boundary and offer
supported steps; do not claim execution or silently drop the requested result.
All existing file, member, thread, resource and tool authorization still applies.
This adapter does not install Skills, grant tools or enable child delegation.
</prismos-office-runtime>
""".strip()


def runtime_agent(agent):
    """Return a detached copy with effective instructions, preserving stored bytes."""
    if agent is None:
        return None
    source = (agent.meta_info or {}).get("octop_source", {})
    if source.get("project") != "Octop" or source.get("template_id") != "expert:office-automation":
        return agent
    prompt = agent.system_prompt or ""
    return agent.model_copy(update={"system_prompt": prompt + "\n\n" + OFFICE_RUNTIME})
