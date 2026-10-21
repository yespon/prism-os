"use client";

import { BotIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { useTenantKey } from "@/core/agents/hooks";
import { fetchAuthApi } from "@/core/api/auth-client";

export function AgentAvatar({
  avatarId,
  className = "size-8",
}: {
  avatarId?: string | null;
  className?: string;
}) {
  const tenant = useTenantKey();
  const [image, setImage] = useState<{ scope: string; url: string } | null>(
    null,
  );
  const scope = `${tenant}:${avatarId ?? ""}`;
  useEffect(() => {
    if (!avatarId) return;
    const controller = new AbortController();
    let url: string | undefined;
    void fetchAuthApi(
      `/api/agent-catalog/avatars/${encodeURIComponent(avatarId)}`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("Avatar unavailable");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        setImage({ scope, url });
      })
      .catch(() => {
        if (!controller.signal.aborted) setImage(null);
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [scope, avatarId]);
  return image?.scope === scope ? (
    // Local object URL comes only from the authenticated, validated SVG catalog.
     
    <img src={image.url} alt="" className={className} />
  ) : (
    <BotIcon className={className} aria-hidden="true" />
  );
}
