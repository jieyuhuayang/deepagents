"use client";

import { createContext, useContext, type ReactNode } from "react";

/**
 * `useResumeInterrupt` lets generative-ui components (e.g. ClarificationCard)
 * resume an interrupt without prop-drilling the callback through ChatInterface
 * → ChatMessage → ToolCallBox → LoadExternalComponent (which doesn't forward
 * onResume to the inner component).
 *
 * Provider lives in ChatInterface (wrapping the message list); consumer is any
 * UI component pushed via `push_ui_message` from a tool that internally calls
 * `interrupt()` (langgraph native pause inside a tool node).
 *
 * See: docs/features/v0.4.0/001-clarification-card/spec.md §6 (decision D),
 *      docs/architecture.md §3.1 patch table.
 */
const ResumeInterruptCtx = createContext<((value: unknown) => void) | null>(
  null,
);

export function ResumeInterruptProvider({
  value,
  children,
}: {
  value: (v: unknown) => void;
  children: ReactNode;
}) {
  return (
    <ResumeInterruptCtx.Provider value={value}>
      {children}
    </ResumeInterruptCtx.Provider>
  );
}

export function useResumeInterrupt() {
  const fn = useContext(ResumeInterruptCtx);
  if (!fn) {
    throw new Error(
      "useResumeInterrupt must be used within <ResumeInterruptProvider>",
    );
  }
  return fn;
}
