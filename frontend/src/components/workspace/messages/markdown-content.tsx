"use client";

import { Play, Loader2, CheckCircle2 } from "lucide-react";
import React, { useMemo } from "react";
import type { AnchorHTMLAttributes } from "react";

import { useTerminalContext } from "@/app/workspace/terminal/context";
import { CodeBlock, CodeBlockCopyButton } from "@/components/ai-elements/code-block";
import {
  MessageResponse,
  type MessageResponseProps,
} from "@/components/ai-elements/message";
import { streamdownPlugins } from "@/core/streamdown";
import { cn } from "@/lib/utils";

import { CitationLink } from "../citations/citation-link";

function isExternalUrl(href: string | undefined): boolean {
  return !!href && /^https?:\/\//.test(href);
}

function textFromChildren(children: React.ReactNode): string {
  if (Array.isArray(children)) {
    return children
      .map((child) =>
        typeof child === "string" || typeof child === "number" ? String(child) : "",
      )
      .join("");
  }
  return typeof children === "string" || typeof children === "number"
    ? String(children)
    : "";
}

export type MarkdownContentProps = {
  content: string;
  isLoading: boolean;
  rehypePlugins: MessageResponseProps["rehypePlugins"];
  className?: string;
  remarkPlugins?: MessageResponseProps["remarkPlugins"];
  components?: MessageResponseProps["components"];
};

type MarkdownParagraphProps = React.HTMLAttributes<HTMLParagraphElement> & {
  node?: unknown;
};

type ExecuteCommandProps = {
  children?: React.ReactNode;
};

function ExecuteCommand({ children }: ExecuteCommandProps) {
  const terminalContext = useTerminalContext();
  const cmd = textFromChildren(children);
  const [isExecuting, setIsExecuting] = React.useState(false);
  const [isFinished, setIsFinished] = React.useState(false);

  const handleRun = async () => {
    if (!terminalContext) return;
    setIsExecuting(true);
    try {
      const output = await terminalContext.executeCommand(cmd);
      setIsFinished(true);

      if (terminalContext.sendMessageRef.current) {
        const resultMessage = `<tool_result>\n${output || "Command executed successfully with no output."}\n</tool_result>`;
        terminalContext.sendMessageRef.current(resultMessage);
      }
    } catch (error: unknown) {
      console.error("Execute error:", error);
      if (terminalContext.sendMessageRef.current) {
        const message = error instanceof Error ? error.message : String(error);
        const errorMessage = `<tool_result>\nError executing command:\n${message}\n</tool_result>`;
        terminalContext.sendMessageRef.current(errorMessage);
      }
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-blue-200 bg-blue-50/50 shadow-sm">
      <div className="flex items-center justify-between bg-blue-100/50 px-4 py-2 border-b border-blue-200/50">
        <div className="flex items-center gap-2 text-blue-700 font-medium text-xs">
          <div className="size-5 rounded-md bg-blue-600 flex items-center justify-center text-white">
            <Play className="size-3" fill="currentColor" />
          </div>
          Command Suggestion
        </div>
        {terminalContext && (
          <button
            onClick={handleRun}
            disabled={isExecuting || isFinished}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
              isFinished
                ? "bg-emerald-100 text-emerald-700 cursor-not-allowed"
                : isExecuting
                  ? "bg-blue-200 text-blue-700 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700 text-white shadow-sm",
            )}
          >
            {isFinished ? (
              <><CheckCircle2 className="size-3.5" /> Done</>
            ) : isExecuting ? (
              <><Loader2 className="size-3.5 animate-spin" /> Running</>
            ) : (
              <>Run in Terminal</>
            )}
          </button>
        )}
      </div>
      <div className="p-4 bg-white/60 font-mono text-[13px] text-zinc-800 break-all whitespace-pre-wrap leading-relaxed">
        {cmd}
      </div>
    </div>
  );
}

