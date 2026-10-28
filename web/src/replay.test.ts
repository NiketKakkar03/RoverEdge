import { describe, expect, test } from "vitest";

import { ReplayController, type ReplayEvent } from "./replay";

const events: ReplayEvent[] = [
  { sequence: 0, simulated_time_s: 0, phase: "approaching_target" },
  { sequence: 1, simulated_time_s: 2, phase: "dwelling" },
  { sequence: 2, simulated_time_s: 4, phase: "completed" },
];

describe("recorded replay controls", () => {
  test("pause, resume, restart, and scrub only select recorded events", () => {
    const replay = new ReplayController(events);

    expect(replay.currentEvent()).toEqual(events[0]);
    replay.play();
    replay.advanceTo(2.5);
    expect(replay.currentEvent()).toEqual(events[1]);

    replay.pause();
    replay.advanceTo(4);
    expect(replay.currentEvent()).toEqual(events[1]);

    replay.scrubTo(4);
    expect(replay.currentEvent()).toEqual(events[2]);
    replay.restart();
    expect(replay.currentEvent()).toEqual(events[0]);
    expect(replay.isPlaying()).toBe(false);
  });
});
