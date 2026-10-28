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
    motion: { max_linear_speed_mps: number; max_angular_speed_radps: number };
    inspection: {
      position_tolerance_m: number;
      heading_tolerance_rad: number;
      dwell_s: number;
    };
    dock: { position_tolerance_m: number; heading_tolerance_rad: number };
    timeout_s: number;
  };
  expected_mission_outcome: "completed" | "timed_out";
}

interface TraceEvent extends ReplayEvent {
  kind: "phase_changed" | "pose_sample" | "observation_captured" | "terminal";
  pose: Pose;
  linear_velocity_mps: number;
  angular_velocity_radps: number;
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
  mission_outcome: "completed" | "timed_out";
  test_verdict: "passed" | "failed";
  terminal_reason: string;
}

export interface RoverEdgeApi {
  getPresetScenario(): Promise<Scenario>;
  run(request: RunRequest): Promise<RunResult>;
}

export const httpApi: RoverEdgeApi = {
  async getPresetScenario() {
    return requestJson<Scenario>("/api/scenarios/preset-open");
  },
  async run(request) {
    return requestJson<RunResult>("/api/runs", request);
  },
};

export async function mountApp(root: HTMLElement, api: RoverEdgeApi = httpApi): Promise<void> {
  root.innerHTML = applicationMarkup();
  const scenario = await api.getPresetScenario();
  setText(root, "scenario", `${scenario.name} · ${scenario.scenario_version}`);
  setText(root, "target", scenario.target.label);

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
    drawScene(root.querySelector("canvas")!, scenario, event);
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
    setText(root, "run-id", result.run_id);
    setText(root, "scenario-version", result.request.scenario_version);
    setText(root, "seed", String(result.request.simulation_seed));
    setText(root, "expectation", result.request.expected_mission_outcome);
    setText(root, "configuration", formatConfiguration(result.request));
    setText(root, "outcome", result.mission_outcome);
    setText(root, "verdict", result.test_verdict);
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
    `${configuration.motion.max_linear_speed_mps} m/s linear max`,
    `${configuration.motion.max_angular_speed_radps} rad/s angular max`,
    `${configuration.inspection.position_tolerance_m} m inspection position tolerance`,
    `${configuration.inspection.heading_tolerance_rad} rad inspection heading tolerance`,
    `${configuration.inspection.dwell_s} s dwell`,
    `${configuration.dock.position_tolerance_m} m dock position tolerance`,
    `${configuration.dock.heading_tolerance_rad} rad dock heading tolerance`,
    `${configuration.timeout_s} s timeout`,
  ].join(" · ");
}

function drawScene(canvas: HTMLCanvasElement, scenario: Scenario, event: TraceEvent): void {
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
}

function applicationMarkup(): string {
  return `
    <section class="hero">
      <p class="eyebrow">Deterministic reference mission</p>
      <h1>Inspect and return</h1>
      <p data-field="scenario">Loading preset…</p>
      <p>Target: <strong data-field="target">—</strong></p>
      <div class="actions">
        <button data-action="start">Start run</button>
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
          <dt>Phase</dt><dd data-field="phase">Not started</dd>
          <dt>Simulated time</dt><dd data-field="time">0.00 s</dd>
          <dt>Mission outcome</dt><dd data-field="outcome">—</dd>
          <dt>Test verdict</dt><dd data-field="verdict">—</dd>
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
