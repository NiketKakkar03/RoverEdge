import { ReplayController, type ReplayEvent } from "./replay";
import { explainRun, summarizeRun } from "./run-summary";
import { attachPresentationCamera, drawPresentationScene, resetPresentationCamera } from "./presentation-scene";

export interface Pose {
  x_m: number;
  y_m: number;
  heading_rad: number;
}

export interface Scenario {
  requested_target_label?: string;
  scenario_version: string;
  name: string;
  map_bounds_m: { width: number; height: number };
  dock_pose: Pose;
  inspection_pose: Pose;
  obstacles: Array<{
    obstacle_id: string;
    x_min_m: number;
    y_min_m: number;
    x_max_m: number;
    y_max_m: number;
  }>;
  target: {
    id: string;
    label: string;
    center_m: { x: number; y: number };
    size_m: { width: number; height: number };
  };
  default_run_request: RunRequest;
  pixels_per_meter?: number;
  source_version?: string | null;
  photo_reference_sha256?: string | null;
}

export interface SceneDraft {
  name: string;
  width_m: number;
  height_m: number;
  pixels_per_meter: number;
  dock_pose: Pose;
  obstacles: Scenario["obstacles"];
  targets: Array<{
    object_id: string;
    label: "Red toolbox" | "Blue barrel";
    x_min_m: number;
    y_min_m: number;
    x_max_m: number;
    y_max_m: number;
    color_rgb: [number, number, number];
  }>;
  source_version: string | null;
  photo_reference_sha256?: string | null;
}

export interface PhotoDraftResult {
  method: "rough_color_region_proposals_v1";
  claim: string;
  photo_reference: { sha256: string; url: string; media_type: string };
  uncertainty: string[];
  draft: SceneDraft;
}

export interface RunRequest {
  scenario_version: string;
  target:
    | { kind: "known_target_fixture"; target_id: string }
    | { kind: "multi_target_fixture"; target_ids: string[] }
    | { kind: "visual_target"; phrase: string; grounding_source: "live" | "recorded" };
  simulation_seed: number;
  configuration: {
    simulation_step_s: number;
    physics_step_s: number;
    planning_period_s: number;
    rover_radius_m: number;
    motion: { max_linear_speed_mps: number; max_angular_speed_radps: number };
    max_linear_acceleration_mps2: number;
    max_braking_deceleration_mps2: number;
    max_angular_acceleration_radps2: number;
    range_ray_count: number;
    range_max_m: number;
    route_grid_resolution_m: number;
    planning_clearance_m: number;
    inspection: {
      position_tolerance_m: number;
      heading_tolerance_rad: number;
      dwell_s: number;
    };
    dock: { position_tolerance_m: number; heading_tolerance_rad: number };
    timeout_s: number;
    controller_kind: "geometric" | "learned_collision_risk";
    inference_backend?:
      | "python-reference"
      | "native-naive"
      | "native-blocked"
      | "native-parallel-blocked"
      | "native-accelerate";
    inference_workers?: number;
    model_artifact_version?: string | null;
    model_sha256?: string | null;
    risk_cutoff?: number | null;
    candidate_set_id?: string | null;
    safety_envelope_version?: "sensor-stopping-v1" | "sensor-stopping-v2";
    execution_mode?: "synchronous" | "virtual_fifo" | "native_paced";
    pacing_overrun_limit_s?: number;
    modeled_device?: {
      dispatch_s: number;
      input_transfer_s: number;
      compute_s: number;
      output_transfer_s: number;
      pending_capacity: number;
      deadline_s: number;
      maximum_age_s: number;
      queue_policy: "fifo" | "latest_pending";
      requests_per_tick: number;
      resident_weights_bytes: number;
      workspace_bytes: number;
      request_payload_bytes: number;
      memory_budget_bytes: number;
    };
  };
  expected_mission_outcome:
    | "completed"
    | "timed_out"
    | "collision"
    | "unreachable"
    | "target_not_found"
    | "target_ambiguous"
    | "provider_unavailable";
}

interface TraceEvent extends ReplayEvent {
  kind:
    | "phase_changed"
    | "pose_sample"
    | "observation_captured"
    | "terminal"
    | "route_planned"
    | "range_sampled"
    | "braking_started"
    | "collision"
    | "control_decision"
    | "inference_event"
    | "pacing_overrun";
  pose: Pose;
  linear_velocity_mps: number;
  angular_velocity_radps: number;
  commanded_linear_velocity_mps?: number;
  commanded_angular_velocity_radps?: number;
  range_readings_m?: number[] | null;
  detail?: string | null;
  candidate_risks?: number[] | null;
  selected_candidate_index?: number | null;
  risk_cutoff?: number | null;
  selected_risk?: number | null;
  selected_progress_score?: number | null;
  inference_event_kind?: string | null;
  request_id?: number | null;
  observation_id?: number | null;
  queue_depth?: number | null;
  observation_age_s?: number | null;
  modeled_event_time_s?: number | null;
  timing_provenance?: "modeled" | "measured" | null;
  queue_wait_s?: number | null;
  modeled_memory_bytes?: number | null;
  memory_budget_bytes?: number | null;
  resident_weights_bytes?: number | null;
  workspace_bytes?: number | null;
  pending_payload_bytes?: number | null;
  in_flight_payload_bytes?: number | null;
  peak_modeled_memory_bytes?: number | null;
  measured_execution_s?: number | null;
  pacing_overrun_s?: number | null;
}

export interface RunResult {
  run_id: string;
  request: RunRequest;
  trace: TraceEvent[];
  observations: Array<{
    target_id: string;
    pose: Pose;
    simulated_time_s: number;
    completion_status: "captured";
  }>;
  mission_outcome:
    | "completed"
    | "timed_out"
    | "collision"
    | "unreachable"
    | "target_not_found"
    | "target_ambiguous"
    | "provider_unavailable";
  test_verdict: "passed" | "failed";
  terminal_reason: string;
  grounding_evidence?: {
    source: "live" | "recorded";
    status: "matched" | "target_not_found" | "target_ambiguous" | "provider_unavailable";
    provider: string;
    model: string;
    parser_version: string;
    target_phrase: string;
    render_sha256: string;
    render_width_px: number;
    render_height_px: number;
    duration_s: number;
    raw_output_sha256: string;
    selected_match_ordinal?: number | null;
    diagnostics: string[];
    matches: Array<{
      ordinal: number;
      box_px: [number, number, number, number];
      confidence?: number | null;
      mask: {
        width_px: number;
        height_px: number;
        counts: number[];
        encoding: "row_major_rle_v1";
      };
    }>;
  } | null;
  planned_routes: Pose[][];
  controller_kind?: "geometric" | "learned_collision_risk";
  model_version?: string | null;
  model_sha256?: string | null;
  validation_evidence_reference?: string | null;
  validation_quality_gate_status?: "met" | "not_met" | null;
  inference_backend?:
    | "python-reference"
    | "native-naive"
    | "native-blocked"
    | "native-parallel-blocked"
    | "native-accelerate"
    | null;
  runtime_provenance?: Record<string, string> | null;
  command_disagreements?: number | null;
  inference_summary?: Record<string, number | string> | null;
  configuration_validity?: {
    configuration_id: string;
    rover_type: "differential_drive";
    model_feature_count: 24;
    training_domain_status: "inside" | "outside" | "not_applicable";
    warnings: string[];
  } | null;
  terminal_failure?: {
    code: "collision" | "unreachable" | "timeout";
    message: string;
    pose: Pose;
    obstacle_id?: string | null;
    contact_point?: { x_m: number; y_m: number } | null;
  } | null;
  target_visits?: Array<{
    target_id: string;
    required_ordinal: number;
    pose?: Pose | null;
    dwell_completed: boolean;
    status:
      | "captured"
      | "not_visited_timeout"
      | "not_visited_collision"
      | "not_visited_setup_failure"
      | "unreachable"
      | "target_not_found"
      | "target_ambiguous";
    observation_sequence?: number | null;
  }>;
}

export interface RoverEdgeApi {
  getScenarios(): Promise<Scenario[]>;
  getSceneDraft?(scenarioVersion: string): Promise<SceneDraft>;
  saveSceneVersion?(draft: SceneDraft): Promise<Scenario>;
  createPhotoDraft?(name: string, dataUrl: string): Promise<PhotoDraftResult>;
  getAccelerateComparison?(): Promise<AccelerateComparison>;
  getHeldOutReadiness?(): Promise<HeldOutReadiness>;
  run(request: RunRequest): Promise<RunResult>;
  exportRun?(result: RunResult): Promise<Blob>;
  exportComparison?(
    before: RunResult,
    after: RunResult,
    declaredFactor?: string,
  ): Promise<Blob>;
}

interface HeldOutReadiness {
  status: "awaiting_quality_review" | "ready_to_execute";
  protocol_approval_status: "pending_quality_threshold_review";
  required_gates: Record<string, "met" | "not_met" | "not_run">;
  final_test_families: string[];
}

interface AccelerateComparison {
  available_locally: boolean;
  recorded_result: {
    hardware_model: string;
    correctness_gate: string;
    timing_provenance: string;
    latency: {
      "native-naive": { median_us: number; samples: number };
      "native-accelerate": { median_us: number; samples: number };
    };
  };
}

