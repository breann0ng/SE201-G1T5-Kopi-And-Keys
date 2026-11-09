import type { BuyerProfile } from "./api";
import type { ThreadMessage, ThreadRuntime } from "@assistant-ui/react";
import { profileWarnings } from "./profileWarnings.ts";

export type ProfileChangeMeta = { kind: "profile_change" };
export type PendingProfileChange = { chatId: string; text: string };

export function profileChangeText(previous: BuyerProfile, next: BuyerProfile): string | null {
  const labels: Record<keyof BuyerProfile, string> = {
    citizenship: "household citizenship", household_type: "household type", age: "age",
    household_income: "household income", first_timer: "subsidy history", subsidy_status: "subsidy history",
  };
  const changed = [...new Set((Object.keys(labels) as (keyof BuyerProfile)[])
    .filter((key) => previous[key] !== next[key]).map((key) => labels[key]))];
  if (!changed.length) return null;
  return `Profile updated: ${changed.join(", ")}. Your next question will use the current sidebar details. Earlier answers keep their original context.` +
    (profileWarnings(next).length ? " Some selections conflict; check the highlighted profile details before asking for policy guidance." : "");
}

export function isProfileChangeMessage(message: Pick<ThreadMessage, "metadata">): boolean {
  return message.metadata?.custom?.kind === "profile_change";
}

/** Local UI notices never start inference or modify a running answer's message tree. */
export class ProfileChangeController {
  private pending: PendingProfileChange | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private ready = false;
  private thread: Pick<ThreadRuntime, "getState" | "append">;
  private currentChat: () => string;
  private showPending: (change: PendingProfileChange | null) => void;
  private delay: number;
  constructor(
    thread: Pick<ThreadRuntime, "getState" | "append">,
    currentChat: () => string,
    showPending: (change: PendingProfileChange | null) => void,
    delay = 350,
  ) { this.thread = thread; this.currentChat = currentChat; this.showPending = showPending; this.delay = delay; }
  notify(text: string) {
    this.pending = { chatId: this.currentChat(), text: text + (this.thread.getState().isRunning
      ? " The answer already in progress uses the profile from when its question was sent." : "") };
    this.ready = false;
    this.showPending(this.pending); // immediately visible; consecutive edits settle into one notice
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.ready = true; this.flush(); }, this.delay);
  }
  onThreadChange() { this.flush(); }
  private flush() {
    if (!this.pending) return;
    if (this.pending.chatId !== this.currentChat()) { this.clear(); return; }
    if (!this.ready || this.thread.getState().isRunning) return;
    const change = this.pending;
    this.clear(); // clear before append triggers synchronous subscribers
    this.thread.append({ role: "assistant", content: [{ type: "text", text: change.text }],
      metadata: { custom: { kind: "profile_change" } satisfies ProfileChangeMeta }, startRun: false });
  }
  private clear() {
    this.pending = null;
    clearTimeout(this.timer);
    this.showPending(null);
  }
  dispose() { this.clear(); }
}
