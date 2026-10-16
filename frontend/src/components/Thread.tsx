import {
  ActionBarPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { ArrowUp, Check, Copy, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import type { AdvisorMeta } from "../lib/adapter";
import { load, save } from "../lib/storage";
import { AnswerExtras, StatusBadge } from "./AnswerExtras";
import { Logo } from "./Logo";
import { QuickReplies } from "./QuickReplies";
import { MarkdownText } from "./MarkdownText";

const STARTERS = [
  "Am I eligible for the Enhanced CPF Housing Grant?",
  "Can a Singapore PR couple buy a resale flat?",
  "How much CPF can I use for an older resale flat?",
  "What is the income ceiling for an HDB loan?",
];

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col">
      <ThreadPrimitive.Viewport className="flex flex-1 flex-col overflow-y-auto px-4">
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">
          <ThreadPrimitive.Empty>
            <Welcome />
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
          <div className="min-h-8 grow" />
        </div>
        <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mx-auto w-full max-w-3xl bg-white pb-4 dark:bg-slate-950">
          <Composer />
          <p className="mt-2 text-center text-xs text-slate-500 dark:text-slate-400">
            Kopi &amp; Keys summarises official HDB/CPF pages. It is not financial or legal advice —
            always confirm with HDB before committing.
          </p>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}

function Welcome() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 py-12 text-center">
      <div>
        <Logo className="mx-auto h-40 w-auto" />
        <h1 className="sr-only">Kopi &amp; Keys</h1>
        <p className="mt-2 max-w-md text-slate-600 dark:text-slate-400">
          Ask about HDB resale eligibility, grants, loans and lease rules. Answers cite official
          HDB and CPF pages, with the date we last checked them.
        </p>
      </div>
      <div className="grid w-full max-w-2xl gap-2 sm:grid-cols-2">
        {STARTERS.map((prompt) => (
          <ThreadPrimitive.Suggestion
            key={prompt}
            prompt={prompt}
            send
            className="rounded-xl border border-slate-200 px-4 py-3 text-left text-sm hover:border-coral-300 hover:bg-coral-50 dark:border-slate-800 dark:hover:border-coral-500/60 dark:hover:bg-slate-900"
          >
            {prompt}
          </ThreadPrimitive.Suggestion>
        ))}
      </div>
    </div>
  );
}

function Composer() {
  return (
    <ComposerPrimitive.Root className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-brand-500 dark:border-slate-700 dark:bg-slate-900">
      <ComposerPrimitive.Input
        rows={1}
        autoFocus
        placeholder="Ask about eligibility, grants, loans or lease…"
        className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-slate-400"
      />
      <ThreadPrimitive.If running={false}>
        <ComposerPrimitive.Send
          aria-label="Send"
          className="rounded-xl bg-brand-500 p-2 text-white hover:bg-brand-600 disabled:opacity-40 dark:bg-coral-500 dark:hover:bg-coral-600"
        >
          <ArrowUp size={18} />
        </ComposerPrimitive.Send>
      </ThreadPrimitive.If>
      <ThreadPrimitive.If running>
        <ComposerPrimitive.Cancel
          aria-label="Stop"
          className="rounded-xl bg-slate-700 p-2 text-white hover:bg-slate-800"
        >
          <Square size={18} />
        </ComposerPrimitive.Cancel>
      </ThreadPrimitive.If>
    </ComposerPrimitive.Root>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end py-3">
      <div className="max-w-[85%] rounded-2xl bg-brand-50 px-4 py-2.5 whitespace-pre-wrap text-slate-900 dark:bg-slate-800 dark:text-slate-100">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  const custom = useAuiState((s) => s.message.metadata.custom) as Partial<AdvisorMeta> | undefined;
  // metadata.custom is {} while the request is in flight, so check it is complete.
  const meta =
    custom?.kind === "response" || custom?.kind === "error" ? (custom as AdvisorMeta) : undefined;
  const running = useAuiState((s) => s.message.status?.type === "running");

  const tone =
    meta?.kind === "error"
      ? "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
      : meta?.response.status === "clarifying"
        ? "border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30"
        : meta?.response.status === "abstained"
          ? "border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-900"
          : "border-transparent";

  return (
    <MessagePrimitive.Root className="py-3">
      <div className={`rounded-2xl border px-4 py-3 ${tone}`}>
        {running && !meta ? (
          <p className="animate-pulse text-slate-500">Checking official sources…</p>
        ) : (
          <>
            <StatusBadge meta={meta} />
            <MessagePrimitive.Parts components={{ Text: MarkdownText }} />
            {meta?.kind === "response" && <AnswerExtras response={meta.response} />}
            {meta?.kind === "response" &&
              meta.response.status === "clarifying" &&
              meta.response.asking_for && (
                <MessagePrimitive.If last>
                  <QuickReplies field={meta.response.asking_for} />
                </MessagePrimitive.If>
              )}
          </>
        )}
      </div>
      {meta?.kind === "response" && <AssistantActions />}
    </MessagePrimitive.Root>
  );
}

function AssistantActions() {
  const id = useAuiState((s) => s.message.id);
  // Feedback is kept in this browser only for now (scaffold for the evaluation dataset).
  const [vote, setVote] = useState<"up" | "down" | null>(() => load(`kk:feedback:${id}`, null));
  const choose = (v: "up" | "down") => {
    const next = vote === v ? null : v;
    setVote(next);
    save(`kk:feedback:${id}`, next);
  };
  const btn = "rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800";
  return (
    <div className="mt-1 flex gap-1 pl-2">
      <ActionBarPrimitive.Root className="flex">
        <ActionBarPrimitive.Copy aria-label="Copy answer" className={btn}>
          <MessagePrimitive.If copied>
            <Check size={15} />
          </MessagePrimitive.If>
          <MessagePrimitive.If copied={false}>
            <Copy size={15} />
          </MessagePrimitive.If>
        </ActionBarPrimitive.Copy>
      </ActionBarPrimitive.Root>
      <button
        aria-label="Helpful"
        aria-pressed={vote === "up"}
        onClick={() => choose("up")}
        className={`${btn} ${vote === "up" ? "text-brand-600" : ""}`}
      >
        <ThumbsUp size={15} />
      </button>
      <button
        aria-label="Not helpful"
        aria-pressed={vote === "down"}
        onClick={() => choose("down")}
        className={`${btn} ${vote === "down" ? "text-red-600" : ""}`}
      >
        <ThumbsDown size={15} />
      </button>
    </div>
  );
}
