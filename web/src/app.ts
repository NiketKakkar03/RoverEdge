import { ReplayController, type ReplayEvent } from "./replay";

export interface Pose {
  x_m: number;
  y_m: number;
  heading_rad: number;
}

export interface Scenario {
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
}

export interface RunRequest {
  scenario_version: string;
  target_id: string;
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
  };
  expected_mission_outcome: "completed" | "timed_out" | "collision" | "unreachable";
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
    | "control_decision";
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
  mission_outcome: "completed" | "timed_out" | "collision" | "unreachable";
  test_verdict: "passed" | "failed";
  terminal_reason: string;
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
  terminal_failure?: {
    code: "collision" | "unreachable" | "timeout";
    message: string;
    pose: Pose;
    obstacle_id?: string | null;
    contact_point?: { x_m: number; y_m: number } | null;
  } | null;
}

export interface RoverEdgeApi {
  getScenarios(): Promise<Scenario[]>;
  getAccelerateComparison?(): Promise<AccelerateComparison>;
  run(request: RunRequest): Promise<RunResult>;
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
  async run(request) {
    return requestJson<RunResult>("/api/runs", request);
  },
};

export async function mountApp(root: HTMLElement, api: RoverEdgeApi = httpApi): Promise<void> {
  root.innerHTML = applicationMarkup();
  const scenarios = await api.getScenarios();
  let scenario = scenarios[0]!;
  const selector = root.querySelector<HTMLSelectElement>("[data-action='scenario']")!;
  for (const available of scenarios) {
    selector.add(new Option(available.name, available.scenario_version));
  }
  const showScenario = (): void => {
    setText(root, "scenario", `${scenario.name} · ${scenario.scenario_version}`);
    setText(root, "target", scenario.target.label);
  };
  showScenario();
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

  let result: RunResult | undefined;
  let replay: ReplayController | undefined;
  let replayStartedAt = 0;
  let replayStartTime = 0;

  const render = (): void => {
    if (!result || !replay) return;
    const event = replay.currentEvent() as TraceEvent;
    setText(root, "phase", humanize(event.phase));
    setText(root, "time", `${event.simulated_time_s.toFixed(2)} s`);
    const slider = root.querySelector<HTMLInputElement>("[data-action='scrub']")!;
    slider.value = String(event.simulated_time_s);
    drawScene(root.querySelector("canvas")!, scenario, result, event);
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
    result = await runRequest();
    replay = new ReplayController(result.trace);
    replayStartedAt = 0;
    replayStartTime = 0;
    setText(root, "status", result.terminal_reason);
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
  selector.addEventListener("change", () => {
    scenario = scenarios.find((item) => item.scenario_version === selector.value)!;
    showScenario();
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
}

async function requestJson<T>(path: string, body?: RunRequest): Promise<T> {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
  return (await response.json()) as T;
}

function setText(root: HTMLElement, field: string, value: string): void {
  root.querySelector<HTMLElement>(`[data-field='${field}']`)!.textContent = value;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function formatConfiguration(request: RunRequest): string {
  const { configuration } = request;
  return [
    `${configuration.simulation_step_s * 1000} ms step`,
    `${configuration.physics_step_s * 1000} ms physics`,
    `${configuration.planning_period_s * 1000} ms planning`,
    `${configuration.motion.max_linear_speed_mps} m/s linear max`,
    `${configuration.motion.max_angular_speed_radps} rad/s angular max`,
    `${configuration.inspection.position_tolerance_m} m inspection position tolerance`,
    `${configuration.inspection.heading_tolerance_rad} rad inspection heading tolerance`,
    `${configuration.inspection.dwell_s} s dwell`,
    `${configuration.dock.position_tolerance_m} m dock position tolerance`,
    `${configuration.dock.heading_tolerance_rad} rad dock heading tolerance`,
    `${configuration.timeout_s} s timeout`,
    `${humanize(configuration.controller_kind)} controller`,
    `${humanize(configuration.inference_backend ?? "python-reference")} inference`,
    `${configuration.inference_workers ?? 1} inference worker(s)`,
  ].join(" · ");
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

function applicationMarkup(): string {
  return `
    <section class="hero">
      <p class="eyebrow">Deterministic reference mission</p>
      <h1>Inspect and return</h1>
      <p data-field="scenario">Loading preset…</p>
      <p>Target: <strong data-field="target">—</strong></p>
      <label>Scenario <select data-action="scenario" aria-label="Scenario"></select></label>
      <div class="actions">
        <button data-action="start">Start run</button>
        <button data-action="learned">Run learned controller</button>
        <button data-action="native">Run native naive</button>
        <button data-action="blocked">Run native blocked</button>
        <button data-action="parallel">Run native parallel (4 workers)</button>
        <button data-action="accelerate">Run Apple Accelerate</button>
        <button data-action="timeout" class="secondary">Run expected timeout</button>
      </div>
    </section>
    <section class="mission-grid">
      <div class="stage"><canvas width="800" height="600" aria-label="Recorded mission replay"></canvas></div>
      <aside class="evidence">
        <p class="eyebrow">Recorded evidence</p>
        <dl>
          <dt>Run</dt><dd data-field="run-id">—</dd>
          <dt>Scenario version</dt><dd data-field="scenario-version">—</dd>
          <dt>Seed</dt><dd data-field="seed">—</dd>
          <dt>Expectation</dt><dd data-field="expectation">—</dd>
          <dt>Configuration</dt><dd data-field="configuration">—</dd>
          <dt>Controller</dt><dd data-field="controller">—</dd>
          <dt>Risk model</dt><dd data-field="model">Not used</dd>
          <dt>Validation evidence</dt><dd data-field="validation">Not applicable</dd>
          <dt>Inference runtime</dt><dd data-field="runtime">Not applicable</dd>
          <dt>Accelerate comparison</dt><dd data-field="accelerate-comparison">Recorded evidence unavailable</dd>
          <dt>Phase</dt><dd data-field="phase">Not started</dd>
          <dt>Simulated time</dt><dd data-field="time">0.00 s</dd>
          <dt>Motion</dt><dd data-field="motion">0.000 m/s · 0.000 rad/s</dd>
          <dt>Replay evidence</dt><dd data-field="replay-evidence">None</dd>
          <dt>Learned decision</dt><dd data-field="decision">None</dd>
          <dt>Mission outcome</dt><dd data-field="outcome">—</dd>
          <dt>Test verdict</dt><dd data-field="verdict">—</dd>
          <dt>Terminal failure</dt><dd data-field="failure">None</dd>
        </dl>
        <p data-field="status">Ready to run.</p>
      </aside>
    </section>
    <section class="replay-controls">
      <button data-action="play">Play</button>
      <button data-action="pause">Pause</button>
      <button data-action="restart">Restart</button>
      <input data-action="scrub" aria-label="Replay time" type="range" min="0" max="0" step="0.05" value="0" disabled>
    </section>
    <section class="timeline"><h2>Mission phases</h2><p data-field="phases">No recorded run yet.</p></section>
  `;
}
