import type { RunResult } from "./app";

export function summarizeRun(run: RunResult) {
  const decisions = run.trace.filter(event => event.kind === "control_decision" && event.observation_age_s != null);
  const ages = decisions.map(event => event.observation_age_s!);
  const poses = run.trace.filter(event => event.kind === "pose_sample").map(event => event.pose);
  const distance = poses.slice(1).reduce((sum, pose, index) => sum + Math.hypot(pose.x_m - poses[index]!.x_m, pose.y_m - poses[index]!.y_m), 0);
  return {
    inspections: run.observations.length,
    duration: run.trace.at(-1)?.simulated_time_s ?? 0,
    distance,
    decisions: decisions.length,
    meanAge: ages.length ? ages.reduce((sum, age) => sum + age, 0) / ages.length : null,
    maxAge: ages.length ? Math.max(...ages) : null,
    expired: run.inference_summary?.expired ?? 0,
  };
}

export function explainRun(run: RunResult): string {
  const summary = summarizeRun(run);
  const timing = summary.meanAge == null
    ? "No observation-age samples were recorded for accepted decisions."
    : `${summary.decisions} decisions accepted; average observation age ${(summary.meanAge * 1000).toFixed(0)} ms, maximum ${(summary.maxAge! * 1000).toFixed(0)} ms. These samples describe acceptance time, not every moment a command was held.`;
  return `${run.terminal_reason}. ${summary.inspections} inspections captured in ${summary.duration.toFixed(2)} simulated seconds; ${summary.distance.toFixed(2)} m travelled. ${timing} ${summary.expired} requests or results expired under the configured freshness limit. Expected outcome: ${run.request.expected_mission_outcome.replaceAll("_", " ")}; test ${run.test_verdict}.`;
}