export const httpApi: RoverEdgeApi = {
  async getScenarios() {
    return requestJson<Scenario[]>("/api/scenarios");
  },
  async getAccelerateComparison() {
    return requestJson<AccelerateComparison>("/api/native-comparisons/accelerate");
  },
  async getHeldOutReadiness() {
    return requestJson<HeldOutReadiness>("/api/evaluations/held-out");
  },
  async getSceneDraft(scenarioVersion) {
    return requestJson<SceneDraft>(`/api/scenarios/${scenarioVersion}/draft`);
  },
  async saveSceneVersion(draft) {
    return requestJson<Scenario>("/api/scene-versions", draft);
  },
  async createPhotoDraft(name, dataUrl) {
    return requestJson<PhotoDraftResult>("/api/photo-drafts", { name, data_url: dataUrl });
  },
  async run(request) {
    return requestJson<RunResult>("/api/runs", request);
  },
  async exportRun(result) {
    return requestBlob("/api/evidence-bundles/run", result);
  },
  async exportComparison(before, after, declaredFactor) {
    return requestBlob("/api/evidence-bundles/comparison", {
      before,
      after,
      declared_factor: declaredFactor ?? null,
    });
  },
};

export async function mountApp(root: HTMLElement, api: RoverEdgeApi = httpApi): Promise<void> {
  root.innerHTML = applicationMarkup();
  root.querySelector<HTMLButtonElement>("[data-action='start']")!.disabled = true;
  root.querySelector<HTMLSelectElement>("[data-action='scenario']")!.disabled = true;
  const presentationCanvas = root.querySelector<HTMLCanvasElement>("[data-field='presentation-canvas']")!;
  attachPresentationCamera(presentationCanvas);
  root.querySelector<HTMLButtonElement>("[data-action='reset-camera']")!.addEventListener("click", () => {
    resetPresentationCamera(presentationCanvas);
  });
  const scenarios = await api.getScenarios();
  let scenario = scenarios[0]!;
  const selector = root.querySelector<HTMLSelectElement>("[data-action='scenario']")!;
  const memoryBudget = root.querySelector<HTMLInputElement>(
    "[data-action='memory-budget']",
  )!;
  for (const available of scenarios) {
    selector.add(new Option(available.name, available.scenario_version));
  }
  const showScenario = (): void => {
    setText(root, "scenario", `${scenario.name} · ${scenario.scenario_version}`);
    setText(root, "target", scenario.requested_target_label ?? scenario.target.label);
    setText(root, "brief-target", scenario.requested_target_label ?? scenario.target.label);
    setText(root, "stage-caption", `${scenario.name}. Target: ${scenario.target.label}. ${scenario.obstacles.length} recorded obstacles. Presentation view; open the technical map for exact geometry.`);
    memoryBudget.value = String(
      scenario.default_run_request.configuration.modeled_device?.memory_budget_bytes ?? 32768,
    );
    populateExperimentForm(root, scenario.default_run_request);
    drawPresentationScene(
      presentationCanvas,
      scenario,
    );
  };
  showScenario();
  if (!api.getSceneDraft || !api.saveSceneVersion) {
    root.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-editor]").forEach(
      (input) => (input.disabled = true),
    );
    root.querySelectorAll<HTMLButtonElement>("[data-scene-action]").forEach(
      (button) => (button.disabled = true),
    );
  }
  if (!api.createPhotoDraft) {
    root.querySelector<HTMLButtonElement>("[data-scene-action='photo-draft']")!.disabled = true;
  }
  const exportRunButton = root.querySelector<HTMLButtonElement>("[data-action='export-run']")!;
  const exportComparisonButton = root.querySelector<HTMLButtonElement>(
    "[data-action='export-comparison']",
  )!;
  exportRunButton.disabled = true;
  exportComparisonButton.disabled = true;
  if (api.getAccelerateComparison) {
    const comparison = await api.getAccelerateComparison();
    const recorded = comparison.recorded_result;
    const accelerateButton = root.querySelector<HTMLButtonElement>(
      "[data-action='accelerate']",
    )!;
    accelerateButton.disabled = !comparison.available_locally;
    if (!comparison.available_locally) {
      accelerateButton.title = "Apple Accelerate is unavailable on this host";
    }
    setText(
      root,
      "accelerate-comparison",
      `${comparison.available_locally ? "available locally" : "unavailable locally"} · recorded ${recorded.hardware_model} · correctness ${recorded.correctness_gate} · naive ${recorded.latency["native-naive"].median_us} µs median · Accelerate ${recorded.latency["native-accelerate"].median_us} µs median · ${recorded.timing_provenance}`,
    );
  }
  if (api.getHeldOutReadiness) {
    const readiness = await api.getHeldOutReadiness();
    const gates = Object.entries(readiness.required_gates)
      .map(([name, status]) => `${humanize(name)}: ${status}`)
      .join(" · ");
    setText(
      root,
      "held-out-readiness",
      `${readiness.status} · protocol ${readiness.protocol_approval_status} · ${readiness.final_test_families.length} untouched families · ${gates}`,
    );
  }

  let result: RunResult | undefined;
  let lastCompletedRun: RunResult | undefined;
  root.querySelector("[data-action='investigate']")!.addEventListener("click", async () => {
    if (!result) return;
    const button = root.querySelector<HTMLButtonElement>("[data-action='investigate']")!;
    const consent = root.querySelector<HTMLInputElement>("[data-action='provider-consent']")!;
    if (!consent.checked) {
      setText(root, "investigation-result", "Confirm the two provider requests before starting the investigation.");
      return;
    }
    button.disabled = true;
    setText(root, "investigation-result", "Investigating the recorded mission…");
    try {
      const response = await requestJson<{ provider_summary: string; model: string; provider_calls_used: number; investigation: { explanation: { what_happened: string; tested_change: string; whether_it_helped: string }; follow_up_runs_used: number } }>("/api/investigations/live", {
        baseline: result,
        instruction: root.querySelector<HTMLTextAreaElement>("[data-action='investigation-question']")!.value,
        confirm_live_provider_call: true,
      });
      const explanation = response.investigation.explanation;
      setText(root, "investigation-result", `${explanation.what_happened}\nTested change: ${explanation.tested_change}\nResult: ${explanation.whether_it_helped}\n${response.provider_summary}`);
      setText(root, "investigation-source", `Live Meta model via Baseten: ${response.model}. ${response.provider_calls_used} provider requests; ${response.investigation.follow_up_runs_used} follow-up simulations.`);
    } catch (error) {
      setText(root, "investigation-result", `Investigation could not finish: ${error instanceof Error ? error.message : String(error)}. Your mission result is still available.`);
      const requestError = error as Error & { providerCallsUsed?: number; model?: string };
      if (requestError.providerCallsUsed !== undefined) {
        setText(root, "investigation-source", `Live Meta model via Baseten: ${requestError.model ?? "configured model"}. ${requestError.providerCallsUsed} provider request${requestError.providerCallsUsed === 1 ? "" : "s"} used before evidence validation stopped the investigation.`);
      }
    } finally { button.disabled = false; }
  });
  let replay: ReplayController | undefined;
  let comparisonBaseline: RunResult | undefined;
  let comparisonReplay: ReplayController | undefined;
  let comparisonScenario: Scenario | undefined;
  let replayStartedAt = 0;
  let replayStartTime = 0;

  const render = (): void => {
    if (!result || !replay) return;
    const event = replay.currentEvent() as TraceEvent;
    setText(root, "phase", humanize(event.phase));
    setText(root, "brief-phase", humanize(event.phase));
    setText(root, "stage-caption", `${scenario.name}. Rover at map x ${event.pose.x_m.toFixed(2)} m, y ${event.pose.y_m.toFixed(2)} m; phase ${humanize(event.phase)}. Presentation view follows recorded pose.`);
    setText(root, "time", `${event.simulated_time_s.toFixed(2)} s`);
    const slider = root.querySelector<HTMLInputElement>("[data-action='scrub']")!;
    slider.value = String(event.simulated_time_s);
    drawScene(root.querySelector<HTMLCanvasElement>(".technical-map canvas")!, scenario, result, event);
    drawPresentationScene(
      presentationCanvas,
      scenario,
      result,
      event,
    );
    if (comparisonBaseline && comparisonReplay && comparisonScenario) {
      comparisonReplay.scrubTo(event.simulated_time_s);
      const comparisonEvent = comparisonReplay.currentEvent() as TraceEvent;
      drawScene(
        root.querySelector<HTMLCanvasElement>("[data-field='comparison-canvas']")!,
        comparisonScenario,
        comparisonBaseline,
        comparisonEvent,
      );
      setText(
        root,
        "comparison-time",
        `before ${comparisonEvent.simulated_time_s.toFixed(2)} s · after ${event.simulated_time_s.toFixed(2)} s`,
      );
    }
    setText(
      root,
      "motion",
      `${event.linear_velocity_mps.toFixed(3)} m/s · ${event.angular_velocity_radps.toFixed(3)} rad/s`,
    );
    const replayEvidence = result.trace
      .slice(0, event.sequence + 1)
      .reverse()
      .find(
        (item) =>
          item.kind === "control_decision" ||
          item.kind === "braking_started" ||
          item.kind === "collision",
      );
    setText(
      root,
      "replay-evidence",
      replayEvidence
        ? `${humanize(replayEvidence.kind)}: ${replayEvidence.detail ?? "recorded"}`
        : "None",
    );
    const decision = result.trace
      .slice(0, event.sequence + 1)
      .reverse()
      .find((item) => item.kind === "control_decision");
    setText(
      root,
      "decision",
      decision?.candidate_risks && decision.selected_candidate_index != null
        ? `candidate ${decision.selected_candidate_index} · risk ${decision.selected_risk?.toFixed(4)} · progress score ${decision.selected_progress_score?.toFixed(3)} · cutoff ${decision.risk_cutoff?.toFixed(2)} · [${decision.candidate_risks.map((risk) => risk.toFixed(3)).join(", ")}]`
        : "None",
    );
    const agedDecision = result.trace
      .slice(0, event.sequence + 1)
      .reverse()
      .find((item) => item.observation_age_s != null);
    setText(
      root,
      "prediction-age",
      agedDecision?.observation_age_s != null
        ? `${agedDecision.observation_age_s.toFixed(3)} s · ${agedDecision.timing_provenance ?? "unknown"}`
        : "Not available",
    );
    setText(root, "prediction-age-primary", agedDecision?.observation_age_s != null
      ? `${agedDecision.observation_age_s.toFixed(3)} s (${agedDecision.timing_provenance ?? "unknown"})`
      : "Not available");
    const queueEvent = result.trace
      .slice(0, event.sequence + 1)
      .reverse()
      .find((item) => item.inference_event_kind != null);
    setText(
      root,
      "queue-state",
      queueEvent
        ? `${queueEvent.inference_event_kind} · depth ${queueEvent.queue_depth ?? 0} · request ${queueEvent.request_id ?? "—"}`
        : "Not available",
    );
  };

  const animate = (timestamp: number): void => {
    if (!result || !replay || !replay.isPlaying()) return;
    if (replayStartedAt === 0) replayStartedAt = timestamp;
    replay.advanceTo(replayStartTime + (timestamp - replayStartedAt) / 1000);
    render();
    const finalTime = result.trace.at(-1)!.simulated_time_s;
    if (replay.currentEvent().simulated_time_s >= finalTime) {
      replay.pause();
      return;
    }
    requestAnimationFrame(animate);
  };

  const run = async (runRequest: () => Promise<RunResult>): Promise<void> => {
    setText(root, "status", "Running deterministic experiment…");
    let nextResult: RunResult;
    try {
      nextResult = await runRequest();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setText(root, "configuration-error", message);
      setText(root, "status", "Configuration rejected; last successful run preserved.");
      return;
    }
    comparisonBaseline = lastCompletedRun;
    comparisonReplay = comparisonBaseline
      ? new ReplayController(comparisonBaseline.trace)
      : undefined;
    comparisonScenario = comparisonBaseline
      ? scenarios.find(
          (item) => item.scenario_version === comparisonBaseline?.request.scenario_version,
        )
      : undefined;
    result = nextResult;
    lastCompletedRun = nextResult;
    root.querySelector<HTMLButtonElement>("[data-action='investigate']")!.disabled = false;
    setText(root, "run-explanation", explainRun(result));
    setText(root, "investigation-result", "Ask the engineer to inspect this run and test a bounded change.");
    setText(root, "investigation-source", "No provider requests made for this investigation yet.");
    replay = new ReplayController(result.trace);
    replayStartedAt = 0;
    replayStartTime = 0;
    setText(root, "configuration-error", "None");
    setText(root, "status", result.terminal_reason);
    exportRunButton.disabled = !api.exportRun;
    exportComparisonButton.disabled = !api.exportComparison || !comparisonBaseline;
    setText(
      root,
      "failure",
      result.terminal_failure
        ? `${result.terminal_failure.code}: ${result.terminal_failure.message}`
        : "None",
    );
    setText(root, "run-id", result.run_id);
    setText(root, "scenario-version", result.request.scenario_version);
    setText(root, "seed", String(result.request.simulation_seed));
    setText(root, "expectation", result.request.expected_mission_outcome);
    setText(root, "configuration", formatConfiguration(result.request));
    setText(root, "outcome", result.mission_outcome);
    setText(root, "verdict", result.test_verdict);
    setText(root, "mission-outcome-primary", humanize(result.mission_outcome));
    setText(root, "test-verdict-primary", humanize(result.test_verdict));
    setText(root, "run-source", result.inference_summary?.timing_provenance === "modeled"
      ? "Modeled device run"
      : result.inference_summary?.timing_provenance === "measured"
        ? "Measured local run"
        : "Deterministic simulation run");
    setText(
      root,
      "target-visits",
      result.target_visits?.length
        ? result.target_visits
            .map(
              (visit) =>
                `${visit.required_ordinal + 1}. ${visit.target_id}: ${visit.status} · dwell ${visit.dwell_completed ? "complete" : "incomplete"}${visit.pose ? ` · pose (${visit.pose.x_m.toFixed(2)}, ${visit.pose.y_m.toFixed(2)}, ${visit.pose.heading_rad.toFixed(2)})` : ""}`,
            )
            .join(" | ")
        : "Single-target evidence is recorded in observations.",
    );
    setText(
      root,
      "grounding",
      result.grounding_evidence
        ? `${result.grounding_evidence.source} · ${result.grounding_evidence.status} · ${result.grounding_evidence.model} · phrase “${result.grounding_evidence.target_phrase}” · render ${result.grounding_evidence.render_sha256.slice(0, 12)}…`
        : "Not used",
    );
    showGroundingEvidence(root, result);
    setText(root, "controller", result.controller_kind ?? result.request.configuration.controller_kind);
    setText(
      root,
      "model",
      result.model_version && result.model_sha256
        ? `${result.model_version} · ${result.model_sha256.slice(0, 12)}…`
        : "Not used",
    );
    setText(
      root,
      "validation",
      result.validation_evidence_reference && result.validation_quality_gate_status
        ? `${result.validation_quality_gate_status} · ${result.validation_evidence_reference}`
        : "Not applicable",
    );
    setText(
      root,
      "runtime",
      formatRuntimeEvidence(result),
    );
    setText(root, "modeled-memory", formatModeledMemory(result));
    setText(root, "native-paced", formatNativePaced(result));
    setText(root, "configuration-validity", formatConfigurationValidity(result));
    const comparisonMode = root.querySelector<HTMLSelectElement>(
      "[data-action='comparison-mode']",
    )!.value;
    const declaredFactor =
      comparisonMode === "controlled"
        ? root.querySelector<HTMLInputElement>("[data-action='declared-factor']")!.value.trim()
        : undefined;
    setText(
      root,
      "comparison-validity",
      formatComparisonValidity(comparisonBaseline?.request, result.request, declaredFactor),
    );
    setText(
      root,
      "comparison-evidence",
      comparisonBaseline
        ? formatComparisonEvidence(comparisonBaseline, result)
        : "Run a second experiment to compare recorded evidence",
    );
    setText(
      root,
      "phases",
      result.trace
        .filter((event) => event.kind === "phase_changed" || event.kind === "terminal")
        .map((event) => event.phase)
        .filter((phase, index, allPhases) => phase !== allPhases[index - 1])
        .join(" → "),
    );
    const slider = root.querySelector<HTMLInputElement>("[data-action='scrub']")!;
    slider.max = String(result.trace.at(-1)!.simulated_time_s);
    slider.disabled = false;
    render();
  };

  root
    .querySelector("[data-action='start']")!
    .addEventListener("click", () => void run(() => api.run(scenario.default_run_request)));
  root.querySelector<HTMLButtonElement>("[data-action='queue-comparison']")!
    .addEventListener("click", async () => {
      const button = root.querySelector<HTMLButtonElement>("[data-action='queue-comparison']")!;
      button.disabled = true;
      const base = scenario.default_run_request;
      const device = base.configuration.modeled_device!;
      const compute = Number(root.querySelector<HTMLSelectElement>("[data-action='comparison-delay']")!.value);
      const fifo: RunRequest = {
        ...base,
        configuration: {
          ...base.configuration,
          controller_kind: "learned_collision_risk",
          model_artifact_version: "risk-model-v2",
          safety_envelope_version: "sensor-stopping-v2",
          execution_mode: "virtual_fifo",
          modeled_device: { ...device, compute_s: compute, pending_capacity: 4, queue_policy: "fifo" },
        },
      };
      const latest: RunRequest = {
        ...fifo,
        configuration: {
          ...fifo.configuration,
          modeled_device: { ...device, compute_s: compute, pending_capacity: 4, queue_policy: "latest_pending" },
        },
      };
      const mode = root.querySelector<HTMLSelectElement>("[data-action='comparison-mode']")!;
      mode.value = "controlled";
      root.querySelector<HTMLInputElement>("[data-action='declared-factor']")!.value =
        "configuration.modeled_device.queue_policy";
      const previousResult = result;
      await run(() => api.run(fifo));
      if (result !== previousResult && result?.request.configuration.modeled_device?.queue_policy === "fifo") {
        const fifoResult = result;
        await run(() => api.run(latest));
        if (result !== fifoResult && comparisonBaseline === fifoResult && result) {
          const before = comparisonBaseline;
          const after = result;
          const validity = formatComparisonValidity(before.request, after.request, "configuration.modeled_device.queue_policy");
          const conclusion = before.mission_outcome === after.mission_outcome
            ? "No mission outcome change observed."
            : `Mission outcome changed from ${humanize(before.mission_outcome)} to ${humanize(after.mission_outcome)}.`;
          setText(root, "story-result", `FIFO: ${humanize(before.mission_outcome)}. Latest pending: ${humanize(after.mission_outcome)}. ${conclusion} ${validity}. FIFO: ${explainRun(before)} Latest pending: ${explainRun(after)}`);
          const observedAge = (run: RunResult): string => {
            const summary = summarizeRun(run);
            return summary.meanAge == null ? "No accepted age samples" : `${(summary.meanAge * 1000).toFixed(0)} ms average / ${(summary.maxAge! * 1000).toFixed(0)} ms max (${summary.decisions} accepted decisions)`;
          };
          setText(root, "fifo-outcome", humanize(before.mission_outcome));
          setText(root, "latest-outcome", humanize(after.mission_outcome));
          setText(root, "fifo-age", observedAge(before));
          setText(root, "latest-age", observedAge(after));
          setText(root, "fifo-replacements", String(before.inference_summary?.replaced ?? "Not available"));
          setText(root, "latest-replacements", String(after.inference_summary?.replaced ?? "Not available"));
        }
      }
      button.disabled = false;
    });
  exportRunButton.addEventListener("click", async () => {
    if (!result || !api.exportRun) return;
    downloadBlob(
      await api.exportRun(result),
      `roveredge-run-${result.run_id}.zip`,
    );
  });
  exportComparisonButton.addEventListener("click", async () => {
    if (!result || !comparisonBaseline || !api.exportComparison) return;
    const comparisonMode = root.querySelector<HTMLSelectElement>(
      "[data-action='comparison-mode']",
    )!.value;
    const declaredFactor =
      comparisonMode === "controlled"
        ? root.querySelector<HTMLInputElement>("[data-action='declared-factor']")!.value.trim()
        : undefined;
    downloadBlob(
      await api.exportComparison(comparisonBaseline, result, declaredFactor),
      "roveredge-comparison.zip",
    );
  });
  root
    .querySelector("[data-action='grounded-recorded']")!
    .addEventListener("click", () => {
      const phrase = root
        .querySelector<HTMLInputElement>("[data-action='target-phrase']")!
        .value.trim();
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          target: { kind: "visual_target", phrase, grounding_source: "recorded" },
        }),
      );
    });
  root.querySelector("[data-action='multi-target']")!.addEventListener("click", () => {
    const targetIds = root
      .querySelector<HTMLInputElement>("[data-action='multi-target-ids']")!
      .value.split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    void run(() =>
      api.run({
        ...scenario.default_run_request,
        target: { kind: "multi_target_fixture", target_ids: targetIds },
      }),
    );
  });
  root
    .querySelector("[data-action='learned']")!
    .addEventListener("click", () =>
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: {
            ...scenario.default_run_request.configuration,
            controller_kind: "learned_collision_risk",
          },
        }),
      ),
    );
  root
    .querySelector("[data-action='native']")!
    .addEventListener("click", () =>
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: {
            ...scenario.default_run_request.configuration,
            controller_kind: "learned_collision_risk",
            inference_backend: "native-naive",
          },
        }),
      ),
    );
  root
    .querySelector("[data-action='native-paced']")!
    .addEventListener("click", () =>
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: {
            ...scenario.default_run_request.configuration,
            controller_kind: "learned_collision_risk",
            inference_backend: "native-naive",
            execution_mode: "native_paced",
          },
        }),
      ),
    );
  root
    .querySelector("[data-action='blocked']")!
    .addEventListener("click", () =>
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: {
            ...scenario.default_run_request.configuration,
            controller_kind: "learned_collision_risk",
            inference_backend: "native-blocked",
          },
        }),
      ),
    );
  root
    .querySelector("[data-action='parallel']")!
    .addEventListener("click", () =>
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: {
            ...scenario.default_run_request.configuration,
            controller_kind: "learned_collision_risk",
            inference_backend: "native-parallel-blocked",
            inference_workers: 4,
          },
        }),
      ),
    );
  root
    .querySelector("[data-action='accelerate']")!
    .addEventListener("click", () =>
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: {
            ...scenario.default_run_request.configuration,
            controller_kind: "learned_collision_risk",
            inference_backend: "native-accelerate",
          },
        }),
      ),
    );
  root
    .querySelector("[data-action='modeled-memory']")!
    .addEventListener("click", () => {
      const modeledDevice = scenario.default_run_request.configuration.modeled_device!;
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: {
            ...scenario.default_run_request.configuration,
            controller_kind: "learned_collision_risk",
            execution_mode: "virtual_fifo",
            modeled_device: {
              ...modeledDevice,
              memory_budget_bytes: Number(memoryBudget.value),
            },
          },
        }),
      );
    });
  root
    .querySelector("[data-action='configured-run']")!
    .addEventListener("click", () =>
      void run(() => api.run(configuredRequest(root, scenario.default_run_request))),
    );
  selector.addEventListener("change", () => {
    replay?.pause();
    result = undefined;
    replay = undefined;
    comparisonBaseline = undefined;
    comparisonReplay = undefined;
    root.querySelector<HTMLButtonElement>("[data-action='investigate']")!.disabled = true;
    root.querySelector<HTMLInputElement>("[data-action='scrub']")!.disabled = true;
    exportRunButton.disabled = true;
    exportComparisonButton.disabled = true;
    for (const field of ["mission-outcome-primary", "test-verdict-primary", "prediction-age-primary", "fifo-outcome", "latest-outcome", "fifo-age", "latest-age", "fifo-replacements", "latest-replacements"]) setText(root, field, "No run for this scenario");
    setText(root, "run-explanation", "Run this scenario to see its result.");
    setText(root, "brief-phase", "Not started");
    setText(root, "run-source", "No run selected");
    setText(root, "story-result", "Run both policies to compare this scenario.");
    scenario = scenarios.find((item) => item.scenario_version === selector.value)!;
    showScenario();
  });
  const editor = (name: string): HTMLInputElement | HTMLSelectElement =>
    root.querySelector(`[data-editor='${name}']`)!;
  const setEditor = (name: string, value: string | number): void => {
    editor(name).value = String(value);
  };
  const populateDraft = (draft: SceneDraft): void => {
    setEditor("name", draft.name);
    setEditor("scale", draft.pixels_per_meter);
    setEditor("dock-x", draft.dock_pose.x_m);
    setEditor("dock-y", draft.dock_pose.y_m);
    setEditor(
      "obstacle",
      draft.obstacles
        .map((item) => `${item.x_min_m},${item.y_min_m},${item.x_max_m},${item.y_max_m}`)
        .join("; "),
    );
    setEditor(
      "target",
      draft.targets
        .map(
          (item) =>
            `${item.label}:${item.x_min_m},${item.y_min_m},${item.x_max_m},${item.y_max_m}`,
        )
        .join("; "),
    );
    const target = draft.targets[0];
    setEditor("target-label", target?.label ?? "Red toolbox");
    const sceneEditor = root.querySelector<HTMLElement>("[data-field='scene-editor']")!;
    sceneEditor.dataset.sourceVersion = draft.source_version ?? "";
    sceneEditor.dataset.photoReferenceSha256 = draft.photo_reference_sha256 ?? "";
    const photoReference = root.querySelector<HTMLImageElement>("[data-field='photo-reference']")!;
    if (draft.photo_reference_sha256) {
      photoReference.src = `/api/photo-references/${draft.photo_reference_sha256}`;
      photoReference.hidden = false;
    } else {
      photoReference.removeAttribute("src");
      photoReference.hidden = true;
    }
  };
  const loadDraft = async (empty: boolean): Promise<void> => {
    if (!api.getSceneDraft) return;
    const draft: SceneDraft = empty
      ? {
          name: "Untitled inspection scene",
          width_m: 8,
          height_m: 6,
          pixels_per_meter: 100,
          dock_pose: { x_m: 1, y_m: 3, heading_rad: 0 },
          obstacles: [],
          targets: [],
          source_version: null,
          photo_reference_sha256: null,
        }
      : await api.getSceneDraft(scenario.scenario_version);
    populateDraft(draft);
    setText(
      root,
      "scene-validation",
      empty ? "Empty draft ready for editing." : "Preset geometry loaded for editing.",
    );
  };
  const parseRectangle = (value: string, label: string): [number, number, number, number] => {
    const values = value.split(",").map((part) => Number(part.trim()));
    if (values.length !== 4 || values.some((item) => !Number.isFinite(item))) {
      throw new Error(`${label} must contain x min, y min, x max, y max`);
    }
    return values as [number, number, number, number];
  };
  const parseRectangles = (
    value: string,
    label: string,
  ): Array<[number, number, number, number]> =>
    value
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => parseRectangle(item, label));
  const parseTargetEntries = (
    value: string,
  ): Array<{
    label: "Red toolbox" | "Blue barrel";
    footprint: [number, number, number, number];
  }> =>
    value
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        const separator = item.indexOf(":");
        const rawLabel = separator >= 0 ? item.slice(0, separator).trim() : editor("target-label").value;
        if (rawLabel !== "Red toolbox" && rawLabel !== "Blue barrel") {
          throw new Error(`Target label must be Red toolbox or Blue barrel: ${rawLabel}`);
        }
        return {
          label: rawLabel,
          footprint: parseRectangle(separator >= 0 ? item.slice(separator + 1) : item, "Each target"),
        };
      });
  const drawEditorPreview = (): void => {
    const canvas = root.querySelector<HTMLCanvasElement>("[data-field='scene-preview']")!;
    const pixelsPerMeter = Number(editor("scale").value);
    canvas.width = Math.round(8 * pixelsPerMeter);
    canvas.height = Math.round(6 * pixelsPerMeter);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#eef2ef";
    context.fillRect(0, 0, canvas.width, canvas.height);
    const drawFootprints = (value: string, color: string): void => {
      for (const [xMin, yMin, xMax, yMax] of parseRectangles(value, "Footprint")) {
        context.fillStyle = color;
        context.fillRect(
          xMin * pixelsPerMeter,
          yMin * pixelsPerMeter,
          (xMax - xMin) * pixelsPerMeter,
          (yMax - yMin) * pixelsPerMeter,
        );
      }
    };
    drawFootprints(editor("obstacle").value, "#5b6560");
    for (const target of parseTargetEntries(editor("target").value)) {
      const [xMin, yMin, xMax, yMax] = target.footprint;
      context.fillStyle = target.label === "Red toolbox" ? "#c4362d" : "#2a5ca8";
      context.fillRect(
        xMin * pixelsPerMeter,
        yMin * pixelsPerMeter,
        (xMax - xMin) * pixelsPerMeter,
        (yMax - yMin) * pixelsPerMeter,
      );
    }
    context.fillStyle = "#233a32";
    context.beginPath();
    context.arc(
      Number(editor("dock-x").value) * pixelsPerMeter,
      Number(editor("dock-y").value) * pixelsPerMeter,
      12,
      0,
      Math.PI * 2,
    );
    context.fill();
    setText(root, "scene-preview-scale", `${editor("scale").value} px/m declared scale`);
  };
  root
    .querySelector("[data-scene-action='preset']")!
    .addEventListener("click", () => {
      void loadDraft(false)
        .then(drawEditorPreview)
        .catch((error) =>
          setText(root, "scene-validation", error instanceof Error ? error.message : String(error)),
        );
    });
  root
    .querySelector("[data-scene-action='empty']")!
    .addEventListener("click", () => {
      void loadDraft(true).then(drawEditorPreview);
    });
  root.querySelectorAll("[data-editor]").forEach((input) => {
    input.addEventListener("input", () => {
      try {
        const confirmationByEditor: Record<string, string> = {
          scale: "scale",
          obstacle: "obstacles",
          "dock-x": "dock",
          "dock-y": "dock",
          target: "targets",
          "target-label": "targets",
        };
        const confirmationName = confirmationByEditor[(input as HTMLElement).dataset.editor ?? ""];
        const hasPhotoReference = Boolean(
          root.querySelector<HTMLElement>("[data-field='scene-editor']")!.dataset
            .photoReferenceSha256,
        );
        if (hasPhotoReference && confirmationName) {
          root.querySelector<HTMLInputElement>(
            `[data-photo-confirmation='${confirmationName}']`,
          )!.checked = false;
        }
        drawEditorPreview();
      } catch (error) {
        setText(root, "scene-validation", error instanceof Error ? error.message : String(error));
      }
    });
  });
  root.querySelector("[data-scene-action='photo-draft']")!.addEventListener("click", async () => {
    if (!api.createPhotoDraft) return;
    const file = root.querySelector<HTMLInputElement>("[data-action='photo-upload']")!.files?.[0];
    if (!file) {
      setText(root, "photo-draft-status", "Choose a PNG or JPEG reference first.");
      return;
    }
    try {
      const dataUrl = await readFileAsDataUrl(file);
      const generated = await api.createPhotoDraft(editor("name").value, dataUrl);
      populateDraft(generated.draft);
      root.querySelectorAll<HTMLInputElement>("[data-photo-confirmation]").forEach(
        (confirmation) => (confirmation.checked = false),
      );
      drawEditorPreview();
      const reference = root.querySelector<HTMLImageElement>("[data-field='photo-reference']")!;
      reference.src = generated.photo_reference.url;
      reference.hidden = false;
      setText(
        root,
        "photo-draft-status",
        `${generated.claim}. Uncertainty: ${generated.uncertainty.join(" ")}`,
      );
    } catch (error) {
      setText(root, "photo-draft-status", error instanceof Error ? error.message : String(error));
    }
  });
  root.querySelector("[data-scene-action='save']")!.addEventListener("click", async () => {
    if (!api.saveSceneVersion) return;
    try {
      const photoReferenceSha256 =
        root.querySelector<HTMLElement>("[data-field='scene-editor']")!.dataset
          .photoReferenceSha256 || null;
      const confirmations = Array.from(
        root.querySelectorAll<HTMLInputElement>("[data-photo-confirmation]"),
      );
      if (photoReferenceSha256 && confirmations.some((item) => !item.checked)) {
        throw new Error(
          "Confirm the photo draft scale, obstacle footprints, dock, and targets before saving.",
        );
      }
      const obstacleText = editor("obstacle").value.trim();
      const targetText = editor("target").value.trim();
      const obstacles = obstacleText
        ? parseRectangles(obstacleText, "Each obstacle").map(
            ([x_min_m, y_min_m, x_max_m, y_max_m], index) => ({
              obstacle_id: `edited-obstacle-${index + 1}`,
              x_min_m,
              y_min_m,
              x_max_m,
              y_max_m,
            }),
          )
        : [];
      const targets = targetText
        ? parseTargetEntries(targetText).map(
            ({ label, footprint: [x_min_m, y_min_m, x_max_m, y_max_m] }, index) => ({
              object_id: `edited-target-${index + 1}`,
              label,
              x_min_m,
              y_min_m,
              x_max_m,
              y_max_m,
              color_rgb: (label === "Red toolbox"
                ? [196, 54, 45]
                : [42, 92, 168]) as [number, number, number],
            }),
          )
        : [];
      const saved = await api.saveSceneVersion({
        name: editor("name").value,
        width_m: 8,
        height_m: 6,
        pixels_per_meter: Number(editor("scale").value),
        dock_pose: {
          x_m: Number(editor("dock-x").value),
          y_m: Number(editor("dock-y").value),
          heading_rad: 0,
        },
        obstacles,
        targets,
        source_version: root.querySelector<HTMLElement>("[data-field='scene-editor']")!.dataset.sourceVersion || null,
        photo_reference_sha256: photoReferenceSha256,
      });
      scenarios.push(saved);
      selector.add(new Option(saved.name, saved.scenario_version));
      selector.value = saved.scenario_version;
      scenario = saved;
      showScenario();
      const groundingPhrase = saved.target.label.toLowerCase();
      const groundingSlug = groundingPhrase.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      setText(
        root,
        "scene-validation",
        `Confirmed and saved immutable version ${saved.scenario_version}. To ground this exact render, manually authorize one call: uv run python scripts/smoke_sam.py --scenario ${saved.scenario_version} --phrase "${groundingPhrase}" --output .roveredge/grounding/${saved.scenario_version}--${groundingSlug}.json --confirm-live-provider-call`,
      );
    } catch (error) {
      setText(root, "scene-validation", error instanceof Error ? error.message : String(error));
    }
  });
  root
    .querySelector("[data-action='timeout']")!
    .addEventListener("click", () =>
      void run(() =>
        api.run({
          ...scenario.default_run_request,
          configuration: { ...scenario.default_run_request.configuration, timeout_s: 2 },
          expected_mission_outcome: "timed_out",
        }),
      ),
    );
  root.querySelector("[data-action='play']")!.addEventListener("click", () => {
    if (!replay) return;
    replay.play();
    replayStartedAt = 0;
    replayStartTime = replay.currentEvent().simulated_time_s;
    requestAnimationFrame(animate);
  });
  root.querySelector("[data-action='pause']")!.addEventListener("click", () => replay?.pause());
  root.querySelector("[data-action='restart']")!.addEventListener("click", () => {
    replay?.restart();
    render();
  });
  root.querySelector("[data-action='scrub']")!.addEventListener("input", (event) => {
    replay?.scrubTo(Number((event.target as HTMLInputElement).value));
    render();
  });
  root.querySelector<HTMLButtonElement>("[data-action='start']")!.disabled = false;
  selector.disabled = false;
}

