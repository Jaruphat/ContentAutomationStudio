import { describe, expect, it } from "vitest";
import { buildDiagnosticId, sanitizeErrorDetail } from "./errorDiagnostics";

describe("sanitizeErrorDetail", () => {
  it("redacts a Windows absolute path from the message", () => {
    const error = new Error(
      String.raw`Cannot read properties of undefined (reading 'map') at C:\Users\jongp\Desktop\ContentAutomationStudio\frontend\src\pages\TimelinePage.tsx:195:20`,
    );
    const { message } = sanitizeErrorDetail(error);
    expect(message).not.toMatch(/[A-Za-z]:\\/);
    expect(message).not.toContain("jongp");
    expect(message).toContain("[path]");
  });

  it("redacts a file:// URI", () => {
    const error = new Error("Failed to load file:///C:/Users/jongp/secret/config.json");
    const { message } = sanitizeErrorDetail(error);
    expect(message).not.toContain("file://");
    expect(message).not.toContain("secret");
  });

  it("redacts long token-like substrings that look like secrets", () => {
    const error = new Error(
      "Request failed with api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789",
    );
    const { message } = sanitizeErrorDetail(error);
    expect(message).not.toContain("sk-abcdefghijklmnopqrstuvwxyz0123456789");
    expect(message).toContain("[redacted]");
  });

  it("falls back to a generic message when there is no usable detail", () => {
    const { message } = sanitizeErrorDetail(new Error(""));
    expect(message.length).toBeGreaterThan(0);
  });

  it("truncates very long messages", () => {
    const error = new Error("x".repeat(5000));
    const { message } = sanitizeErrorDetail(error);
    expect(message.length).toBeLessThan(300);
  });

  it("preserves the error name", () => {
    class MyError extends Error {
      constructor(message: string) {
        super(message);
        this.name = "MyError";
      }
    }
    const { name } = sanitizeErrorDetail(new MyError("boom"));
    expect(name).toBe("MyError");
  });

  it("handles non-Error thrown values without crashing", () => {
    expect(() => sanitizeErrorDetail("just a string")).not.toThrow();
    expect(() => sanitizeErrorDetail(null)).not.toThrow();
    expect(() => sanitizeErrorDetail(undefined)).not.toThrow();
    expect(() => sanitizeErrorDetail({ weird: "object" })).not.toThrow();
  });
});

describe("buildDiagnosticId", () => {
  it("is stable for the same stage and error content", () => {
    const a = buildDiagnosticId("Timeline", new Error("Cannot read properties of undefined"));
    const b = buildDiagnosticId("Timeline", new Error("Cannot read properties of undefined"));
    expect(a).toBe(b);
  });

  it("differs for different error messages", () => {
    const a = buildDiagnosticId("Timeline", new Error("first failure"));
    const b = buildDiagnosticId("Timeline", new Error("second failure"));
    expect(a).not.toBe(b);
  });

  it("differs for different stages with the same error", () => {
    const a = buildDiagnosticId("Timeline", new Error("boom"));
    const b = buildDiagnosticId("Review", new Error("boom"));
    expect(a).not.toBe(b);
  });

  it("matches the expected ERR-XXXXXXXX shape", () => {
    const id = buildDiagnosticId("Export", new Error("boom"));
    expect(id).toMatch(/^ERR-[0-9A-F]{8}$/);
  });

  it("never leaks a path or secret into the id itself", () => {
    const id = buildDiagnosticId(
      "Generate",
      new Error(String.raw`C:\Users\jongp\secret\thing.ts sk-abcdefghijklmnopqrstuvwxyz0123456789`),
    );
    expect(id).not.toContain("jongp");
    expect(id).not.toContain("sk-abcdefghijklmnopqrstuvwxyz0123456789");
  });
});
