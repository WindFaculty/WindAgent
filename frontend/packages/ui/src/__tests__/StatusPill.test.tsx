import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "../StatusPill.tsx";

describe("StatusPill", () => {
  it("renders label and level", () => {
    render(<StatusPill level="ok" label="API healthy" />);
    const pill = screen.getByTestId("status-pill");
    expect(pill.textContent).toContain("API healthy");
    expect(pill.getAttribute("data-level")).toBe("ok");
  });
});
