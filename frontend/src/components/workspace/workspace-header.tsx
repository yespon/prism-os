"use client";

import Link from "next/link";

import { useSidebar } from "@/components/ui/sidebar";
import { env } from "@/env";
import { cn } from "@/lib/utils";

function PrismOSMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex h-6 w-6 items-center justify-center shrink-0",
        className,
      )}
      aria-label="PrismOS"
    >
        <img
        src="/images/opsintech.svg"
        alt="PrismOS Logo"
        className="h-full w-full object-contain"
      />
    </div>
  );
}

export function WorkspaceHeader({ className }: { className?: string }) {
  const { state } = useSidebar();
  return (
    <>
      <div
        className={cn(
          "flex h-12 flex-col justify-center",
          className,
        )}
      >
        {state === "collapsed" ? (
          <div className="flex w-full items-center justify-center">
            <PrismOSMark className="transition-transform hover:scale-105" />
          </div>
        ) : (
          <div className="flex items-center px-1">
            {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ? (
              <Link href="/" className="text-foreground ml-1 flex items-center gap-2.5 transition-opacity hover:opacity-80">
                <PrismOSMark />
                <span className="truncate text-sm font-semibold tracking-tight">
                  PrismOS Platform
                </span>
              </Link>
            ) : (
              <div className="text-foreground ml-1 flex items-center gap-2.5 cursor-default">
                <PrismOSMark />
                <span className="truncate text-sm font-semibold tracking-tight">
                  PrismOS Platform
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
