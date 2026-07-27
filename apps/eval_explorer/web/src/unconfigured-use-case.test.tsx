import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  UnconfiguredEvidenceDisplay,
  unconfiguredUseCaseAdapter,
} from "@eval-ui/unconfigured-use-case";
import type { EvidenceView } from "@eval-ui/contracts";


describe("neutral use-case adapter", () => {
  it("renders a precise not-configured state", () => {
    const evidence = {} as EvidenceView;
    const markup = renderToStaticMarkup(
      <UnconfiguredEvidenceDisplay evidence={evidence} />,
    );

    expect(markup).toContain("Use case not configured");
    expect(unconfiguredUseCaseAdapter.contextLabel).toBe(
      "Use case not configured",
    );
  });
});
