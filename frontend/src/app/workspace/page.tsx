import { redirect } from "next/navigation";
import { env } from "@/env";
import { listDemoThreads } from "@/server/demo-files";

export default function WorkspacePage() {
  if (env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true") {
    const firstThread = listDemoThreads()[0];
    if (firstThread) return redirect(`/workspace/chats/${firstThread}`);
  }
  return redirect("/workspace/overview");
}
