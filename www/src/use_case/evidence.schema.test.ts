import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { buildEvidenceWindows, SpiraxEvidenceDisplay } from "./adapter";
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

  it("derives the model's segmented 365-day, 30-day, and 7-day views", () => {
    const alarm = "2026-03-17T12:00:00.000Z";
    const telemetry = [365, 274, 183, 92, 29, 6, 0].map((days, index) => ({
      timestamp: new Date(Date.parse(alarm) - days * 24 * 60 * 60 * 1000).toISOString(),
      steam_temperature: 130 + index,
      condensate_temperature: 100,
      temperature_delta: 30 + index,
      front_mic: 0,
    }));

    const windows = buildEvidenceWindows(telemetry, alarm);

    expect(windows.year).toHaveLength(4);
    expect(windows.year.map((item) => item.rows.length)).toEqual([2, 1, 1, 3]);
    expect(windows.month.map((item) => item.timestamp)).toEqual(telemetry.slice(4).map((item) => item.timestamp));
    expect(windows.week.map((item) => item.timestamp)).toEqual(telemetry.slice(5).map((item) => item.timestamp));

    const html = renderToStaticMarkup(createElement(SpiraxEvidenceDisplay, { evidence: {
      example: { example_id: "example-a", unit_id: "unit-a", decision_timestamp: alarm, metadata: {} },
      window: { start: telemetry[0].timestamp, end: alarm, basis: "lookback", lookback_days: 365 },
      evidence: {
        selected_alarm: {},
        asset: {},
        telemetry,
        alarm_markers: {},
        coverage: {},
        known_gaps: [],
      },
      metadata: {
        evidence_schema_version: "1",
        evidence_recipe_id: "recipe@v1",
        source_snapshot_id: "snapshot-a",
        source_snapshot_content_sha256: "hash",
        source_kind: "azure_blob",
        known_gaps: [],
      },
    } }));
    expect(html).toContain("365-day temperature history");
    expect(html).toContain("30-day alarm context");
    expect(html).toContain("7-day alarm detail");
    expect(html).toContain("alarm is at the right edge of segment 4");
  });
});
