/**
 * 确定性 fixture —— 一次"调研 → ResearchCard 渲染"的录制回放数据。
 *
 * 用 `page.route` 拦截 deployment URL 的请求并 fulfill 这些 canned 响应,
 * E2E 因此不依赖真后端 / 真 LLM(见 research-card.spec.ts)。
 *
 * 真实 feature 的 fixture 应通过 `npm run e2e:record`(对真后端跑一次,
 * 抓 SSE 落盘)生成;本种子是手写的最小忠实样例,字段形状对齐:
 *   - backend/server.py `_sse_event`:`event: <type>\r\ndata: <json>\r\n\r\n`
 *   - backend tools.py `emit_research_card` → push_ui_message("research_card",
 *     {title,summary,sources}, metadata={tool_call_id}) → state.ui[] 的 UIMessage
 *   - frontend ChatMessage.tsx:ui 按 metadata.tool_call_id 匹配 toolCall.id,
 *     LoadExternalComponent 按 ui.name 在 LOCAL_UI_COMPONENTS 找组件、用 ui.props 渲染
 */

const TOOL_CALL_ID = "tool-call-1";

export const CARD = {
  title: "Topic Overview",
  summary: "Key findings summary.",
  sources: ["https://example.com", "https://example2.com"],
};

const AI_MESSAGE = {
  type: "ai",
  id: "msg-ai-1",
  content: "Let me research this topic.",
  tool_calls: [
    {
      name: "emit_research_card",
      id: TOOL_CALL_ID,
      args: CARD,
    },
  ],
};

// state.ui[] 里的 UIMessage(langgraph push_ui_message 产物形状)
const UI_MESSAGE = {
  type: "ui",
  id: "ui-1",
  name: "research_card",
  metadata: { tool_call_id: TOOL_CALL_ID, message_id: "msg-ai-1" },
  props: CARD,
};

const FINAL_STATE = {
  messages: [AI_MESSAGE],
  todos: [],
  files: {},
  ui: [UI_MESSAGE],
};

function sse(event: string, data: unknown): string {
  return `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

/** 一次完整 run 的 SSE 字节流(metadata → values → end)。 */
export function researchCardStream(threadId = "test-thread-1", runId = "test-run-1"): string {
  return (
    sse("metadata", { run_id: runId, thread_id: threadId, attempt: 1 }) +
    sse("values", FINAL_STATE) +
    sse("end", { run_id: runId })
  );
}

/** mount 期/其它端点的 canned JSON。 */
export const ASSISTANT = {
  assistant_id: "research",
  graph_id: "research",
  name: "research",
  config: {},
  metadata: {},
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

export const THREAD = {
  thread_id: "test-thread-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  metadata: {},
  status: "idle",
  values: null,
};

export const EMPTY_STATE = {
  values: { messages: [], todos: [], files: {}, ui: [] },
  next: [],
  tasks: [],
  metadata: {},
  created_at: null,
  checkpoint: null,
  parent_checkpoint: null,
};
