import type { EvidenceView, UseCaseAdapter } from "./contracts";

export function UnconfiguredEvidenceDisplay(
  { evidence: _evidence }: { evidence: EvidenceView },
) {
  return (
    <section role="status" className="m-5 rounded-lg border p-5">
      <h2 className="text-base font-semibold">Use case not configured</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Port the project evidence schema and display before reviewing evidence.
      </p>
    </section>
  );
}

export const unconfiguredUseCaseAdapter: UseCaseAdapter = {
  EvidenceDisplay: UnconfiguredEvidenceDisplay,
  contextLabel: "Use case not configured",
};
