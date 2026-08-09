import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { QueryProvider } from "./query-provider";

describe("QueryProvider", () => {
  it("keeps the initial server render visible", () => {
    const html = renderToString(
      <QueryProvider>
        <main>Application content</main>
      </QueryProvider>,
    );

    expect(html).toContain("Application content");
  });
});
