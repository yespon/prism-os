import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as testingLibrary from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import { I18nProvider } from "@/core/i18n/context";

function TestProviders({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return (
    <I18nProvider initialLocale="zh-CN">
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </I18nProvider>
  );
}

export * from "@testing-library/react";

export function render(ui: ReactElement, options?: testingLibrary.RenderOptions) {
  document.cookie = "locale=zh-CN; path=/";
  return testingLibrary.render(ui, { wrapper: TestProviders, ...options });
}
