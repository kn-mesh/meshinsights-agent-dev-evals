import { describe, expect, it } from "vitest";
import { spiraxEvidenceSchema } from "./evidence.schema";

describe("spiraxEvidenceSchema", () => {
  it("accepts a normalized evidence package", () => {
    const result = spiraxEvidenceSchema.parse({
      selected_alarm: { alarm_id: "alarm-1" },
      asset: { sensor_id: 7 },
      telemetry: [{
        timestamp: "2026-03-17T12:00:00+00:00",
        steam_temperature: 130,
        condensate_temperature: 105,
        temperature_delta: 25,
        front_mic: 0,
      }],
      alarm_markers: {},
      coverage: { telemetry_point_count: 1 },
      known_gaps: [],
    });

    expect(result.telemetry[0].temperature_delta).toBe(25);
  });

  it("rejects an unnormalized telemetry value", () => {
    const result = spiraxEvidenceSchema.safeParse({
      selected_alarm: {},
      asset: {},
      telemetry: [{
        timestamp: "2026-03-17T12:00:00+00:00",
        steam_temperature: "130",
        condensate_temperature: null,
        temperature_delta: null,
        front_mic: null,
      }],
      alarm_markers: {},
      coverage: {},
      known_gaps: [],
    });

    expect(result.success).toBe(false);
  });
});
