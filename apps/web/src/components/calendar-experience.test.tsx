import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CalendarExperience } from "@/components/calendar-experience";

describe("CalendarExperience", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("keeps demo mutations behind a sign-in gate", () => {
    render(<CalendarExperience mode="demo" />);
    fireEvent.click(screen.getByRole("button", { name: /fit in study time/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/demo is safely read-only/i)).toBeInTheDocument();
  });

  it("places voice transcription in the composer without applying changes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ transcript: "Move gym after my lab on Wednesday.", detected_language: "en" }),
    }));
    render(<CalendarExperience mode="dashboard" />);
    const input = document.querySelector("#voice-recording-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["audio"], "note.webm", { type: "audio/webm" })] } });
    await waitFor(() => expect(screen.getByRole("textbox", { name: /message ai planner/i })).toHaveValue(
        "Move gym after my lab on Wednesday.",
      ));
    expect(screen.queryByText("Applied")).not.toBeInTheDocument();
  });

  it("shows an editable review before importing image events", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "plan-1",
        summary: "Import two events",
        changes: [{ type: "create", title: "Product strategy workshop" }, { type: "create", title: "Career fair" }],
        conflicts: [],
        warnings: [],
        status: "pending",
        expires_at: "2026-08-01T00:00:00Z",
      }),
    }));
    render(<CalendarExperience mode="dashboard" />);
    const input = document.querySelector("#schedule-image-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["image"], "schedule.png", { type: "image/png" })] } });
    expect(await screen.findByRole("heading", { name: /review extracted events/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Product strategy workshop")).toBeInTheDocument();
  });
});