/** Renders markdown content. */
export function MarkdownContent({
  content,
  rehypePlugins,
  className,
  remarkPlugins = streamdownPlugins.remarkPlugins,
  components: componentsFromProps,
}: MarkdownContentProps) {
  const components = useMemo(() => {
    return {
      p: (props: MarkdownParagraphProps) => {
        const { node, ...rest } = props;
        void node;
        return <div className="mb-3 last:mb-0" {...rest} />;
      },
      a: (props: AnchorHTMLAttributes<HTMLAnchorElement>) => {
        if (typeof props.children === "string") {
          const match = /^citation:(.+)$/.exec(props.children);
          if (match) {
            const [, text] = match;
            return <CitationLink {...props}>{text}</CitationLink>;
          }
        }
        const { className, target, rel, ...rest } = props;
        const external = isExternalUrl(props.href);
        return (
          <a
            {...rest}
            className={cn("text-primary underline decoration-primary/30 underline-offset-2 hover:decoration-primary/60 transition-colors", className)}
            target={target ?? (external ? "_blank" : undefined)}
            rel={rel ?? (external ? "noopener noreferrer" : undefined)}
          />
        );
      },
      code: ({
        _node,
        inline,
        className,
        children,
        ...props
      }: React.HTMLAttributes<HTMLElement> & {
        _node?: unknown;
        inline?: boolean;
        className?: string;
        children?: React.ReactNode;
      }) => {
        const match = /language-([^\s]+)/.exec(className ?? "");
        if (!inline && match) {
          const lang = match[1] ?? "text";
          const codeString = Array.isArray(children)
            ? children
                .map((child) =>
                  typeof child === "string" || typeof child === "number"
                    ? String(child)
                    : "",
                )
                .join("")
            : typeof children === "string" || typeof children === "number"
              ? String(children)
              : "";
          return (
            <div className="my-6 overflow-hidden rounded-[12px] border border-black/5 dark:border-white/10 bg-slate-50 dark:bg-[#0c0c0d] relative group">
              <div className="flex h-10 items-center justify-between border-b border-black/5 dark:border-white/5 bg-black/5 dark:bg-white/5 px-4 text-xs text-zinc-500 dark:text-zinc-400">
                <span className="font-mono uppercase tracking-wider">{lang}</span>
                <CodeBlockCopyButton variant="ghost" size="icon" className="h-6 w-6 rounded-[6px] hover:bg-black/5 dark:hover:bg-white/10 text-zinc-400 dark:text-zinc-400" />
              </div>
              <CodeBlock
                code={codeString.replace(/\n$/, "")}
                language={lang}
                className="rounded-none border-0 bg-transparent p-4 pb-4 *:!bg-transparent text-[12px] leading-[1.6] font-mono text-zinc-800 dark:text-zinc-200"
                {...props}
              />
            </div>
          );
        }
        return (
          <code
            className={cn(
              "rounded-[6px] bg-black/5 dark:bg-white/10 px-1.5 py-0.5 font-mono text-[12.5px] font-medium text-foreground",
              className
            )}
            {...props}
          >
            {children}
          </code>
        );
      },
      execute_command: ExecuteCommand,
      ...componentsFromProps,
    };
  }, [componentsFromProps]);

  // Preprocess: escape XML tool_call/function/parameter tags that models leak into text.
  // These get rendered as HTML by the markdown parser, so we escape them to plain text.
  // Only process outside markdown code blocks to avoid breaking execute_command cards.
  const cleanContent = useMemo(() => {
    const parts = content.split(/(```[\s\S]*?```)/g);
    const cleaned = parts.map((part, idx) => {
      if (idx % 2 === 1) return part; // skip code blocks
      // Escape <tool_call>, <function=...>, <parameter=...> and their closing tags
      return part
        .replace(/<(\/?)(tool_call|function|parameter)([^>]*)>/g, '&lt;$1$2$3&gt;')
        .replace(/\n{3,}/g, '\n\n');
    });
    return cleaned.join('').trim();
  }, [content]);

  if (!content) return null;

  return (
    <MessageResponse
      className={cn(
        "text-[13px] leading-[1.7] text-zinc-800 dark:text-zinc-200",
        // Paragraphs
        "[&_p]:mb-3 [&_p:last-child]:mb-0",
        // Headings
        "[&_h1]:mb-3 [&_h1]:mt-6 [&_h1]:text-xl [&_h1]:font-bold [&_h1]:tracking-tight [&_h1]:text-zinc-900 dark:[&_h1]:text-zinc-100",
        "[&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-lg [&_h2]:font-bold [&_h2]:tracking-tight [&_h2]:text-zinc-900 dark:[&_h2]:text-zinc-100",
        "[&_h3]:mb-1.5 [&_h3]:mt-4 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:tracking-tight [&_h3]:text-zinc-900 dark:[&_h3]:text-zinc-100",
        "[&_h4]:mb-1 [&_h4]:mt-3 [&_h4]:text-sm [&_h4]:font-semibold [&_h4]:tracking-tight [&_h4]:text-zinc-900 dark:[&_h4]:text-zinc-100",
        // Lists
        "[&_ul]:mb-3 [&_ul]:ml-5 [&_ul]:list-disc [&_ul_li]:pl-1 [&_ul_li]:mb-1.5",
        "[&_ol]:mb-3 [&_ol]:ml-5 [&_ol]:list-decimal [&_ol_li]:pl-1 [&_ol_li]:mb-1.5",
        // Blockquotes
        "[&_blockquote]:border-l-4 [&_blockquote]:border-zinc-300 [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-zinc-500 dark:[&_blockquote]:border-zinc-700 dark:[&_blockquote]:text-zinc-400",
        // Links
        "[&_a]:text-primary [&_a]:underline-offset-4 hover:[&_a]:underline",
        // Bold/Strong
        "[&_strong]:font-semibold [&_strong]:text-zinc-900 dark:[&_strong]:text-zinc-100",
        // Tables
        "[&_table]:w-full [&_table]:mb-4 [&_table]:border-collapse",
        "[&_th]:border [&_th]:border-zinc-200 dark:[&_th]:border-zinc-700 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_th]:bg-zinc-50 dark:[&_th]:bg-zinc-800",
        "[&_td]:border [&_td]:border-zinc-200 dark:[&_td]:border-zinc-700 [&_td]:px-3 [&_td]:py-2",
        // Code blocks
        "[&_pre]:mb-4 [&_pre]:rounded-lg [&_pre]:bg-zinc-900 [&_pre]:p-4",
        "[&_pre_code]:text-zinc-100 [&_pre_code]:text-sm",
        // Horizontal rules
        "[&_hr]:my-6 [&_hr]:border-zinc-200 dark:[&_hr]:border-zinc-700",
        className,
      )}
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
    >
      {cleanContent}
    </MessageResponse>
  );
}
