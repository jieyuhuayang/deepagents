"use client";

import { useCallback, useEffect } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import {
  type Message,
  type Assistant,
  type Checkpoint,
} from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import type { UseStreamThread } from "@langchain/langgraph-sdk/react";
import type { TodoItem } from "@/app/types/types";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState } from "nuqs";

// deepagents 后端 state.files 实际是 dict[str, FileData],FileData =
// {content, encoding, created_at?, modified_at?}。string 形态保留是为了向后
// 兼容旧 thread checkpoint(未迁移到 FileData 之前的纯字符串)。归一化在
// TasksFilesSidebar.tsx 的 FilesPopover 里做。
export type RawFileEntry =
  | string
  | { content: string | string[]; encoding?: "utf-8" | "base64" };

export type StateType = {
  messages: Message[];
  todos: TodoItem[];
  files: Record<string, RawFileEntry>;
  email?: {
    id?: string;
    subject?: string;
    page_content?: string;
  };
  ui?: any;
};

export function useChat({
  activeAssistant,
  onHistoryRevalidate,
  thread,
}: {
  activeAssistant: Assistant | null;
  onHistoryRevalidate?: () => void;
  thread?: UseStreamThread<StateType>;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const client = useClient();

  // langgraph-cli[inmem]'s OpenAPI schema rejects stream_mode "tools",
  // but newer @langchain/langgraph-sdk silently appends it once any
  // internal getter touches toolProgress. We can't disable that from the
  // outside, so strip it on the wire.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const orig = window.fetch;
    window.fetch = function patched(...args) {
      try {
        const [url, init] = args as [RequestInfo | URL, RequestInit | undefined];
        const urlStr = typeof url === "string" ? url : url.toString();
        if (urlStr.includes("/runs/stream") && init?.body && typeof init.body === "string") {
          const body = JSON.parse(init.body);
          if (Array.isArray(body.stream_mode)) {
            const filtered = body.stream_mode.filter((m: string) => m !== "tools");
            if (filtered.length !== body.stream_mode.length) {
              body.stream_mode = filtered;
              init.body = JSON.stringify(body);
            }
          }
        }
      } catch {
        /* leave request untouched on parse failure */
      }
      return orig.apply(this, args);
    };
    return () => {
      window.fetch = orig;
    };
  }, []);

  // SDK 的公开 UseStreamOptions 签名漏掉了 streamMode (只在内部 AnyStreamOptions
  // 暴露),所以传 streamMode + assistantId 时两个 overload 都不匹配,但运行时接受。
  // SDK 修齐签名后这个 @ts-expect-error 自己会报错提示清理。详见 §3.3。
  // @ts-expect-error - streamMode missing from public UseStreamOptions
  const stream = useStream<StateType>({
    assistantId: activeAssistant?.assistant_id || "",
    client: client ?? undefined,
    reconnectOnMount: true,
    threadId: threadId ?? null,
    onThreadId: setThreadId,
    defaultHeaders: { "x-auth-scheme": "langsmith" },
    // Enable fetching state history when switching to existing threads
    fetchStateHistory: true,
    // langgraph-cli[inmem] OpenAPI schema rejects the "tools" stream_mode
    // that newer @langchain/langgraph-sdk auto-adds when toolProgress is
    // observed. Pin to the modes both ends agree on.
    streamMode: ["values", "messages-tuple", "updates"],
    // Revalidate thread list when stream finishes, errors, or creates new thread
    onFinish: onHistoryRevalidate,
    onError: onHistoryRevalidate,
    onCreated: onHistoryRevalidate,
    experimental_thread: thread,
  });

  const sendMessage = useCallback(
    (content: string) => {
      const newMessage: Message = { id: uuidv4(), type: "human", content };
      stream.submit(
        { messages: [newMessage] },
        {
          optimisticValues: (prev) => ({
            messages: [...(prev.messages ?? []), newMessage],
          }),
          config: { ...(activeAssistant?.config ?? {}), recursion_limit: 100 },
        }
      );
      // Update thread list immediately when sending a message
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const runSingleStep = useCallback(
    (
      messages: Message[],
      checkpoint?: Checkpoint,
      isRerunningSubagent?: boolean,
      optimisticMessages?: Message[]
    ) => {
      if (checkpoint) {
        stream.submit(undefined, {
          ...(optimisticMessages
            ? { optimisticValues: { messages: optimisticMessages } }
            : {}),
          config: activeAssistant?.config,
          checkpoint: checkpoint,
          ...(isRerunningSubagent
            ? { interruptAfter: ["tools"] }
            : { interruptBefore: ["tools"] }),
        });
      } else {
        stream.submit(
          { messages },
          { config: activeAssistant?.config, interruptBefore: ["tools"] }
        );
      }
    },
    [stream, activeAssistant?.config]
  );

  const setFiles = useCallback(
    async (files: Record<string, RawFileEntry>) => {
      if (!threadId) return;
      // TODO: missing a way how to revalidate the internal state
      // I think we do want to have the ability to externally manage the state
      await client.threads.updateState(threadId, { values: { files } });
    },
    [client, threadId]
  );

  const continueStream = useCallback(
    (hasTaskToolCall?: boolean) => {
      stream.submit(undefined, {
        config: {
          ...(activeAssistant?.config || {}),
          recursion_limit: 100,
        },
        ...(hasTaskToolCall
          ? { interruptAfter: ["tools"] }
          : { interruptBefore: ["tools"] }),
      });
      // Update thread list when continuing stream
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const markCurrentThreadAsResolved = useCallback(() => {
    stream.submit(null, { command: { goto: "__end__", update: null } });
    // Update thread list when marking thread as resolved
    onHistoryRevalidate?.();
  }, [stream, onHistoryRevalidate]);

  // Stale-interrupt guard: before sending a resume, fetch the latest
  // server-side head and compare its interrupt id with the one the UI
  // is currently displaying. If they diverge, the UI is stale (most
  // commonly because another tab/reconnect advanced the thread) and
  // sending `resume` here would silently fork from the old checkpoint —
  // skip the submit and refresh local state instead.
  const resumeInterrupt = useCallback(
    async (value: any) => {
      if (!threadId) return;
      try {
        const serverState = await client.threads.getState(threadId);
        const serverInterruptId = (serverState.tasks ?? [])
          .flatMap((t) => t.interrupts ?? [])[0]?.id;
        const uiInterruptId = stream.interrupt?.id;
        if (
          serverInterruptId &&
          uiInterruptId &&
          serverInterruptId !== uiInterruptId
        ) {
          console.warn(
            "[resumeInterrupt] stale UI interrupt; refreshing instead of forking",
            { ui: uiInterruptId, server: serverInterruptId },
          );
          onHistoryRevalidate?.();
          return;
        }
      } catch (e) {
        // If the head check itself fails, fall through to the original
        // submit — better to risk a fork than block the user entirely.
        console.warn("[resumeInterrupt] head check failed; submitting anyway", e);
      }
      stream.submit(null, { command: { resume: value } });
      onHistoryRevalidate?.();
    },
    [stream, threadId, client, onHistoryRevalidate]
  );

  const stopStream = useCallback(() => {
    stream.stop();
  }, [stream]);

  return {
    stream,
    todos: stream.values.todos ?? [],
    files: stream.values.files ?? {},
    email: stream.values.email,
    ui: stream.values.ui,
    setFiles,
    messages: stream.messages,
    isLoading: stream.isLoading,
    isThreadLoading: stream.isThreadLoading,
    interrupt: stream.interrupt,
    getMessagesMetadata: stream.getMessagesMetadata,
    sendMessage,
    runSingleStep,
    continueStream,
    stopStream,
    markCurrentThreadAsResolved,
    resumeInterrupt,
  };
}
