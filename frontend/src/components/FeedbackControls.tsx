import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useId, useState } from "react";
import { postFeedback, type ChatResponse, type FeedbackReason } from "../lib/api";
import { load, save } from "../lib/storage";

const COMMENT_MAX = 500;

const REASONS: { value: FeedbackReason; label: string }[] = [
  { value: "wrong_numbers", label: "Wrong numbers" },
  { value: "wrong_policy_info", label: "Wrong policy info" },
  { value: "outdated", label: "Outdated" },
  { value: "misunderstood_question", label: "Misunderstood my question" },
  { value: "missing_info", label: "Missing information" },
  { value: "wrong_suggestions", label: "Wrong suggestions" },
  { value: "other", label: "Other" },
];

type Rating = 1 | -1;
type Status = "idle" | "sending" | "sent" | "failed";

/**
 * Thumbs up/down under an answer, recorded for the team to review (docs/feedback-loop.md).
 * Feedback never changes answers. Failures show a quiet note and never block the chat.
 * Renders thumbs inline, then the details panel on its own line (parent row uses flex-wrap).
 */
export function FeedbackControls({ response }: { response: ChatResponse }) {
  const messageId = response.message_id;
  const storageKey = `kk:feedback:${messageId}`;
  // Remembered in this browser only so the chosen thumb stays highlighted after a reload.
  const [rating, setRating] = useState<Rating | null>(() =>
    messageId ? load<Rating | null>(storageKey, null) : null,
  );
  const [panelOpen, setPanelOpen] = useState(false);
  const [reason, setReason] = useState<FeedbackReason | null>(null);
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const ids = useId();

  // Older saved chats have no message_id, so there is nothing to attach feedback to.
  if (!messageId) return null;

  const send = async (next: Rating, details: { reason: FeedbackReason | null; comment: string | null }) => {
    setStatus("sending");
    try {
      await postFeedback({
        message_id: messageId,
        langsmith_run_id: response.langsmith_run_id ?? null,
        rating: next,
        reason: details.reason,
        comment: details.comment,
      });
      setStatus("sent");
    } catch {
      setStatus("failed");
    }
  };

  const choose = (next: Rating) => {
    if (next === 1) {
      setPanelOpen(false);
      if (rating === 1) return; // already recorded
      setReason(null);
      setComment("");
    } else {
      setPanelOpen(true);
      if (rating === -1) return; // reopen the details panel without re-sending
    }
    setRating(next);
    save(storageKey, next);
    void send(next, { reason: null, comment: null });
  };

  const sendDetails = () => {
    const trimmed = comment.trim();
    void send(-1, { reason, comment: trimmed ? trimmed : null });
    setPanelOpen(false);
  };

  const btn = "rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800";
  const chip = (selected: boolean) =>
    `rounded-full border px-3 py-1 text-xs ${
      selected
        ? "border-red-400 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-950/40 dark:text-red-200"
        : "border-slate-300 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"
    }`;

  return (
    <>
      <button
        type="button"
        aria-label="Helpful"
        aria-pressed={rating === 1}
        title="Helpful"
        onClick={() => choose(1)}
        className={`${btn} ${rating === 1 ? "text-brand-600 dark:text-brand-200" : ""}`}
      >
        <ThumbsUp size={15} fill={rating === 1 ? "currentColor" : "none"} />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        aria-pressed={rating === -1}
        aria-expanded={panelOpen}
        aria-controls={`${ids}-panel`}
        title="Not helpful"
        onClick={() => choose(-1)}
        className={`${btn} ${rating === -1 ? "text-red-600" : ""}`}
      >
        <ThumbsDown size={15} fill={rating === -1 ? "currentColor" : "none"} />
      </button>
      <span role="status" aria-live="polite" className="self-center text-xs text-slate-500">
        {status === "sent" && !panelOpen ? "Thanks, your feedback was recorded." : ""}
        {status === "failed" ? "Feedback couldn't be recorded. You can try again later." : ""}
      </span>

      {panelOpen && (
        <div
          id={`${ids}-panel`}
          className="mt-1 basis-full rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-700"
        >
          <p id={`${ids}-reasons`} className="font-medium">
            What went wrong? <span className="font-normal text-slate-500">(optional)</span>
          </p>
          <div role="group" aria-labelledby={`${ids}-reasons`} className="mt-2 flex flex-wrap gap-1.5">
            {REASONS.map((r) => (
              <button
                key={r.value}
                type="button"
                aria-pressed={reason === r.value}
                onClick={() => setReason(reason === r.value ? null : r.value)}
                className={chip(reason === r.value)}
              >
                {r.label}
              </button>
            ))}
          </div>
          <label htmlFor={`${ids}-comment`} className="mt-3 block font-medium">
            Anything else? <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <textarea
            id={`${ids}-comment`}
            value={comment}
            maxLength={COMMENT_MAX}
            rows={2}
            onChange={(e) => setComment(e.target.value.slice(0, COMMENT_MAX))}
            aria-describedby={`${ids}-note ${ids}-count`}
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900"
          />
          <div className="mt-1 flex flex-wrap justify-between gap-2 text-xs text-slate-500">
            <span id={`${ids}-note`}>Please don't include personal details like your NRIC or exact income.</span>
            <span id={`${ids}-count`}>
              {comment.length}/{COMMENT_MAX}
            </span>
          </div>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={sendDetails}
              disabled={status === "sending"}
              className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600 disabled:opacity-60"
            >
              Send
            </button>
            <button
              type="button"
              onClick={() => setPanelOpen(false)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs dark:border-slate-700"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </>
  );
}
