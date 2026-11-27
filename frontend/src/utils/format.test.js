import { describe, expect, it } from "vitest";
import { formatInr, formatPercent, humanize, toRupees } from "./format";

describe("formatInr", () => {
  it("uses lakh and crore", () => {
    expect(formatInr(8500000)).toBe("₹85 L");
    expect(formatInr(8550000)).toBe("₹85.5 L");
    expect(formatInr(12000000)).toBe("₹1.20 Cr");
  });
  it("handles missing values", () => {
    expect(formatInr(null)).toBe("—");
    expect(formatInr(undefined)).toBe("—");
  });
  it("formats small amounts with Indian grouping", () => {
    expect(formatInr(25000)).toBe("₹25,000");
  });
});

describe("other helpers", () => {
  it("formats percentages", () => {
    expect(formatPercent(0.256)).toBe("26%");
    expect(formatPercent(0.2567, 1)).toBe("25.7%");
    expect(formatPercent(null)).toBe("—");
  });
  it("humanizes snake_case", () => {
    expect(humanize("facebook_ads")).toBe("Facebook ads");
    expect(humanize(null)).toBe("—");
  });
  it("converts lakh/crore inputs to rupees", () => {
    expect(toRupees("85", "lakh")).toBe(8500000);
    expect(toRupees("1.2", "cr")).toBe(12000000);
    expect(toRupees("", "lakh")).toBeNull();
    expect(toRupees("-5", "lakh")).toBeNull();
  });
});
