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
  execution_mode: "synchronous" as const,
  modeled_device: {
    dispatch_s: 0.001,
    input_transfer_s: 0.002,
    compute_s: 0.005,
    output_transfer_s: 0.002,
    pending_capacity: 2,
    deadline_s: 0.02,
    maximum_age_s: 0.1,
    queue_policy: "fifo" as const,
    requests_per_tick: 1,
    resident_weights_bytes: 14852,
    workspace_bytes: 4096,
    request_payload_bytes: 1024,
    memory_budget_bytes: 32768,
  },
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
    target: { kind: "known_target_fixture", target_id: "preset-storage-container" },
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
    target: { kind: "known_target_fixture", target_id: "preset-storage-container" },
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
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "4 m sensor range",
    );
    expect(root.querySelector("[data-field='configuration']")?.textContent).toContain(
      "32768 B modeled memory budget",
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

  test("edits a preset, confirms geometry, and selects the immutable saved version", async () => {
    const saved: Scenario = {
      ...scenario,
      scenario_version: "scene-0123456789abcdef",
      name: "Edited inspection room",
      pixels_per_meter: 120,
      source_version: scenario.scenario_version,
      target: { ...scenario.target, label: "Blue barrel" },
      default_run_request: {
        ...scenario.default_run_request,
        scenario_version: "scene-0123456789abcdef",
      },
    };
    const getSceneDraft = vi.fn(async () => ({
      name: scenario.name,
      width_m: 8,
      height_m: 6,
      pixels_per_meter: 100,
      dock_pose: scenario.dock_pose,
      obstacles: scenario.obstacles,
      targets: [
        {
          object_id: "red-toolbox",
          label: "Red toolbox" as const,
          x_min_m: 5.8,
          y_min_m: 2.2,
          x_max_m: 7.2,
          y_max_m: 3.8,
          color_rgb: [196, 54, 45] as [number, number, number],
        },
        {
          object_id: "blue-barrel",
          label: "Blue barrel" as const,
          x_min_m: 3.8,
          y_min_m: 4,
          x_max_m: 5.2,
          y_max_m: 5.6,
          color_rgb: [42, 92, 168] as [number, number, number],
        },
      ],
      source_version: scenario.scenario_version,
    }));
    const saveSceneVersion = vi.fn(async (_draft: import("./app").SceneDraft) => saved);
    const api: RoverEdgeApi = {
      getScenarios: async () => [scenario],
      getSceneDraft,
      saveSceneVersion,
      run: async () => result,
    };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector("[data-scene-action='preset']")!);
    await waitFor(() => expect(getSceneDraft).toHaveBeenCalledWith(scenario.scenario_version));
    fireEvent.input(root.querySelector("[data-editor='name']")!, {
      target: { value: "Edited inspection room" },
    });
    fireEvent.input(root.querySelector("[data-editor='scale']")!, {
      target: { value: "120" },
    });
    expect(root.querySelector<HTMLCanvasElement>("[data-field='scene-preview']")?.width).toBe(
      960,
    );
    fireEvent.input(root.querySelector("[data-editor='obstacle']")!, {
      target: { value: "2,0.5,2.5,1.5" },
    });
    fireEvent.click(root.querySelector("[data-scene-action='save']")!);

    await waitFor(() => expect(saveSceneVersion).toHaveBeenCalled());
    expect(root.querySelector("[data-field='scene-validation']")?.textContent).toContain(
      "scene-0123456789abcdef",
    );
    expect(root.querySelector("[data-field='scene-validation']")?.textContent).toContain(
      '--phrase "blue barrel"',
    );
    expect(root.querySelector<HTMLSelectElement>("[data-action='scenario']")?.value).toBe(
      "scene-0123456789abcdef",
    );
    expect(saveSceneVersion.mock.calls[0]![0]).toMatchObject({
      name: "Edited inspection room",
      pixels_per_meter: 120,
      source_version: scenario.scenario_version,
      obstacles: [{ obstacle_id: "edited-obstacle-1" }],
      targets: [
        { label: "Red toolbox", color_rgb: [196, 54, 45] },
        { label: "Blue barrel", color_rgb: [42, 92, 168] },
      ],
    });
  });

  test("turns an uploaded photo draft into a corrected saved mission", async () => {
    const photoDraft = {
      method: "rough_color_region_proposals_v1" as const,
      claim: "heuristic draft only; no automatic metric or hidden-geometry reconstruction",
      photo_reference: {
        sha256: "a".repeat(64),
        url: `/api/photo-references/${"a".repeat(64)}`,
        media_type: "image/png",
      },
      uncertainty: ["Scale is not measured.", "Dock pose must be confirmed."],
      draft: {
        name: "Photo warehouse",
        width_m: 8,
        height_m: 6,
        pixels_per_meter: 100,
        dock_pose: { x_m: 1, y_m: 3, heading_rad: 0 },
        obstacles: [],
        targets: [
          {
            object_id: "photo-red-target",
            label: "Red toolbox" as const,
            x_min_m: 5.5,
            y_min_m: 2.2,
            x_max_m: 7,
            y_max_m: 3.8,
            color_rgb: [196, 54, 45] as [number, number, number],
          },
        ],
        source_version: null,
        photo_reference_sha256: "a".repeat(64),
      },
    };
    const saved: Scenario = {
      ...scenario,
      scenario_version: "scene-photo-confirmed",
      name: "Photo warehouse",
      photo_reference_sha256: "a".repeat(64),
      default_run_request: {
        ...scenario.default_run_request,
        scenario_version: "scene-photo-confirmed",
      },
    };
    const createPhotoDraft = vi.fn(async () => photoDraft);
    const saveSceneVersion = vi.fn(async (_draft: import("./app").SceneDraft) => saved);
    const run = vi.fn(async () => ({ ...result, request: saved.default_run_request }));
    const api: RoverEdgeApi = {
      getScenarios: async () => [scenario],
      getSceneDraft: async () => photoDraft.draft,
      createPhotoDraft,
      saveSceneVersion,
      run,
    };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    const upload = root.querySelector<HTMLInputElement>("[data-action='photo-upload']")!;
    fireEvent.change(upload, {
      target: { files: [new File(["representative photo"], "warehouse.png", { type: "image/png" })] },
    });
    fireEvent.click(root.querySelector("[data-scene-action='photo-draft']")!);
    await waitFor(() => expect(createPhotoDraft).toHaveBeenCalled());
    expect(root.querySelector("[data-field='photo-draft-status']")?.textContent).toContain(
      "no automatic metric",
    );
    expect(root.querySelector<HTMLImageElement>("[data-field='photo-reference']")?.src).toContain(
      photoDraft.photo_reference.url,
    );

    fireEvent.input(root.querySelector("[data-editor='scale']")!, {
      target: { value: "120" },
    });
    fireEvent.click(root.querySelector("[data-scene-action='save']")!);
    expect(saveSceneVersion).not.toHaveBeenCalled();
    expect(root.querySelector("[data-field='scene-validation']")?.textContent).toContain(
      "Confirm the photo draft scale",
    );
    root.querySelectorAll<HTMLInputElement>("[data-photo-confirmation]").forEach((input) => {
      fireEvent.click(input);
    });
    fireEvent.input(root.querySelector("[data-editor='dock-x']")!, {
      target: { value: "0.8" },
    });
    fireEvent.click(root.querySelector("[data-scene-action='save']")!);
    expect(saveSceneVersion).not.toHaveBeenCalled();
    fireEvent.click(root.querySelector("[data-photo-confirmation='dock']")!);
    fireEvent.click(root.querySelector("[data-scene-action='save']")!);
    await waitFor(() => expect(saveSceneVersion).toHaveBeenCalled());
    expect(saveSceneVersion.mock.calls[0]![0]).toMatchObject({
      pixels_per_meter: 120,
      photo_reference_sha256: "a".repeat(64),
    });
    const reopenedReference = root.querySelector<HTMLImageElement>("[data-field='photo-reference']")!;
    reopenedReference.hidden = true;
    fireEvent.click(root.querySelector("[data-scene-action='preset']")!);
    await waitFor(() => expect(reopenedReference.hidden).toBe(false));
    expect(reopenedReference.src).toContain(`/api/photo-references/${"a".repeat(64)}`);
    fireEvent.click(root.querySelector("[data-action='start']")!);
    await waitFor(() => expect(run).toHaveBeenCalledWith(saved.default_run_request));
    fireEvent.click(root.querySelector("[data-action='grounded-recorded']")!);
    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...saved.default_run_request,
        target: {
          kind: "visual_target",
          phrase: "red toolbox",
          grounding_source: "recorded",
        },
      }),
    );
  });

  test("submits a recorded visual target and displays grounding provenance", async () => {
    const groundedResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        target: {
          kind: "visual_target",
          phrase: "red toolbox",
          grounding_source: "recorded",
        },
      },
      grounding_evidence: {
        source: "recorded",
        status: "matched",
        provider: "meta-model-api",
        model: "sam-3.1",
        parser_version: "meta-sam-parser-0.1.0",
        target_phrase: "red toolbox",
        render_sha256: "abcdef0123456789",
        render_width_px: 800,
        render_height_px: 600,
        duration_s: 0.2,
        raw_output_sha256: "1234567890abcdef",
        selected_match_ordinal: 0,
        diagnostics: [],
        matches: [
          {
            ordinal: 0,
            box_px: [583, 250, 718, 354],
            confidence: 0.95,
            mask: {
              width_px: 800,
              height_px: 600,
              counts: [480000],
              encoding: "row_major_rle_v1",
            },
          },
        ],
      },
    };
    const run = vi.fn(async () => groundedResult);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector("[data-action='grounded-recorded']")!);

    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...scenario.default_run_request,
        target: {
          kind: "visual_target",
          phrase: "red toolbox",
          grounding_source: "recorded",
        },
      }),
    );
    expect(root.querySelector("[data-field='grounding']")?.textContent).toContain(
      "recorded · matched · sam-3.1",
    );
    const preview = root.querySelector<HTMLElement>("[data-field='grounding-preview']")!;
    expect(preview.hidden).toBe(false);
    expect(preview.dataset.renderSha256).toBe("abcdef0123456789");
    expect(preview.querySelector("figcaption")?.textContent).toContain(
      "recorded sam-3.1 mask over render abcdef0123456789",
    );
  });

  test("runs an ordered multi-target mission and displays per-target progress", async () => {
    const multiResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        target: {
          kind: "multi_target_fixture",
          target_ids: ["preset-storage-container", "secondary-inspection-point"],
        },
      },
      target_visits: [
        {
          target_id: "preset-storage-container",
          required_ordinal: 0,
          pose: { x_m: 5.5, y_m: 3, heading_rad: 0 },
          dwell_completed: true,
          status: "captured",
          observation_sequence: 0,
        },
        {
          target_id: "secondary-inspection-point",
          required_ordinal: 1,
          pose: null,
          dwell_completed: false,
          status: "not_visited_timeout",
          observation_sequence: null,
        },
      ],
      mission_outcome: "timed_out",
      test_verdict: "passed",
    };
    const run = vi.fn(async () => multiResult);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector("[data-action='multi-target']")!);

    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...scenario.default_run_request,
        target: {
          kind: "multi_target_fixture",
          target_ids: ["preset-storage-container", "secondary-inspection-point"],
        },
      }),
    );
    expect(root.querySelector("[data-field='target-visits']")?.textContent).toContain(
      "preset-storage-container: captured",
    );
    expect(root.querySelector("[data-field='target-visits']")?.textContent).toContain(
      "secondary-inspection-point: not_visited_timeout",
    );
    expect(root.querySelector("[data-field='outcome']")?.textContent).toBe("timed_out");
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
              observation_age_s: 0.05,
              timing_provenance: "modeled",
              inference_event_kind: "consumed",
              queue_depth: 1,
              request_id: 7,
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
    expect(root.querySelector("[data-field='prediction-age']")?.textContent).toBe(
      "0.050 s · modeled",
    );
    expect(root.querySelector("[data-field='queue-state']")?.textContent).toBe(
      "consumed · depth 1 · request 7",
    );
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

  test("launches native paced inference and displays measured timing evidence", async () => {
    const pacedResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        configuration: {
          ...result.request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-naive",
          execution_mode: "native_paced",
        },
      },
      controller_kind: "learned_collision_risk",
      inference_backend: "native-naive",
      command_disagreements: 0,
      inference_summary: {
        execution_mode: "native_paced",
        timing_provenance: "measured",
        pacing_overruns: 1,
        maximum_pacing_overrun_s: 0.003,
      },
      trace: [
        ...result.trace,
        {
          ...result.trace.at(-1)!,
          sequence: result.trace.length,
          kind: "inference_event",
          inference_event_kind: "completed",
          request_id: 4,
          observation_id: 4,
          timing_provenance: "measured",
          measured_execution_s: 0.00125,
        },
        {
          ...result.trace.at(-1)!,
          sequence: result.trace.length + 1,
          kind: "control_decision",
          request_id: 4,
          observation_id: 4,
          observation_age_s: 0.05,
          timing_provenance: "measured",
        },
      ],
    };
    const run = vi.fn(async () => pacedResult);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='native-paced']")!);

    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...scenario.default_run_request,
        configuration: {
          ...scenario.default_run_request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-naive",
          execution_mode: "native_paced",
        },
      }),
    );
    expect(root.querySelector("[data-field='native-paced']")?.textContent).toContain(
      "measured native paced · execution 0.001250 s · observation age 0.050 s · request 4 · observation 4 · overruns 1",
    );
  });

  test("labels modeled memory separately and shows rejection recovery evidence", async () => {
    const modeledResult: RunResult = {
      ...result,
      inference_summary: {
        timing_provenance: "modeled",
        resident_weights_bytes: 14852,
        workspace_bytes: 4096,
        pending_payload_bytes: 0,
        in_flight_payload_bytes: 0,
        current_modeled_memory_bytes: 18948,
        peak_modeled_memory_bytes: 19972,
        memory_budget_bytes: 19972,
        memory_rejections: 2,
      },
    };
    const run = vi.fn(async () => modeledResult);
    const api: RoverEdgeApi = {
      getScenarios: async () => [scenario],
      run,
    };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.input(root.querySelector<HTMLInputElement>("[data-action='memory-budget']")!, {
      target: { value: "19972" },
    });
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='modeled-memory']")!);

    await waitFor(() => expect(run).toHaveBeenCalledOnce());
    expect(run).toHaveBeenCalledWith({
      ...scenario.default_run_request,
      configuration: {
        ...scenario.default_run_request.configuration,
        controller_kind: "learned_collision_risk",
        execution_mode: "virtual_fifo",
        modeled_device: {
          ...scenario.default_run_request.configuration.modeled_device,
          memory_budget_bytes: 19972,
        },
      },
    });
    expect(root.querySelector("[data-field='modeled-memory']")?.textContent).toContain(
      "modeled allocation · resident weights 14852 B",
    );
    expect(root.querySelector("[data-field='modeled-memory']")?.textContent).toContain(
      "rejections 2 · recovered request payloads",
    );
    expect(root.querySelector("[data-field='modeled-memory']")?.textContent).not.toContain(
      "RSS",
    );
  });

  test("round-trips configured runs, classifies differences, and preserves success on error", async () => {
    let runNumber = 0;
    const run = vi.fn(async (request: RunResult["request"]): Promise<RunResult> => {
      if (request.configuration.rover_radius_m <= 0) {
        throw new Error("rover radius must be positive");
      }
      runNumber += 1;
      return {
        ...result,
        run_id: `configured-${runNumber}`,
        request: structuredClone(request),
        configuration_validity: {
          configuration_id: `config-${runNumber}`,
          rover_type: "differential_drive",
          model_feature_count: 24,
          training_domain_status:
            request.configuration.rover_radius_m === 0.2 ? "inside" : "outside",
          warnings:
            request.configuration.rover_radius_m === 0.2
              ? []
              : ["rover radius differs from the training condition"],
        },
      };
    });
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);
    await waitFor(() => expect(root.querySelector("[data-field='run-id']")?.textContent).toBe("configured-1"));
    expect(root.querySelector("[data-field='configuration-validity']")?.textContent).toContain(
      "fixed differential_drive · fixed 24-feature model · training domain inside",
    );

    fireEvent.input(root.querySelector("[data-setting='rover-radius']")!, {
      target: { value: "0.25" },
    });
    fireEvent.change(root.querySelector("[data-action='comparison-mode']")!, {
      target: { value: "controlled" },
    });
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);
    await waitFor(() => expect(root.querySelector("[data-field='run-id']")?.textContent).toBe("configured-2"));
    expect(root.querySelector("[data-field='comparison-validity']")?.textContent).toBe(
      "Controlled comparison valid · declared factor configuration.rover_radius_m",
    );
    expect(root.querySelector("[data-field='comparison-evidence']")?.textContent).toContain(
      "before configured-1 · model not used · numerical disagreements not compared · runtime not measured · mission completed · test passed | after configured-2",
    );
    expect(root.querySelector("[data-field='comparison-time']")?.textContent).toBe(
      "before 0.00 s · after 0.00 s",
    );
    expect(run.mock.calls[1]?.[0].expected_mission_outcome).toBe("completed");

    fireEvent.input(root.querySelector("[data-setting='sensor-range']")!, {
      target: { value: "3.5" },
    });
    fireEvent.input(root.querySelector("[data-setting='planning-period']")!, {
      target: { value: "0.1" },
    });
    fireEvent.change(root.querySelector("[data-action='comparison-mode']")!, {
      target: { value: "exploratory" },
    });
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);
    await waitFor(() => expect(root.querySelector("[data-field='run-id']")?.textContent).toBe("configured-3"));
    expect(root.querySelector("[data-field='comparison-validity']")?.textContent).toContain(
      "Exploratory comparison · 2 changed settings: configuration.planning_period_s, configuration.range_max_m",
    );
    expect(root.querySelector("[data-field='comparison-validity']")?.textContent).toContain(
      "no isolated-cause claim permitted",
    );

    fireEvent.input(root.querySelector("[data-setting='rover-radius']")!, {
      target: { value: "0" },
    });
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);
    await waitFor(() =>
      expect(root.querySelector("[data-field='configuration-error']")?.textContent).toBe(
        "rover radius must be positive",
      ),
    );
    expect(root.querySelector("[data-field='run-id']")?.textContent).toBe("configured-3");
    expect(root.querySelector("[data-field='expectation']")?.textContent).toBe("completed");
  });

  test("rejects a controlled declaration when additional request paths change", async () => {
    let count = 0;
    const run = vi.fn(async (request: RunResult["request"]): Promise<RunResult> => ({
      ...result,
      run_id: `comparison-${++count}`,
      request: structuredClone(request),
    }));
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    fireEvent.change(root.querySelector("[data-action='comparison-mode']")!, {
      target: { value: "controlled" },
    });
    fireEvent.input(root.querySelector("[data-setting='rover-radius']")!, {
      target: { value: "0.25" },
    });
    fireEvent.input(root.querySelector("[data-setting='sensor-range']")!, {
      target: { value: "3.5" },
    });
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);

    await waitFor(() => expect(run).toHaveBeenCalledTimes(2));
    expect(root.querySelector("[data-field='comparison-validity']")?.textContent).toContain(
      "Controlled comparison invalid · declared configuration.rover_radius_m · actual differences: configuration.range_max_m, configuration.rover_radius_m",
    );
    expect(root.querySelector("[data-field='comparison-validity']")?.textContent).toContain(
      "no isolated-cause claim permitted",
    );
  });

  test("includes scenario identity in comparison validity", async () => {
    const narrow: Scenario = {
      ...scenario,
      scenario_version: "preset-narrow-v1",
      name: "Narrow inspection corridor",
      default_run_request: {
        ...scenario.default_run_request,
        scenario_version: "preset-narrow-v1",
      },
    };
    const run = vi.fn(async (request: RunResult["request"]): Promise<RunResult> => ({
      ...result,
      request,
    }));
    const api: RoverEdgeApi = { getScenarios: async () => [scenario, narrow], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);
    await waitFor(() => expect(run).toHaveBeenCalledTimes(1));
    fireEvent.change(root.querySelector("[data-action='scenario']")!, {
      target: { value: "preset-narrow-v1" },
    });
    fireEvent.input(root.querySelector("[data-setting='rover-radius']")!, {
      target: { value: "0.25" },
    });
    fireEvent.click(root.querySelector("[data-action='configured-run']")!);

    await waitFor(() => expect(run).toHaveBeenCalledTimes(2));
    expect(root.querySelector("[data-field='comparison-validity']")?.textContent).toContain(
      "Exploratory comparison · 2 changed settings: configuration.rover_radius_m, scenario_version",
    );
  });

  test("displays the correctness-gated blocked versus naive latency comparison", async () => {
    const blockedResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        configuration: {
          ...result.request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-blocked",
        },
      },
      controller_kind: "learned_collision_risk",
      inference_backend: "native-blocked",
      command_disagreements: 0,
      runtime_provenance: {
        comparison_correctness: "passed",
        timing_provenance: "measured_saved_input_replay",
        kernel: "fresh-blocked-fp32-v1",
        block_size: "16",
        saved_input_sha256: "007cd77405e48b5ed82d6b5c21b3ef1",
        comparison_evidence: "artifacts/issue-10/native-blocked-comparison.json",
        naive_median_us: "210.167",
        blocked_median_us: "194.542",
      },
    };
    const run = vi.fn(async () => blockedResult);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='blocked']")!);

    await waitFor(() => expect(run).toHaveBeenCalledOnce());
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "measured_saved_input_replay",
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "naive 210.167 µs median · blocked 194.542 µs median",
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "correctness passed · fresh-blocked-fp32-v1 · block 16",
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "artifacts/issue-10/native-blocked-comparison.json",
    );
  });

  test("runs parallel blocked inference and displays worker overhead honestly", async () => {
    const parallelResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        configuration: {
          ...result.request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-parallel-blocked",
          inference_workers: 4,
        },
      },
      controller_kind: "learned_collision_risk",
      inference_backend: "native-parallel-blocked",
      command_disagreements: 0,
      runtime_provenance: {
        comparison_correctness: "passed",
        timing_provenance: "measured_saved_input_replay",
        kernel: "fresh-parallel-blocked-fp32-v1",
        block_size: "16",
        worker_count: "4",
        saved_input_sha256: "007cd77405e48b5ed82d6b5c21b3ef1",
        comparison_evidence: "artifacts/issue-11/native-parallel-comparison.json",
        serial_blocked_median_us: "198.0415",
        parallel_median_us: "314.9375",
      },
    };
    const run = vi.fn(async () => parallelResult);
    const api: RoverEdgeApi = { getScenarios: async () => [scenario], run };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='parallel']")!);

    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...scenario.default_run_request,
        configuration: {
          ...scenario.default_run_request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-parallel-blocked",
          inference_workers: 4,
        },
      }),
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "workers 4 · serial blocked 198.0415 µs median · parallel 314.9375 µs median",
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "artifacts/issue-11/native-parallel-comparison.json",
    );
  });

  test("runs Accelerate and labels the recorded M1 comparison", async () => {
    const accelerateResult: RunResult = {
      ...result,
      request: {
        ...result.request,
        configuration: {
          ...result.request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-accelerate",
        },
      },
      controller_kind: "learned_collision_risk",
      inference_backend: "native-accelerate",
      command_disagreements: 0,
      runtime_provenance: {
        accelerate_available: "true",
        comparison_correctness: "passed",
        timing_provenance: "measured_saved_input_replay",
        kernel: "apple-accelerate-cblas-sgemm",
        block_size: "16",
        saved_input_sha256: "007cd77405e48b5ed82d6b5c21b3ef1",
        comparison_evidence: "artifacts/issue-12/native-accelerate-comparison.json",
        recorded_hardware_model: "Apple M1 Pro",
        naive_median_us: "25.416",
        accelerate_median_us: "24.042",
      },
    };
    const run = vi.fn(async () => accelerateResult);
    const api: RoverEdgeApi = {
      getScenarios: async () => [scenario],
      getAccelerateComparison: async () => ({
        available_locally: true,
        recorded_result: {
          hardware_model: "Apple M1 Pro",
          correctness_gate: "passed",
          timing_provenance: "measured_saved_input_replay",
          latency: {
            "native-naive": { median_us: 25.416, samples: 3000 },
            "native-accelerate": { median_us: 24.042, samples: 3000 },
          },
        },
      }),
      run,
    };
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='accelerate']")!);

    await waitFor(() =>
      expect(run).toHaveBeenCalledWith({
        ...scenario.default_run_request,
        configuration: {
          ...scenario.default_run_request.configuration,
          controller_kind: "learned_collision_risk",
          inference_backend: "native-accelerate",
        },
      }),
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "recorded Apple M1 Pro · naive 25.416 µs median · Accelerate 24.042 µs median",
    );
    expect(root.querySelector("[data-field='runtime']")?.textContent).toContain(
      "artifacts/issue-12/native-accelerate-comparison.json",
    );
    expect(root.querySelector("[data-field='accelerate-comparison']")?.textContent).toContain(
      "available locally · recorded Apple M1 Pro · correctness passed",
    );
  });

  test("disables live Accelerate execution when the backend is unavailable", async () => {
    const api: RoverEdgeApi = {
      getScenarios: async () => [scenario],
      getAccelerateComparison: async () => ({
        available_locally: false,
        recorded_result: {
          hardware_model: "Apple M1 Pro",
          correctness_gate: "passed",
          timing_provenance: "measured_saved_input_replay",
          latency: {
            "native-naive": { median_us: 25.416, samples: 3000 },
            "native-accelerate": { median_us: 24.042, samples: 3000 },
          },
        },
      }),
      run: vi.fn(async () => result),
    };
    document.body.innerHTML = '<main id="app"></main>';
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, api);

    expect(root.querySelector<HTMLButtonElement>("[data-action='accelerate']")?.disabled).toBe(true);
    expect(root.querySelector("[data-field='accelerate-comparison']")?.textContent).toContain(
      "unavailable locally · recorded Apple M1 Pro",
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
      .mockResolvedValueOnce(
        Response.json({
          available_locally: false,
          recorded_result: {
            hardware_model: "Apple M1 Pro",
            correctness_gate: "passed",
            timing_provenance: "measured_saved_input_replay",
            latency: {
              "native-naive": { median_us: 25.416, samples: 3000 },
              "native-accelerate": { median_us: 24.042, samples: 3000 },
            },
          },
        }),
      )
      .mockResolvedValueOnce(Response.json(result));
    vi.stubGlobal("fetch", fetchMock);
    document.body.innerHTML = '<main id="app"></main>';
    HTMLCanvasElement.prototype.getContext = () => null;
    const root = document.querySelector<HTMLElement>("#app")!;

    await mountApp(root, httpApi);
    fireEvent.click(root.querySelector<HTMLButtonElement>("[data-action='start']")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/scenarios");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/native-comparisons/accelerate");
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/runs");
    const requestOptions = fetchMock.mock.calls[2]?.[1];
    expect(JSON.parse(String(requestOptions?.body))).toEqual(scenario.default_run_request);
    vi.unstubAllGlobals();
  });

  test("HTTP adapter exposes FastAPI validation messages", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json(
        { detail: [{ msg: "Value error, rover radius must be positive" }] },
        { status: 422 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(httpApi.run(scenario.default_run_request)).rejects.toThrow(
      "Value error, rover radius must be positive",
    );

    vi.unstubAllGlobals();
  });
});
