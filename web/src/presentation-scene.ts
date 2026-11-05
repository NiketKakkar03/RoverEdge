import type { Pose, RunResult, Scenario } from "./app";

type Vec3 = [number, number, number];
type Camera = { yaw: number; pitch: number; distance: number; dragging: boolean; x: number; y: number };
type Renderer = { gl: WebGLRenderingContext; program: WebGLProgram; position: number; normal: number; model: WebGLUniformLocation; viewProjection: WebGLUniformLocation; color: WebGLUniformLocation; light: WebGLUniformLocation; buffer: WebGLBuffer };

const cameras = new WeakMap<HTMLCanvasElement, Camera>();
const renderers = new WeakMap<HTMLCanvasElement, Renderer | null>();
const redraws = new WeakMap<HTMLCanvasElement, () => void>();
const vertexShader = `attribute vec3 a_position; attribute vec3 a_normal; uniform mat4 u_model; uniform mat4 u_viewProjection; varying vec3 v_normal; varying vec3 v_position; void main() { vec4 world = u_model * vec4(a_position, 1.0); v_position = world.xyz; v_normal = mat3(u_model) * a_normal; gl_Position = u_viewProjection * world; }`;
const fragmentShader = `precision mediump float; uniform vec3 u_color; uniform vec3 u_light; varying vec3 v_normal; varying vec3 v_position; void main() { vec3 normal = normalize(v_normal); float direct = max(dot(normal, normalize(u_light)), 0.0); float rim = pow(1.0 - max(dot(normal, normalize(vec3(0.0, 5.0, 8.0) - v_position)), 0.0), 2.0); vec3 lit = u_color * (0.24 + direct * 0.76) + vec3(0.08, 0.12, 0.13) * rim; gl_FragColor = vec4(lit, 1.0); }`;

