"use client";

import { ResearchCard } from "./ResearchCard";

/**
 * Local generative-UI registry.
 *
 * Key = the name passed to `push_ui_message(name, props)` on the backend.
 * Value = a React component that receives `props` as its props.
 *
 * When a backend tool pushes a UI message whose `name` matches a key here,
 * `LoadExternalComponent` will render the local component instead of
 * fetching JS/CSS from LangSmith CDN.
 *
 * NOTE: `ClarificationCard` (Step 0 澄清卡) is NOT registered here —— it
 * doesn't go through the push_ui_message channel because langgraph 1.2.1
 * doesn't persist pending UI writes during interrupt halt. Instead it's
 * rendered directly in ChatMessage.tsx from `toolCall.args`. See
 * docs/architecture.md §2.6 + spec.md.
 */
export const LOCAL_UI_COMPONENTS: Record<string, React.ComponentType<any>> = {
  research_card: ResearchCard,
};