async function requestJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const error = (await response.json()) as {
      detail?: string | Array<{ msg?: string }> | {
        message?: string;
        provider_calls_used?: number;
        model?: string;
      };
    };
    const detail = Array.isArray(error.detail)
      ? error.detail.map((item) => item.msg).filter(Boolean).join("; ")
      : typeof error.detail === "object" && error.detail
        ? error.detail.message
        : error.detail;
    const requestError = new Error(detail || `Request failed with status ${response.status}`) as Error & {
      providerCallsUsed?: number;
      model?: string;
    };
    if (typeof error.detail === "object" && error.detail && !Array.isArray(error.detail)) {
      requestError.providerCallsUsed = error.detail.provider_calls_used;
      requestError.model = error.detail.model;
    }
    throw requestError;
  }
  return (await response.json()) as T;
}

async function requestBlob(path: string, body: unknown): Promise<Blob> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = (await response.json()) as { detail?: string };
    throw new Error(error.detail || `Request failed with status ${response.status}`);
  }
  return response.blob();
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result)));
    reader.addEventListener("error", () => reject(new Error("Unable to read the selected photo")));
    reader.readAsDataURL(file);
  });
}

function setText(root: HTMLElement, field: string, value: string): void {
  root.querySelector<HTMLElement>(`[data-field='${field}']`)!.textContent = value;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function formatConfiguration(request: RunRequest): string {
  const { configuration } = request;
  const parts = [
    `${configuration.simulation_step_s * 1000} ms step`,
    `${configuration.physics_step_s * 1000} ms physics`,
    `${configuration.planning_period_s * 1000} ms planning`,
    `${configuration.rover_radius_m} m rover radius`,
    `${configuration.motion.max_linear_speed_mps} m/s linear max`,
    `${configuration.motion.max_angular_speed_radps} rad/s angular max`,
    `${configuration.max_linear_acceleration_mps2} m/s² linear acceleration`,
    `${configuration.max_braking_deceleration_mps2} m/s² braking`,
    `${configuration.max_angular_acceleration_radps2} rad/s² angular acceleration`,
    `${configuration.range_ray_count} fixed range rays`,
    `${configuration.range_max_m} m sensor range`,
    `${configuration.inspection.position_tolerance_m} m inspection position tolerance`,
    `${configuration.inspection.heading_tolerance_rad} rad inspection heading tolerance`,
    `${configuration.inspection.dwell_s} s dwell`,
    `${configuration.dock.position_tolerance_m} m dock position tolerance`,
    `${configuration.dock.heading_tolerance_rad} rad dock heading tolerance`,
    `${configuration.timeout_s} s timeout`,
    `${humanize(configuration.controller_kind)} controller`,
    `${humanize(configuration.inference_backend ?? "python-reference")} inference`,
    `${configuration.inference_workers ?? 1} inference worker(s)`,
    `${humanize(configuration.execution_mode ?? "synchronous")} execution`,
  ];
  const device = configuration.modeled_device;
  if (device) {
    parts.push(
      `${humanize(device.queue_policy)} queue`,
      `${device.pending_capacity} pending capacity`,
      `${device.deadline_s} s reporting deadline`,
      `${device.maximum_age_s} s maximum age`,
      `${device.dispatch_s}/${device.input_transfer_s}/${device.compute_s}/${device.output_transfer_s} s dispatch/input/compute/output`,
      `${device.memory_budget_bytes} B modeled memory budget`,
    );
  }
  return parts.join(" · ");
}

function formatRuntimeEvidence(result: RunResult): string {
  if (!result.inference_backend) return "Not applicable";
  const provenance = result.runtime_provenance;
  const parts = [
    result.inference_backend,
    `disagreements ${result.command_disagreements ?? "not compared"}`,
    provenance?.timing_provenance ?? "reference execution",
  ];
  if (provenance?.comparison_correctness) {
    parts.push(`correctness ${provenance.comparison_correctness}`);
    parts.push(`${provenance.kernel} · block ${provenance.block_size}`);
    parts.push(`input ${provenance.saved_input_sha256?.slice(0, 12)}…`);
    parts.push(provenance.comparison_evidence ?? "comparison evidence unavailable");
  }
  if (
    provenance?.comparison_correctness === "passed" &&
    provenance.naive_median_us &&
    provenance.blocked_median_us
  ) {
    parts.push(`naive ${provenance.naive_median_us} µs median`);
    parts.push(`blocked ${provenance.blocked_median_us} µs median`);
  }
  if (
    provenance?.comparison_correctness === "passed" &&
    provenance.serial_blocked_median_us &&
    provenance.parallel_median_us
  ) {
    parts.push(`workers ${provenance.worker_count}`);
    parts.push(`serial blocked ${provenance.serial_blocked_median_us} µs median`);
    parts.push(`parallel ${provenance.parallel_median_us} µs median`);
  }
  if (
    provenance?.comparison_correctness === "passed" &&
    provenance.recorded_hardware_model &&
    provenance.naive_median_us &&
    provenance.accelerate_median_us
  ) {
    parts.push(`recorded ${provenance.recorded_hardware_model}`);
    parts.push(`naive ${provenance.naive_median_us} µs median`);
    parts.push(`Accelerate ${provenance.accelerate_median_us} µs median`);
  }
  return parts.join(" · ");
}

function formatModeledMemory(result: RunResult): string {
  const summary = result.inference_summary;
  if (!summary || summary.timing_provenance !== "modeled") return "Not applicable";
  const recovered =
    summary.pending_payload_bytes === 0 && summary.in_flight_payload_bytes === 0
      ? "recovered request payloads"
      : "request payloads still allocated";
  return [
    "modeled allocation",
    `resident weights ${summary.resident_weights_bytes} B`,
    `reusable workspace ${summary.workspace_bytes} B`,
    `pending payloads ${summary.pending_payload_bytes} B`,
    `in-flight payloads ${summary.in_flight_payload_bytes} B`,
    `current ${summary.current_modeled_memory_bytes} B`,
    `peak ${summary.peak_modeled_memory_bytes} B`,
    `budget ${summary.memory_budget_bytes} B`,
    `rejections ${summary.memory_rejections}`,
    recovered,
  ].join(" · ");
}

function formatNativePaced(result: RunResult): string {
  const summary = result.inference_summary;
  if (!summary || summary.timing_provenance !== "measured") return "Not applicable";
  const completion = [...result.trace]
    .reverse()
    .find((event) => event.inference_event_kind === "completed");
  const decision = [...result.trace]
    .reverse()
    .find((event) => event.kind === "control_decision");
  return [
    "measured native paced",
    `execution ${completion?.measured_execution_s?.toFixed(6) ?? "unavailable"} s`,
    `observation age ${decision?.observation_age_s?.toFixed(3) ?? "unavailable"} s`,
    `request ${decision?.request_id ?? "unavailable"}`,
    `observation ${decision?.observation_id ?? "unavailable"}`,
    `overruns ${summary.pacing_overruns ?? 0}`,
    `maximum overrun ${Number(summary.maximum_pacing_overrun_s ?? 0).toFixed(6)} s`,
  ].join(" · ");
}

function formatConfigurationValidity(result: RunResult): string {
  const validity = result.configuration_validity;
  if (!validity) return "Not available";
  const warnings = validity.warnings.length
    ? validity.warnings.join("; ")
    : "no training-domain warnings";
  return `${validity.configuration_id} · fixed ${validity.rover_type} · fixed ${validity.model_feature_count}-feature model · training domain ${validity.training_domain_status} · ${warnings}`;
}

function formatComparisonValidity(
  previous: RunRequest | undefined,
  current: RunRequest,
  declaredFactor?: string,
): string {
  if (!previous) return "First successful configuration; comparison not yet available";
  const differences = runRequestDifferences(previous, current);
  if (differences.length === 0) return "Reproducible replay · no configuration differences";
  if (declaredFactor) {
    const valid = differences.length === 1 && differences[0] === declaredFactor;
    return valid
      ? `Controlled comparison valid · declared factor ${declaredFactor}`
      : `Controlled comparison invalid · declared ${declaredFactor} · actual differences: ${differences.join(", ")} · no isolated-cause claim permitted`;
  }
  return `Exploratory comparison · ${differences.length} changed settings: ${differences.join(", ")} · no isolated-cause claim permitted`;
}

function formatComparisonEvidence(before: RunResult, after: RunResult): string {
  const evidence = (label: string, run: RunResult): string => {
    const timing =
      String(run.inference_summary?.timing_provenance ?? "") ||
      run.runtime_provenance?.timing_provenance ||
      "not measured";
    const runtime = run.inference_summary
      ? `${timing}, completed ${run.inference_summary.completed ?? 0}, dropped ${run.inference_summary.dropped_total ?? 0}, deadline misses ${run.inference_summary.deadline_misses ?? 0}`
      : `${timing}${run.runtime_provenance?.kernel ? `, ${run.runtime_provenance.kernel}` : ""}`;
    return `${label} ${run.run_id} · model ${run.model_sha256?.slice(0, 12) ?? "not used"} · numerical disagreements ${run.command_disagreements ?? "not compared"} · runtime ${runtime} · mission ${run.mission_outcome} · test ${run.test_verdict}`;
  };
  return `${evidence("before", before)} | ${evidence("after", after)}`;
}

function runRequestDifferences(previous: RunRequest, current: RunRequest): string[] {
  const flatten = (value: unknown, prefix = ""): Record<string, unknown> => {
    if (typeof value !== "object" || value === null) {
      return { [prefix]: value };
    }
    if (Array.isArray(value)) {
      return value.reduce<Record<string, unknown>>((result, child, index) => {
        const path = `${prefix}[${index}]`;
        return { ...result, ...flatten(child, path) };
      }, {});
    }
    return Object.entries(value).reduce<Record<string, unknown>>((result, [key, child]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return { ...result, ...flatten(child, path) };
    }, {});
  };
  const before = flatten(previous);
  const after = flatten(current);
  return [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .filter((key) => before[key] !== after[key])
    .sort();
}

function populateExperimentForm(root: HTMLElement, request: RunRequest): void {
  const configuration = request.configuration;
  const device = configuration.modeled_device!;
  const values: Record<string, number | string> = {
    "rover-radius": configuration.rover_radius_m,
    "max-linear-speed": configuration.motion.max_linear_speed_mps,
    "max-angular-speed": configuration.motion.max_angular_speed_radps,
    "linear-acceleration": configuration.max_linear_acceleration_mps2,
    "braking-deceleration": configuration.max_braking_deceleration_mps2,
    "angular-acceleration": configuration.max_angular_acceleration_radps2,
    "sensor-range": configuration.range_max_m,
    "planning-period": configuration.planning_period_s,
    backend: configuration.inference_backend ?? "python-reference",
    workers: configuration.inference_workers ?? 1,
    "execution-mode": configuration.execution_mode ?? "synchronous",
    "queue-policy": device.queue_policy,
    "pending-capacity": device.pending_capacity,
    deadline: device.deadline_s,
    "maximum-age": device.maximum_age_s,
    dispatch: device.dispatch_s,
    "input-transfer": device.input_transfer_s,
    compute: device.compute_s,
    "output-transfer": device.output_transfer_s,
    "memory-budget": device.memory_budget_bytes,
  };
  for (const [name, value] of Object.entries(values)) {
    const element = root.querySelector<HTMLInputElement | HTMLSelectElement>(
      `[data-setting='${name}']`,
    )!;
    element.value = String(value);
  }
}

function configuredRequest(root: HTMLElement, base: RunRequest): RunRequest {
  const value = (name: string): string =>
    root.querySelector<HTMLInputElement | HTMLSelectElement>(
      `[data-setting='${name}']`,
    )!.value;
  const number = (name: string): number => Number(value(name));
  const device = base.configuration.modeled_device!;
  return {
    ...base,
    configuration: {
      ...base.configuration,
      rover_radius_m: number("rover-radius"),
      motion: {
        max_linear_speed_mps: number("max-linear-speed"),
        max_angular_speed_radps: number("max-angular-speed"),
      },
      max_linear_acceleration_mps2: number("linear-acceleration"),
      max_braking_deceleration_mps2: number("braking-deceleration"),
      max_angular_acceleration_radps2: number("angular-acceleration"),
      range_max_m: number("sensor-range"),
      planning_period_s: number("planning-period"),
      controller_kind: "learned_collision_risk",
      inference_backend: value("backend") as NonNullable<
        RunRequest["configuration"]["inference_backend"]
      >,
      inference_workers: number("workers"),
      execution_mode: value("execution-mode") as NonNullable<
        RunRequest["configuration"]["execution_mode"]
      >,
      modeled_device: {
        ...device,
        queue_policy: value("queue-policy") as "fifo" | "latest_pending",
        pending_capacity: number("pending-capacity"),
        deadline_s: number("deadline"),
        maximum_age_s: number("maximum-age"),
        dispatch_s: number("dispatch"),
        input_transfer_s: number("input-transfer"),
        compute_s: number("compute"),
        output_transfer_s: number("output-transfer"),
        memory_budget_bytes: number("memory-budget"),
      },
    },
  };
}

function drawScene(
  canvas: HTMLCanvasElement,
  scenario: Scenario,
  result: RunResult,
  event: TraceEvent,
): void {
  let context: CanvasRenderingContext2D | null = null;
  try {
    context = canvas.getContext("2d");
  } catch {
    return;
  }
  if (!context) return;
  const scaleX = canvas.width / scenario.map_bounds_m.width;
  const scaleY = canvas.height / scenario.map_bounds_m.height;
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#ecf3ee";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#6b746f";
  for (const obstacle of scenario.obstacles) {
    context.fillRect(
      obstacle.x_min_m * scaleX,
      obstacle.y_min_m * scaleY,
      (obstacle.x_max_m - obstacle.x_min_m) * scaleX,
      (obstacle.y_max_m - obstacle.y_min_m) * scaleY,
    );
  }
  context.strokeStyle = "#3d6d8c";
  context.lineWidth = 2;
  for (const route of result.planned_routes) {
    context.beginPath();
    route.forEach((waypoint, index) => {
      const x = waypoint.x_m * scaleX;
      const y = waypoint.y_m * scaleY;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.stroke();
  }
  context.fillStyle = "#d36b3f";
  context.fillRect(
    (scenario.target.center_m.x - scenario.target.size_m.width / 2) * scaleX,
    (scenario.target.center_m.y - scenario.target.size_m.height / 2) * scaleY,
    scenario.target.size_m.width * scaleX,
    scenario.target.size_m.height * scaleY,
  );
  context.fillStyle = "#243a32";
  context.beginPath();
  context.arc(event.pose.x_m * scaleX, event.pose.y_m * scaleY, 10, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = "#f8f4e8";
  context.beginPath();
  context.moveTo(event.pose.x_m * scaleX, event.pose.y_m * scaleY);
  context.lineTo(
    event.pose.x_m * scaleX + Math.cos(event.pose.heading_rad) * 18,
    event.pose.y_m * scaleY + Math.sin(event.pose.heading_rad) * 18,
  );
  context.stroke();
  const rangeEvent = result.trace
    .slice(0, event.sequence + 1)
    .reverse()
    .find((item) => item.kind === "range_sampled" && item.range_readings_m);
  if (rangeEvent?.range_readings_m) {
    context.strokeStyle = "rgba(211, 107, 63, 0.35)";
    context.lineWidth = 1;
    rangeEvent.range_readings_m.forEach((distance, index) => {
      const angle = rangeEvent.pose.heading_rad + (index * 2 * Math.PI) / rangeEvent.range_readings_m!.length;
      context.beginPath();
      context.moveTo(rangeEvent.pose.x_m * scaleX, rangeEvent.pose.y_m * scaleY);
      context.lineTo(
        (rangeEvent.pose.x_m + Math.cos(angle) * distance) * scaleX,
        (rangeEvent.pose.y_m + Math.sin(angle) * distance) * scaleY,
      );
      context.stroke();
    });
  }
  if (event.phase === "collision" && result.terminal_failure?.contact_point) {
    context.strokeStyle = "#b42318";
    context.lineWidth = 4;
    context.beginPath();
    context.arc(
      result.terminal_failure.contact_point.x_m * scaleX,
      result.terminal_failure.contact_point.y_m * scaleY,
      9,
      0,
      Math.PI * 2,
    );
    context.stroke();
  }
}

function showGroundingEvidence(root: HTMLElement, result: RunResult): void {
  const figure = root.querySelector<HTMLElement>("[data-field='grounding-preview']")!;
  const evidence = result.grounding_evidence;
  if (!evidence || evidence.matches.length === 0) {
    figure.hidden = true;
    return;
  }
  figure.hidden = false;
  figure.dataset.renderSha256 = evidence.render_sha256;
  figure.querySelector<HTMLElement>("figcaption")!.textContent =
    `${evidence.source} ${evidence.model} mask over render ${evidence.render_sha256}`;
  if (typeof Image === "undefined") return;
  const canvas = figure.querySelector<HTMLCanvasElement>("canvas")!;
  canvas.width = evidence.render_width_px;
  canvas.height = evidence.render_height_px;
  const image = new Image();
  image.addEventListener("load", () => {
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const overlayCanvas = document.createElement("canvas");
    overlayCanvas.width = canvas.width;
    overlayCanvas.height = canvas.height;
    const overlayContext = overlayCanvas.getContext("2d");
    if (!overlayContext) return;
    const overlay = overlayContext.createImageData(canvas.width, canvas.height);
    for (const match of evidence.matches) {
      let pixel = 0;
      let value = 0;
      for (const run of match.mask.counts) {
        if (value === 1) {
          for (let offset = 0; offset < run; offset += 1) {
            const index = (pixel + offset) * 4;
            overlay.data[index] = 255;
            overlay.data[index + 1] = 52;
            overlay.data[index + 2] = 112;
            overlay.data[index + 3] = 112;
          }
        }
        pixel += run;
        value = 1 - value;
      }
    }
    overlayContext.putImageData(overlay, 0, 0);
    context.drawImage(overlayCanvas, 0, 0);
  });
  image.src = `/api/scenarios/${encodeURIComponent(result.request.scenario_version)}/render`;
}

function applicationMarkup(): string {
  return `
    <header class="workshop-header"><a href="#app" class="wordmark">RoverEdge</a><nav aria-label="Workshop sections"><a href="#mission">Mission</a><a href="#experiment">Experiment</a><a href="#evidence">Evidence</a></nav><span>Robotics experiment workshop</span></header>
    <section class="hero">
      <h1>Inspect the target. Test the delay.</h1>
      <p class="intro">See how old inference changes a simulated inspection mission.</p>
      <p data-field="scenario">Loading preset…</p>
      <p>Target: <strong data-field="target">—</strong></p>
      <label>Scenario <select data-action="scenario" aria-label="Scenario"></select></label>
      <details class="setup-disclosure" id="experiment"><summary>Set up an experiment</summary>
      <section data-field="scene-editor" class="scene-editor">
        <h2>Scene editor</h2>
        <div class="controls">
          <button data-scene-action="preset">Edit selected preset</button>
          <button data-scene-action="empty">Start empty</button>
          <label>Photo reference <input data-action="photo-upload" type="file" accept="image/png,image/jpeg"></label>
          <button data-scene-action="photo-draft">Generate rough uncertain draft</button>
          <label>Name <input data-editor="name" value="Untitled inspection scene"></label>
          <label>Scale (px/m) <input data-editor="scale" type="number" min="20" max="400" value="100"></label>
          <label>Dock X <input data-editor="dock-x" type="number" step="0.1" value="1"></label>
          <label>Dock Y <input data-editor="dock-y" type="number" step="0.1" value="3"></label>
          <label>Obstacle footprints <input data-editor="obstacle" placeholder="x min, y min, x max, y max; …"></label>
          <label>Target footprints <input data-editor="target" placeholder="Red toolbox:x min, y min, x max, y max; Blue barrel:…"></label>
          <label>Target <select data-editor="target-label"><option>Red toolbox</option><option>Blue barrel</option></select></label>
          <button data-scene-action="save">Confirm and save new version</button>
        </div>
        <p data-field="scene-validation">Load a preset or start empty. Saving validates geometry and creates a new immutable version.</p>
        <p data-field="photo-draft-status">Photo drafting uses rough color-region proposals and never claims metric reconstruction.</p>
        <img data-field="photo-reference" alt="Original uploaded photo reference" hidden>
        <fieldset>
          <legend>Required photo-draft confirmation</legend>
          <label><input type="checkbox" data-photo-confirmation="scale"> Scale corrected or confirmed</label>
          <label><input type="checkbox" data-photo-confirmation="obstacles"> Obstacle footprints corrected or confirmed</label>
          <label><input type="checkbox" data-photo-confirmation="dock"> Dock corrected or confirmed</label>
          <label><input type="checkbox" data-photo-confirmation="targets"> Targets corrected or confirmed</label>
        </fieldset>
        <figure>
          <canvas data-field="scene-preview" width="800" height="600" aria-label="Editable top-down scene confirmation preview"></canvas>
          <figcaption data-field="scene-preview-scale">100 px/m declared scale</figcaption>
        </figure>
      </section>
      <div class="actions advanced-actions">
        <button data-action="learned">Run learned controller</button>
        <button data-action="native">Run native naive</button>
        <button data-action="native-paced">Run native paced</button>
        <button data-action="blocked">Run native blocked</button>
        <button data-action="parallel">Run native parallel (4 workers)</button>
        <button data-action="accelerate">Run Apple Accelerate</button>
        <button data-action="timeout" class="secondary">Run expected timeout</button>
      </div>
      <div class="grounding-controls">
        <label>Visual target phrase
          <input data-action="target-phrase" value="red toolbox" maxlength="120">
        </label>
        <button data-action="grounded-recorded">Run recorded grounding replay</button>
        <p>Live Meta grounding is run only through the guarded manual smoke command.</p>
      </div>
      <div class="grounding-controls">
        <label>Required target sequence
          <input data-action="multi-target-ids" value="preset-storage-container, secondary-inspection-point">
        </label>
        <button data-action="multi-target">Run multi-target mission</button>
      </div>
      <figure class="grounding-preview" data-field="grounding-preview" hidden>
        <canvas width="800" height="600" aria-label="Recorded grounding mask over exact scenario render"></canvas>
        <figcaption></figcaption>
      </figure>
        <div class="actions">
          <label>Modeled allocation budget (bytes)
            <input data-action="memory-budget" aria-label="Modeled allocation budget bytes" type="number" min="0" step="1">
          </label>
          <button data-action="modeled-memory">Run modeled memory experiment</button>
        </div>
        <div class="actions">
          <button data-action="export-run">Download run evidence bundle</button>
          <button data-action="export-comparison">Download comparison evidence bundle</button>
        </div>
        <details>
          <summary>Configure rover and device experiment</summary>
          <div class="configuration-grid">
            <label>Rover radius (m)<input data-setting="rover-radius" type="number" step="0.01"></label>
            <label>Maximum linear speed (m/s)<input data-setting="max-linear-speed" type="number" step="0.01"></label>
            <label>Maximum angular speed (rad/s)<input data-setting="max-angular-speed" type="number" step="0.01"></label>
            <label>Linear acceleration (m/s²)<input data-setting="linear-acceleration" type="number" step="0.01"></label>
            <label>Braking deceleration (m/s²)<input data-setting="braking-deceleration" type="number" step="0.01"></label>
            <label>Angular acceleration (rad/s²)<input data-setting="angular-acceleration" type="number" step="0.01"></label>
            <label>Sensor range (m)<input data-setting="sensor-range" type="number" step="0.1"></label>
            <label>Planning period (s)<input data-setting="planning-period" type="number" step="0.001"></label>
            <label>Inference backend<select data-setting="backend">
              <option value="python-reference">Python reference</option>
              <option value="native-naive">Native naive</option>
              <option value="native-blocked">Native blocked</option>
              <option value="native-parallel-blocked">Native parallel blocked</option>
              <option value="native-accelerate">Apple Accelerate</option>
            </select></label>
            <label>Inference workers<select data-setting="workers">
              <option value="1">1</option><option value="2">2</option><option value="4">4</option>
            </select></label>
            <label>Execution mode<select data-setting="execution-mode">
              <option value="synchronous">Synchronous</option>
              <option value="virtual_fifo">Virtual modeled device</option>
              <option value="native_paced">Native wall-clock paced</option>
            </select></label>
            <label>Queue policy<select data-setting="queue-policy">
              <option value="fifo">FIFO</option><option value="latest_pending">Latest pending</option>
            </select></label>
            <label>Pending capacity<input data-setting="pending-capacity" type="number" step="1"></label>
            <label>Reporting deadline (s)<input data-setting="deadline" type="number" step="0.001"></label>
            <label>Maximum observation age (s)<input data-setting="maximum-age" type="number" step="0.001"></label>
            <label>Dispatch cost (s)<input data-setting="dispatch" type="number" step="0.001"></label>
            <label>Input transfer cost (s)<input data-setting="input-transfer" type="number" step="0.001"></label>
            <label>Compute cost (s)<input data-setting="compute" type="number" step="0.001"></label>
            <label>Output transfer cost (s)<input data-setting="output-transfer" type="number" step="0.001"></label>
            <label>Modeled memory budget (bytes)<input data-setting="memory-budget" type="number" step="1"></label>
          </div>
          <p>Fixed contract: differential-drive rover · 16 range rays · 24 model features · fixed candidate structure.</p>
          <button data-action="configured-run">Run saved configuration</button>
        </details>
        <div class="actions">
          <label>Comparison mode<select data-action="comparison-mode">
            <option value="exploratory">Exploratory</option>
            <option value="controlled">Controlled one-factor</option>
          </select></label>
          <label>Declared factor path<input data-action="declared-factor" value="configuration.rover_radius_m"></label>
        </div>
      </details>
    </section>
    <section class="mission-grid" id="mission">
      <div class="stage">
        <canvas data-field="presentation-canvas" width="1200" height="660" aria-label="Interactive 3D presentation of the recorded warehouse mission. Drag to orbit; use arrow keys to orbit and plus or minus to zoom."></canvas>
        <div class="stage-tools"><span>Recorded 3D replay · drag to orbit · wheel or +/− to zoom</span><button class="secondary" data-action="reset-camera">Reset camera</button></div>
        <div class="stage-caption" data-field="stage-caption">Presentation view follows recorded scenario geometry and rover poses.</div>
        <details class="technical-map"><summary>Inspect synchronized top-down map</summary><canvas width="800" height="600" aria-label="Recorded mission replay"></canvas><canvas data-field="comparison-canvas" width="800" height="600" aria-label="Before mission replay"></canvas></details>
      </div>
      <aside class="mission-brief"><h2>Mission brief</h2><dl><dt>Task</dt><dd>Inspect the selected target and return to dock</dd><dt>Target</dt><dd data-field="brief-target">—</dd><dt>Phase</dt><dd data-field="brief-phase">Not started</dd><dt>Source</dt><dd data-field="run-source">No run selected</dd></dl><button data-action="start">Run mission</button></aside>
    </section>
    <section class="replay-controls">
      <button data-action="play">Play</button>
      <button data-action="pause">Pause</button>
      <button data-action="restart">Restart</button>
      <input data-action="scrub" aria-label="Replay time" type="range" min="0" max="0" step="0.05" value="0" disabled>
    </section>
    <section class="primary-evidence" aria-label="Current mission evidence"><div><span>Mission outcome</span><strong data-field="mission-outcome-primary">—</strong></div><div><span>Test verdict</span><strong data-field="test-verdict-primary">—</strong></div><div><span>Observation age at replay time</span><strong data-field="prediction-age-primary">Not available</strong></div></section>
    <section class="experiment-story" aria-label="Run explanation"><h2>What happened in this mission?</h2><p data-field="run-explanation">Run a mission to see whether the rover inspected its target and returned to dock.</p><h2>Investigate with the mission engineer</h2><p>The Meta model reads this run, tests a bounded configuration change, and explains the recorded result.</p><label>Investigation question <textarea data-action="investigation-question" rows="3">Why did this mission finish or stop? Inspect the trace, test one supported change, and explain whether it helped.</textarea></label><p><label><input type="checkbox" data-action="provider-consent"> Send this run and question to Baseten for two Meta model requests and up to three local follow-up simulations.</label></p><button data-action="investigate" disabled>Investigate this run</button><p data-field="investigation-result" role="status">Run a mission first.</p><p data-field="investigation-source">No provider requests made for this investigation yet.</p></section>
    <section class="experiment-story"><h2>Does processing older observations affect this mission?</h2><p>FIFO processes observations in arrival order. Latest pending replaces waiting observations with newer ones. Compare their progress under the same simulated delay. Expired results cannot drive the rover. Compute time is only one part of total inference latency, and outcomes remain scenario-dependent.</p><p><strong>Recommended latency demonstration:</strong> use Open inspection lane or Perception feasibility room. In the other scenarios, perception or physical constraints can determine the outcome before queue policy does.</p><div class="story-facts"><span>Changed factor: queue policy</span><label>Simulated compute time <select data-action="comparison-delay"><option value="0.02">20 ms compute</option><option value="0.08" selected>80 ms compute (congested)</option></select></label><span>Pending capacity: 4</span></div><button data-action="queue-comparison">Run queue comparison</button><p data-field="story-result" role="status">Run both policies to compare their actual outcomes.</p><table class="comparison-table"><caption>Paired modeled runs on the selected mission</caption><thead><tr><th scope="col">Policy</th><th scope="col">Mission outcome</th><th scope="col">Accepted decision age (whole run)</th><th scope="col">Pending replacements</th></tr></thead><tbody><tr><th scope="row">FIFO</th><td data-field="fifo-outcome">—</td><td data-field="fifo-age">—</td><td data-field="fifo-replacements">—</td></tr><tr><th scope="row">Latest pending</th><td data-field="latest-outcome">—</td><td data-field="latest-age">—</td><td data-field="latest-replacements">—</td></tr></tbody></table><a href="#experiment">Configure another experiment</a></section>
    <details class="evidence" id="evidence"><summary>Technical details and reproducibility</summary>
        <dl>
          <dt>Run</dt><dd data-field="run-id">—</dd>
          <dt>Scenario version</dt><dd data-field="scenario-version">—</dd>
          <dt>Seed</dt><dd data-field="seed">—</dd>
          <dt>Expectation</dt><dd data-field="expectation">—</dd>
          <dt>Configuration</dt><dd data-field="configuration">—</dd>
          <dt>Target grounding</dt><dd data-field="grounding">Not used</dd>
          <dt>Controller</dt><dd data-field="controller">—</dd>
          <dt>Risk model</dt><dd data-field="model">Not used</dd>
          <dt>Validation evidence</dt><dd data-field="validation">Not applicable</dd>
          <dt>Held-out readiness</dt><dd data-field="held-out-readiness">Not loaded</dd>
          <dt>Inference runtime</dt><dd data-field="runtime">Not applicable</dd>
          <dt>Modeled memory</dt><dd data-field="modeled-memory">Not applicable</dd>
          <dt>Native paced timing</dt><dd data-field="native-paced">Not applicable</dd>
          <dt>Configuration validity</dt><dd data-field="configuration-validity">Not available</dd>
          <dt>Comparison validity</dt><dd data-field="comparison-validity">Not available</dd>
          <dt>Paired comparison evidence</dt><dd data-field="comparison-evidence">Run a second experiment to compare recorded evidence</dd>
          <dt>Aligned replay time</dt><dd data-field="comparison-time">Not available</dd>
          <dt>Configuration error</dt><dd data-field="configuration-error">None</dd>
          <dt>Accelerate comparison</dt><dd data-field="accelerate-comparison">Recorded evidence unavailable</dd>
          <dt>Phase</dt><dd data-field="phase">Not started</dd>
          <dt>Simulated time</dt><dd data-field="time">0.00 s</dd>
          <dt>Motion</dt><dd data-field="motion">0.000 m/s · 0.000 rad/s</dd>
          <dt>Replay evidence</dt><dd data-field="replay-evidence">None</dd>
          <dt>Learned decision</dt><dd data-field="decision">None</dd>
          <dt>Prediction age</dt><dd data-field="prediction-age">Not available</dd>
          <dt>Queue state</dt><dd data-field="queue-state">Not available</dd>
          <dt>Mission outcome</dt><dd data-field="outcome">—</dd>
          <dt>Required target visits</dt><dd data-field="target-visits">Not available</dd>
          <dt>Test verdict</dt><dd data-field="verdict">—</dd>
          <dt>Terminal failure</dt><dd data-field="failure">None</dd>
        </dl>
        <p data-field="status">Ready to run.</p>
    </details>
    <section class="timeline"><h2>Mission phases</h2><p data-field="phases">No recorded run yet.</p></section>
  `;
}
