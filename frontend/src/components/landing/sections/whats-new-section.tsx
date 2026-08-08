"use client";

import MagicBento, { type BentoCardProps } from "@/components/ui/magic-bento";
import { cn } from "@/lib/utils";

import { Section } from "../section";

const COLOR = "#0a0a0a";
const features: BentoCardProps[] = [
  {
    color: COLOR,
    label: "Multi-Tenant",
    title: "Team-Ready Governance",
    description: "Tenant isolation, RBAC, and audit trails from day one",
  },
  {
    color: COLOR,
    label: "Customizable",
    title: "Agents with Guardrails",
    description:
      "Define agent personality, tool whitelists, and behavioral boundaries per tenant",
  },
  {
    color: COLOR,
    label: "Extensible",
    title: "Skills and Tools",
    description:
      "Plug, play, or swap built-in tools. Connect MCP servers. Build the agent you want.",
  },
  {
    color: COLOR,
    label: "Secure",
    title: "Sandbox Execution",
    description: "Isolated Docker containers — read, write, run, audit",
  },
  {
    color: COLOR,
    label: "Flexible",
    title: "20+ Model Providers",
    description: "OpenAI, Anthropic, DeepSeek, Gemini, Ollama, 智谱, 百炼...",
  },
  {
    color: COLOR,
    label: "Open Source",
    title: "MIT License",
    description: "Self-hosted, full control, community-driven",
  },
];

export function WhatsNewSection({ className }: { className?: string }) {
  return (
    <Section
      className={cn("", className)}
      title="What PrismOS Offers"
      subtitle="From a single-user Agent to a governed, multi-tenant platform for your digital workforce"
    >
      <div className="flex w-full items-center justify-center">
        <MagicBento data={features} />
      </div>
    </Section>
  );
}
