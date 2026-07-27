import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EvalExplorerApp } from "@eval-ui/eval-explorer-app";
import { projectUseCaseAdapter } from "@use-case/adapter";
import "./styles.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <EvalExplorerApp adapter={projectUseCaseAdapter} />
    </QueryClientProvider>
  </React.StrictMode>,
);