// Presentation only: every object comes from the recorded scenario and every pose from the trace.
export function drawPresentationScene(canvas: HTMLCanvasElement, scenario: Scenario, result?: RunResult, event?: { pose: Pose; phase: string }): void {
  redraws.set(canvas, () => drawPresentationScene(canvas, scenario, result, event));
  const renderer = getRenderer(canvas);
  if (!renderer) return;
  const { gl } = renderer;
  resize(canvas, gl);
  const camera = cameras.get(canvas) ?? defaultCamera();
  if (!cameras.has(canvas)) cameras.set(canvas, camera);
  const center: Vec3 = [scenario.map_bounds_m.width / 2, 0, scenario.map_bounds_m.height / 2];
  const eye: Vec3 = [center[0] + Math.sin(camera.yaw) * Math.cos(camera.pitch) * camera.distance, center[1] + Math.sin(camera.pitch) * camera.distance, center[2] + Math.cos(camera.yaw) * Math.cos(camera.pitch) * camera.distance];
  gl.viewport(0, 0, canvas.width, canvas.height); gl.clearColor(0.035, 0.063, 0.08, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.useProgram(renderer.program);
  gl.uniformMatrix4fv(renderer.viewProjection, false, multiply(perspective(Math.PI / 4, canvas.width / canvas.height, 0.1, 100), lookAt(eye, [center[0], 0.35, center[2]], [0, 1, 0]))); gl.uniform3f(renderer.light, -4, 8, 5);
  gl.bindBuffer(gl.ARRAY_BUFFER, renderer.buffer); gl.enableVertexAttribArray(renderer.position); gl.vertexAttribPointer(renderer.position, 3, gl.FLOAT, false, 24, 0); gl.enableVertexAttribArray(renderer.normal); gl.vertexAttribPointer(renderer.normal, 3, gl.FLOAT, false, 24, 12);
  const cube = (position: Vec3, scale: Vec3, color: Vec3, yaw = 0): void => drawCube(renderer, position, scale, color, yaw);
  const w = scenario.map_bounds_m.width, h = scenario.map_bounds_m.height;
  cube([w / 2, -0.08, h / 2], [w, 0.16, h], [0.15, 0.19, 0.19]);
  for (let x = 0; x <= w; x += 1) cube([x, 0.008, h / 2], [0.012, 0.012, h], [0.25, 0.31, 0.30]);
  for (let z = 0; z <= h; z += 1) cube([w / 2, 0.009, z], [w, 0.012, 0.012], [0.25, 0.31, 0.30]);
  cube([w / 2, 1.35, -0.06], [w + 0.12, 2.7, 0.12], [0.10, 0.15, 0.17]); cube([-0.06, 1.35, h / 2], [0.12, 2.7, h + 0.12], [0.10, 0.15, 0.17]);
  for (const obstacle of scenario.obstacles) cube([(obstacle.x_min_m + obstacle.x_max_m) / 2, 0.48, (obstacle.y_min_m + obstacle.y_max_m) / 2], [obstacle.x_max_m - obstacle.x_min_m, 0.96, obstacle.y_max_m - obstacle.y_min_m], [0.33, 0.42, 0.44]);
  const target = scenario.target;
  cube([target.center_m.x, target.size_m.height / 2, target.center_m.y], [target.size_m.width, target.size_m.height, target.size_m.width * 0.62], [0.72, 0.20, 0.13]); cube([target.center_m.x, target.size_m.height + 0.025, target.center_m.y], [target.size_m.width * 1.08, 0.05, target.size_m.width * 0.72], [0.95, 0.43, 0.20]);
  const dock = scenario.dock_pose;
  cube([dock.x_m, 0.03, dock.y_m], [0.96, 0.06, 0.72], [0.80, 0.53, 0.16], -dock.heading_rad); cube([dock.x_m, 0.07, dock.y_m], [0.62, 0.035, 0.46], [0.12, 0.17, 0.18], -dock.heading_rad);
  for (const route of result?.planned_routes ?? []) drawRoute(cube, route);
  drawRover(cube, event?.pose ?? dock, event?.phase === "collision");
}

export function attachPresentationCamera(canvas: HTMLCanvasElement): void {
  if (cameras.has(canvas)) return;
  cameras.set(canvas, defaultCamera()); canvas.tabIndex = 0;
  canvas.addEventListener("pointerdown", (event) => { const c = cameras.get(canvas)!; c.dragging = true; c.x = event.clientX; c.y = event.clientY; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener("pointermove", (event) => { const c = cameras.get(canvas)!; if (!c.dragging) return; c.yaw -= (event.clientX - c.x) * 0.012; c.pitch = Math.max(0.18, Math.min(1.12, c.pitch - (event.clientY - c.y) * 0.01)); c.x = event.clientX; c.y = event.clientY; });
  canvas.addEventListener("pointerup", () => { cameras.get(canvas)!.dragging = false; });
  canvas.addEventListener("wheel", (event) => { event.preventDefault(); const c = cameras.get(canvas)!; c.distance = Math.max(5, Math.min(18, c.distance + event.deltaY * 0.012)); }, { passive: false });
  canvas.addEventListener("keydown", (event) => { const c = cameras.get(canvas)!; if (event.key === "ArrowLeft") c.yaw += 0.12; else if (event.key === "ArrowRight") c.yaw -= 0.12; else if (event.key === "ArrowUp") c.pitch = Math.min(1.12, c.pitch + 0.08); else if (event.key === "ArrowDown") c.pitch = Math.max(0.18, c.pitch - 0.08); else if (event.key === "+" || event.key === "=") c.distance = Math.max(5, c.distance - 0.7); else if (event.key === "-") c.distance = Math.min(18, c.distance + 0.7); else return; event.preventDefault(); });
  for (const event of ["pointermove", "wheel", "keydown"]) canvas.addEventListener(event, () => redraws.get(canvas)?.());
  canvas.addEventListener("pointercancel", () => { cameras.get(canvas)!.dragging = false; });
}
export function resetPresentationCamera(canvas: HTMLCanvasElement): void { const c = cameras.get(canvas); if (c) Object.assign(c, defaultCamera()); redraws.get(canvas)?.(); }
function defaultCamera(): Camera { return { yaw: 0.78, pitch: 0.52, distance: 10.8, dragging: false, x: 0, y: 0 }; }
function drawRoute(cube: (position: Vec3, scale: Vec3, color: Vec3, yaw?: number) => void, route: Pose[]): void { for (let i = 1; i < route.length; i += 1) { const a = route[i - 1]!, b = route[i]!, dx = b.x_m - a.x_m, dz = b.y_m - a.y_m, length = Math.hypot(dx, dz); if (length > 0) cube([(a.x_m + b.x_m) / 2, 0.045, (a.y_m + b.y_m) / 2], [0.055, 0.028, length], [0.93, 0.62, 0.20], -Math.atan2(dx, dz)); } }
function drawRover(cube: (position: Vec3, scale: Vec3, color: Vec3, yaw?: number) => void, pose: Pose, collision: boolean): void { const yaw = -pose.heading_rad, color: Vec3 = collision ? [0.76, 0.18, 0.13] : [0.62, 0.70, 0.69]; cube([pose.x_m, 0.28, pose.y_m], [0.72, 0.34, 0.54], color, yaw); cube([pose.x_m, 0.51, pose.y_m], [0.46, 0.12, 0.36], [0.78, 0.82, 0.78], yaw); for (const side of [-1, 1]) cube([pose.x_m + Math.cos(pose.heading_rad + Math.PI / 2) * side * 0.34, 0.16, pose.y_m + Math.sin(pose.heading_rad + Math.PI / 2) * side * 0.34], [0.10, 0.26, 0.52], [0.035, 0.05, 0.055], yaw); cube([pose.x_m, 0.78, pose.y_m], [0.055, 0.5, 0.055], [0.72, 0.77, 0.75], yaw); cube([pose.x_m + Math.cos(pose.heading_rad) * 0.08, 1.05, pose.y_m + Math.sin(pose.heading_rad) * 0.08], [0.26, 0.13, 0.18], [0.06, 0.14, 0.17], yaw); cube([pose.x_m + Math.cos(pose.heading_rad) * 0.43, 0.42, pose.y_m + Math.sin(pose.heading_rad) * 0.43], [0.08, 0.11, 0.30], [0.94, 0.62, 0.18], yaw); }
function getRenderer(canvas: HTMLCanvasElement): Renderer | null { const known = renderers.get(canvas); if (known !== undefined) return known; const gl = canvas.getContext("webgl", { antialias: true, alpha: false }); if (!gl) { renderers.set(canvas, null); return null; } const program = gl.createProgram(), vs = shader(gl, gl.VERTEX_SHADER, vertexShader), fs = shader(gl, gl.FRAGMENT_SHADER, fragmentShader); if (!program || !vs || !fs) return null; gl.attachShader(program, vs); gl.attachShader(program, fs); gl.linkProgram(program); if (!gl.getProgramParameter(program, gl.LINK_STATUS)) { renderers.set(canvas, null); return null; } const model = gl.getUniformLocation(program, "u_model"), viewProjection = gl.getUniformLocation(program, "u_viewProjection"), color = gl.getUniformLocation(program, "u_color"), light = gl.getUniformLocation(program, "u_light"), buffer = gl.createBuffer(); if (!model || !viewProjection || !color || !light || !buffer) { renderers.set(canvas, null); return null; } gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, cubeVertices(), gl.STATIC_DRAW); gl.enable(gl.DEPTH_TEST); gl.enable(gl.CULL_FACE); const renderer = { gl, program, position: gl.getAttribLocation(program, "a_position"), normal: gl.getAttribLocation(program, "a_normal"), model, viewProjection, color, light, buffer }; renderers.set(canvas, renderer); return renderer; }
function shader(gl: WebGLRenderingContext, type: number, source: string): WebGLShader | null { const value = gl.createShader(type); if (!value) return null; gl.shaderSource(value, source); gl.compileShader(value); return gl.getShaderParameter(value, gl.COMPILE_STATUS) ? value : null; }
function drawCube(renderer: Renderer, position: Vec3, scale: Vec3, color: Vec3, yaw: number): void { renderer.gl.uniformMatrix4fv(renderer.model, false, multiply(translate(position), multiply(rotateY(yaw), scaleMatrix(scale)))); renderer.gl.uniform3fv(renderer.color, color); renderer.gl.drawArrays(renderer.gl.TRIANGLES, 0, 36); }
function resize(canvas: HTMLCanvasElement, gl: WebGLRenderingContext): void { const dpr = Math.min(window.devicePixelRatio || 1, 2), width = Math.round(canvas.clientWidth * dpr), height = Math.round(canvas.clientHeight * dpr); if (width && height && (canvas.width !== width || canvas.height !== height)) { canvas.width = width; canvas.height = height; } }
function cubeVertices(): Float32Array { const p = [[-0.5,-0.5,0.5],[0.5,-0.5,0.5],[0.5,0.5,0.5],[-0.5,0.5,0.5],[-0.5,-0.5,-0.5],[0.5,-0.5,-0.5],[0.5,0.5,-0.5],[-0.5,0.5,-0.5]]; const faces: Array<[number,number,number,number,Vec3]> = [[0,1,2,3,[0,0,1]],[5,4,7,6,[0,0,-1]],[4,0,3,7,[-1,0,0]],[1,5,6,2,[1,0,0]],[3,2,6,7,[0,1,0]],[4,5,1,0,[0,-1,0]]]; const out: number[]=[]; for (const [a,b,c,d,n] of faces) for (const i of [a,b,c,a,c,d]) out.push(...p[i]!, ...n); return new Float32Array(out); }
function multiply(a: Float32Array, b: Float32Array): Float32Array { const out = new Float32Array(16); for(let r=0;r<4;r+=1) for(let c=0;c<4;c+=1) for(let k=0;k<4;k+=1) out[c*4+r]! += a[k*4+r]! * b[c*4+k]!; return out; }
function translate([x,y,z]: Vec3): Float32Array { return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,x,y,z,1]); } function scaleMatrix([x,y,z]: Vec3): Float32Array { return new Float32Array([x,0,0,0,0,y,0,0,0,0,z,0,0,0,0,1]); } function rotateY(a: number): Float32Array { const c=Math.cos(a),s=Math.sin(a); return new Float32Array([c,0,-s,0,0,1,0,0,s,0,c,0,0,0,0,1]); } function perspective(fov: number, aspect: number, near: number, far: number): Float32Array { const f=1/Math.tan(fov/2), nf=1/(near-far); return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]); } function lookAt(eye: Vec3, target: Vec3, up: Vec3): Float32Array { const z=normalize(subtract(eye,target)), x=normalize(cross(up,z)), y=cross(z,x); return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1]); } function subtract(a: Vec3,b: Vec3): Vec3 { return [a[0]-b[0],a[1]-b[1],a[2]-b[2]]; } function cross(a: Vec3,b: Vec3): Vec3 { return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]; } function dot(a: Vec3,b: Vec3): number { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; } function normalize(v: Vec3): Vec3 { const l=Math.hypot(...v)||1; return [v[0]/l,v[1]/l,v[2]/l]; }
