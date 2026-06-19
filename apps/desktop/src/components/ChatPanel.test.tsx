/** Phase 10 — ChatPanel render test (per ban_ke_hoach.md §Phase 10.1).
 *
 * Smoke test: render the panel with no messages, expect the empty-state
 * hint; then render with messages, expect them in the DOM.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ChatPanel } from "../components/ChatPanel";

describe("<ChatPanel>", () => {
  it("shows the empty-state hint when there are no messages", () => {
    render(
      <ChatPanel
        messages={[]}
        toolCalls={[]}
        disabled={false}
        onSend={vi.fn()}
      />,
    );
    expect(screen.getByText(/Chat/i)).toBeInTheDocument();
    expect(screen.getByText(/Chưa có message/i)).toBeInTheDocument();
  });

  it("renders messages passed in props", () => {
    render(
      <ChatPanel
        messages={[
          {
            id: "m1",
            sender: "user",
            content: "Mở Notepad",
            createdAt: Date.parse("2026-06-19T12:00:00Z"),
          },
          {
            id: "m2",
            sender: "assistant",
            content: "Đã mở Notepad.",
            createdAt: Date.parse("2026-06-19T12:00:05Z"),
          },
        ]}
        toolCalls={[]}
        disabled={false}
        onSend={vi.fn()}
      />,
    );
    expect(screen.getByText("Mở Notepad")).toBeInTheDocument();
    expect(screen.getByText("Đã mở Notepad.")).toBeInTheDocument();
  });

  it("disables the input when disabled=true", () => {
    render(
      <ChatPanel
        messages={[]}
        toolCalls={[]}
        disabled={true}
        onSend={vi.fn()}
      />,
    );
    const input = screen.getByRole("textbox");
    expect(input).toBeDisabled();
  });
});
