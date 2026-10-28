export interface ReplayEvent {
  sequence: number;
  simulated_time_s: number;
  phase: string;
}

export class ReplayController {
  readonly #events: readonly ReplayEvent[];
  #eventIndex = 0;
  #playing = false;

  constructor(events: readonly ReplayEvent[]) {
    if (events.length === 0) {
      throw new Error("A recorded replay requires at least one event");
    }
    this.#events = events;
  }

  currentEvent(): ReplayEvent {
    return this.#events[this.#eventIndex]!;
  }

  isPlaying(): boolean {
    return this.#playing;
  }

  play(): void {
    this.#playing = true;
  }

  pause(): void {
    this.#playing = false;
  }

  restart(): void {
    this.#eventIndex = 0;
    this.#playing = false;
  }

  scrubTo(simulatedTimeS: number): void {
    this.#selectEventAt(simulatedTimeS);
  }

  advanceTo(simulatedTimeS: number): void {
    if (this.#playing) {
      this.#selectEventAt(simulatedTimeS);
    }
  }

  #selectEventAt(simulatedTimeS: number): void {
    let selected = 0;
    for (let index = 0; index < this.#events.length; index += 1) {
      if (this.#events[index]!.simulated_time_s > simulatedTimeS) {
        break;
      }
      selected = index;
    }
    this.#eventIndex = selected;
  }
}
