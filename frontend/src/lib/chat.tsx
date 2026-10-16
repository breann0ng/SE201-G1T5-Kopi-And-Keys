import type { AssistantRuntime } from "@assistant-ui/react";
import { createContext, useContext } from "react";

/** Gives pages and message components access to the chat runtime (set up in Layout). */
export type ChatContextValue = {
  runtime: AssistantRuntime;
  /** Clears the visible conversation and the copy saved in this browser. */
  newChat: () => void;
};

export const ChatContext = createContext<ChatContextValue | null>(null);

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used inside Layout");
  return ctx;
}
