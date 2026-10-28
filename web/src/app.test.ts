// @vitest-environment jsdom

import { fireEvent, waitFor } from "@testing-library/dom";
import { describe, expect, test, vi } from "vitest";

import { httpApi, mountApp, type RoverEdgeApi, type RunResult, type Scenario } from "./app";

const configuration = {
  simulation_step_s: 0.05,
  physics_step_s: 0.005,
  planning_period_s: 0.05,
  rover_radius_m: 0.2,
  motion: { max_linear_speed_mps: 0.6, max_angular_speed_radps: 0.8 },
  max_linear_acceleration_mps2: 0.8,
  max_braking_deceleration_mps2: 1.2,
  max_angular_acceleration_radps2: 1.6,
  range_ray_count: 16,
  range_max_m: 4,
  route_grid_resolution_m: 0.1,
  planning_clearance_m: 0.05,
  inspection: {
    position_tolerance_m: 0.15,
    heading_tolerance_rad: 0.2617993877991494,
    dwell_s: 1,
  },
  dock: { position_tolerance_m: 0.15, heading_tolerance_rad: 0.2617993877991494 },
  timeout_s: 120,
  controller_kind: "geometric" as const,
};

const scenario: Scenario = {
  scenario_version: "preset-open-v1",
  name: "Open inspection lane",
  map_bounds_m: { width: 8, height: 6 },
  dock_pose: { x_m: 1, y_m: 3, heading_rad: 0 },
  inspection_pose: { x_m: 5.5, y_m: 3, heading_rad: 0 },
  obstacles: [],
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
    configuration,
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
    configuration,
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
  planned_routes: [
    [scenario.dock_pose, scenario.inspection_pose],
    [scenario.inspection_pose, scenario.dock_pose],
  ],
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

const collisionResult: RunResult = {
  ...result,
  run_id: "run-collision-test",
  request: { ...result.request, expected_mission_outcome: "collision" },
  trace: [
    {
      ...result.trace[0]!,
      phase: "approaching_target",
      kind: "braking_started",
      detail: "forward range requires physical deceleration",
    },
    {
      ...result.trace[0]!,
      sequence: 1,
      phase: "collision",
      kind: "collision",
      detail: "swept rover contact with obstacle near-obstacle",
    },
    {
      ...result.trace[0]!,
      sequence: 2,
      phase: "collision",
      kind: "terminal",
      detail: "swept rover contact with obstacle near-obstacle",
    },
  ],
  observations: [],
  mission_outcome: "collision",
  test_verdict: "passed",
  terminal_reason: "insufficient stopping distance before obstacle near-obstacle",
  terminal_failure: {
    code: "collision",
    message: "insufficient stopping distance before obstacle near-obstacle",
    pose: { x_m: 1.1, y_m: 3, heading_rad: 0 },
    obstacle_id: "near-obstacle",
    contact_point: { x_m: 1.3, y_m: 3 },
  },
};

describe("mission replay application", () => {
  test("starts a run and displays recorded phases and terminal evidence", async () => {
    const api: RoverEdgeApi = {
      getScenarios: async () => [scenario],
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

  test("selects a fixed obstacle scenario and runs its server-owned request", async () => {
    const narrow: Scenario = {
      ...scenario,
      scenario_version: "preset-narrow-v1",
      name: "Narrow inspection corridor",
      obstacles: [
        {
          obstacle_id: "upper-block",
          x_min_m: 2.5,
          y_min_m: 3.4,
          x_max_m: 5,
          y_max_m: 5.5,
        },
      ],
      default_run_request: {
        ...scenario.default_run_request,
        scenario_version: "preset-narrow-v1",
      },
    };
    const run = vi.fn(async () => result);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario, narrow], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.change(root.querySelector("[data-action='scenario']")!, {
      target: { value: "preset-narrow-v1" },
    });
    fireEvent.click(root.querySelector("[data-action='start']")!);

    await waitFor(() => expect(run).toHaveBeenCalledWith(narrow.default_run_request));
    expect(root.querySelector("[data-field='scenario']")?.textContent).toContain(
      "preset-narrow-v1",
    );
  });

  test("requests the learned controller and displays its model evidence", async () => {
    const learnedResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        configuration: {
          ...result.request.configuration,
          controller_kind: "learned_collision_risk",
        },
      },
      controller_kind: "learned_collision_risk",
      model_version: "risk-model-v1",
      model_sha256: "abcdef0123456789",
      validation_evidence_reference: "artifacts/issue-8/validation-report.json",
      validation_quality_gate_status: "not_met",
      trace: result.trace.map((event, index) =>
        index === 0
          ? {
              ...event,
              kind: "control_decision",
              candidate_risks: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
              selected_candidate_index: 1,
              selected_risk: 0.2,
              selected_progress_score: 0.2,
              risk_cutoff: 0.25,
              detail: "acceptable candidate with maximum kinematic progress",
            }
          : event,
      ),
    };
    const run = vi.fn(async () => learnedResult);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='learned']")!);

    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...scenario.default_run_request,
        configuration: {
          ...scenario.default_run_request.configuration,
          controller_kind: "learned_collision_risk",
        },
      }),
    );
    expect(root.querySelector("[data-field='controller']")?.textContent).toContain(
      "learned_collision_risk",
    );
    expect(root.querySelector("[data-field='model']")?.textContent).toContain("risk-model-v1");
    expect(root.querySelector("[data-field='validation']")?.textContent).toContain("not_met");
    expect(root.querySelector("[data-field='decision']")?.textContent).toContain("candidate 1");
    expect(root.querySelector("[data-field='decision']")?.textContent).toContain("cutoff 0.25");
  });

  test("requests native naive inference and displays correctness provenance", async () => {
    const nativeResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        configuration: {
          ...result.request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-naive",
        },
      },
      controller_kind: "learned_collision_risk",
      inference_backend: "native-naive",
      command_disagreements: 0,
      runtime_provenance: {
        kernel: "fresh-naive-fp32-v1",
        timing_provenance: "not_measured",
      },
    };
    const run = vi.fn(async () => nativeResult);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='native']")!);

    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...scenario.default_run_request,
        configuration: {
          ...scenario.default_run_request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-naive",
        },
      }),
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "native-naive · disagreements 0 · not_measured",
    );
  });

  test("displays recorded physical failure evidence", async () => {
    const collisionScenario: Scenario = {
      ...scenario,
      scenario_version: "fixture-collision-stop-v1",
      name: "Insufficient stopping distance fixture",
      default_run_request: collisionResult.request,
    };
    const api: RoverEdgeApi = {
      getScenarios: async () => [collisionScenario],
      run: async () => collisionResult,
    };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector("[data-action='start']")!);

    await waitFor(() => {
      expect(root.querySelector("[data-field='failure']")?.textContent).toContain("collision");
    });
    expect(root.querySelector("[data-field='status']")?.textContent).toContain(
      "stopping distance",
    );
    expect(root.querySelector("[data-field='replay-evidence']")?.textContent).toContain(
      "braking started",
    );
    expect(root.querySelector("[data-field='verdict']")?.textContent).toBe("passed");
  });

  test("browser serializes the server-owned request through the HTTP adapter", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json([scenario]))
      .mockResolvedValueOnce(Response.json(result));
    vi.stubGlobal("fetch", fetchMock);
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, httpApi);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='start']")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/scenarios");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/runs");
    const requestOptions = fetchMock.mock.calls[1]?.[1];
    expect(JSON.parse(String(requestOptions?.body))).toEqual(scenario.default_run_request);
    vi.unstubAllGlobals();
  });
});
