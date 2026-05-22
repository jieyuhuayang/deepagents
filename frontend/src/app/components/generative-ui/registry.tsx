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
 */
export const LOCAL_UI_COMPONENTS: Record<string, React.ComponentType<any>> = {
  research_card: ResearchCard,
};
