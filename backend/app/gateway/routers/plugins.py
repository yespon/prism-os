"""Plugin info endpoint — exposes enabled/disabled state to frontend."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.gateway.config import get_plugin_states
from app.plugins.registry import PLUGIN_DEFINITIONS

router = APIRouter(prefix="/api", tags=["plugins"])


class PluginInfo(BaseModel):
    key: str
    name: str
    description: str
    enabled: bool
    frontendNavIds: list[str]


class PluginsResponse(BaseModel):
    plugins: list[PluginInfo]


@router.get("/plugins", response_model=PluginsResponse)
async def list_plugins() -> PluginsResponse:
    """Return all plugin definitions with their current enabled state."""
    states = get_plugin_states()
    items: list[PluginInfo] = []
    for defn in PLUGIN_DEFINITIONS.values():
        items.append(PluginInfo(
            key=defn.key,
            name=defn.name,
            description=defn.description,
            enabled=states.get(defn.key, defn.default_enabled),
            frontendNavIds=defn.frontend_nav_ids,
        ))
    return PluginsResponse(plugins=items)