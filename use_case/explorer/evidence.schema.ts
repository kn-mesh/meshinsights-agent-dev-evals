import { z } from "zod";

export const telemetryPointSchema = z.object({
  timestamp: z.string(),
  steam_temperature: z.number().nullable(),
  condensate_temperature: z.number().nullable(),
  temperature_delta: z.number().nullable(),
  front_mic: z.number().nullable(),
});

export const spiraxEvidenceSchema = z.object({
  selected_alarm: z.record(z.string(), z.unknown()),
  asset: z.record(z.string(), z.unknown()),
  telemetry: z.array(telemetryPointSchema),
  alarm_markers: z.record(z.string(), z.unknown()),
  coverage: z.record(z.string(), z.unknown()),
  known_gaps: z.array(z.string()),
});

export type SpiraxEvidence = z.infer<typeof spiraxEvidenceSchema>;
