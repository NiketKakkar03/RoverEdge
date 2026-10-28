// @vitest-environment jsdom

import { fireEvent, waitFor } from "@testing-library/dom";
import { describe, expect, test, vi } from "vitest";

import { httpApi, mountApp, type RoverEdgeApi, type RunResult, type Scenario } from "./app";

const scenario: Scenario = {
  scenario_version: "preset-open-v1",
  name: "Open inspection lane",
  map_bounds_m: { width: 8, height: 6 },
  dock_pose: { x_m: 1, y_m: 3, heading_rad: 0 },
  target: {
    id: "preset-storage-container",
    label: "Storage container",
    center_m: { x: 6.5, y: 3 },
    size_m: { width: 0.6, height: 1 },
  },
  default_run_request: {
    scenario_version: "preset-open-v1",
    target_id: "preset-storage-container",
    simulation_seed: 20261027,
    configuration: {
      simulation_step_s: 0.05,
      motion: { max_linear_speed_mps: 0.6, max_angular_speed_radps: 0.8 },
      inspection: {
        position_tolerance_m: 0.15,
        heading_tolerance_rad: 0.2617993877991494,
        dwell_s: 1,
      },
      dock: { position_tolerance_m: 0.15, heading_tolerance_rad: 0.2617993877991494 },
      timeout_s: 120,
    },
    expected_mission_outcome: "completed",
  },
};

const phases = [
  "approaching_target",
  "aligning_to_target",
  "stopping_for_inspection",
  "dwelling",
  "observation_captured",
  "returning_to_dock",
  "aligning_at_dock",
  "completed",
];

const result: RunResult = {
  run_id: "run-browser-test",
  request: {
    scenario_version: "preset-open-v1",
    target_id: "preset-storage-container",
    simulation_seed: 20261027,
    configuration: {
      simulation_step_s: 0.05,
      motion: { max_linear_speed_mps: 0.6, max_angular_speed_radps: 0.8 },
      inspection: {
        position_tolerance_m: 0.15,
        heading_tolerance_rad: 0.2617993877991494,
        dwell_s: 1,
      },
      dock: { position_tolerance_m: 0.15, heading_tolerance_rad: 0.2617993877991494 },
      timeout_s: 120,
    },
    expected_mission_outcome: "completed",
  },
  trace: phases.map((phase, sequence) => ({
    sequence,
    simulated_time_s: sequence,
    phase,
    kind: sequence === phases.length - 1 ? "terminal" : "phase_changed",
    pose: { x_m: 1 + sequence * 0.5, y_m: 3, heading_rad: 0 },
    linear_velocity_mps: 0,
    angular_velocity_radps: 0,
  })),
  observations: [
    {
      target_id: "preset-storage-container",
      pose: { x_m: 5.5, y_m: 3, heading_rad: 0 },
      simulated_time_s: 4,
      completion_status: "captured",
    },
  ],
  mission_outcome: "completed",
  test_verdict: "passed",
  terminal_reason: "inspection captured and rover returned to dock",
};

const timeoutResult: RunResult = {
  ...result,
  run_id: "run-timeout-test",
  request: {
    ...result.request,
    configuration: { ...result.request.configuration, timeout_s: 2 },
    expected_mission_outcome: "timed_out",
  },
  trace: [
    result.trace[0]!,
    {
      ...result.trace[0]!,
      sequence: 1,
      simulated_time_s: 2.05,
      phase: "timed_out",
      kind: "terminal",
    },
  ],
  observations: [],
  mission_outcome: "timed_out",
  test_verdict: "passed",
  terminal_reason: "mission exceeded its simulated-time limit",
};

describe("mission replay application", () => {
  test("starts a run and displays recorded phases and terminal evidence", async () => {
    const api: RoverEdgeApi = {
      getPresetScenario: async () => scenario,
      run: async (request) =>
        request.expected_mission_outcome === "timed_out" ? timeoutResult : result,
    };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='start']")!);

    await waitFor(() => {
      expect(root.querySelector("[data-field='outcome']")?.textContent).toContain("completed");
    });
    expect(root.querySelector("[data-field='verdict']")?.textContent).toContain("passed");
    expect(root.querySelector("[data-field='run-id']")?.textContent).toContain(
      "run-browser-test",
    );
    expect(root.querySelector("[data-field='scenario-version']")?.textContent).toContain(
      "preset-open-v1",
    );
    expect(root.querySelector("[data-field='seed']")?.textContent).toContain("20261027");
    expect(root.querySelector("[data-field='expectation']")?.textContent).toContain("completed");
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "50 ms step",
    );
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "0.8 rad/s angular max",
    );
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "inspection position tolerance",
    );
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "inspection heading tolerance",
    );
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "dock position tolerance",
    );
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "dock heading tolerance",
    );
    for (const phase of phases) {
      expect(root.querySelector("[data-field='phases']")?.textContent).toContain(phase);
    }

    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='timeout']")!);
    await waitFor(() => {
      expect(root.querySelector("[data-field='outcome']")?.textContent).toContain("timed_out");
    });
    expect(root.querySelector("[data-field='verdict']")?.textContent).toContain("passed");
    expect(root.querySelector("[data-field='expectation']")?.textContent).toContain("timed_out");
  });

  test("browser serializes the server-owned request through the HTTP adapter", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(scenario))
      .mockResolvedValueOnce(Response.json(result));
    vi.stubGlobal("fetch", fetchMock);
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, httpApi);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='start']")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/scenarios/preset-open");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/runs");
    const requestOptions = fetchMock.mock.calls[1]?.[1];
    expect(JSON.parse(String(requestOptions?.body))).toEqual(scenario.default_run_request);
    vi.unstubAllGlobals();
  });
});
