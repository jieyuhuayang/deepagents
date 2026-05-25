"use client";

import React, {
  useMemo,
  useCallback,
  useState,
  useEffect,
  useRef,
} from "react";
import {
  FileText,
  FileType,
  Globe,
  CheckCircle,
  Circle,
  Clock,
  ChevronDown,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { TodoItem, FileItem } from "@/app/types/types";
import type { RawFileEntry } from "@/app/hooks/useChat";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { FileViewDialog } from "@/app/components/FileViewDialog";

// 把后端 state.files 里的 entry 归一为前端 FileItem。后端 v2 格式是
// {content: str, encoding: "utf-8"|"base64"};旧 thread checkpoint 可能仍是
// 纯字符串或 {content: list[str]} v1 兼容形态。保留 encoding 信息,让
// FileViewDialog 能识别二进制走下载占位 + base64 解码下载。
function normalizeFileEntry(path: string, raw: RawFileEntry): FileItem {
  if (typeof raw === "object" && raw !== null && "content" in raw) {
    const c = raw.content;
    const content = Array.isArray(c) ? c.join("\n") : String(c ?? "");
    const encoding = raw.encoding === "base64" ? "base64" : "utf-8";
    return { path, content, encoding };
  }
  return { path, content: String(raw ?? ""), encoding: "utf-8" };
}

function fileIconFor(path: string) {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "html" || ext === "htm") return Globe;
  if (ext === "docx" || ext === "doc" || ext === "pdf") return FileType;
  return FileText;
}

export function FilesPopover({
  files,
  setFiles,
  editDisabled,
}: {
  files: Record<string, RawFileEntry>;
  setFiles: (files: Record<string, RawFileEntry>) => Promise<void>;
  editDisabled: boolean;
}) {
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);

  const handleSaveFile = useCallback(
    async (fileName: string, content: string) => {
      // 用户手动编辑只走 utf-8 路径(二进制是后端工具产物,前端不该改)
      await setFiles({ ...files, [fileName]: content });
      setSelectedFile({ path: fileName, content, encoding: "utf-8" });
    },
    [files, setFiles]
  );

  return (
    <>
      {Object.keys(files).length === 0 ? (
        <div className="flex h-full items-center justify-center p-4 text-center">
          <p className="text-xs text-muted-foreground">暂无文件</p>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(256px,1fr))] gap-2">
          {Object.keys(files).map((file) => {
            const filePath = String(file);
            const fileItem = normalizeFileEntry(filePath, files[file]);
            const Icon = fileIconFor(filePath);

            return (
              <button
                key={filePath}
                type="button"
                onClick={() => setSelectedFile(fileItem)}
                className="cursor-pointer space-y-1 truncate rounded-md border border-border px-2 py-3 shadow-sm transition-colors"
                style={{
                  backgroundColor: "var(--color-file-button)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor =
                    "var(--color-file-button-hover)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor =
                    "var(--color-file-button)";
                }}
              >
                <Icon
                  size={24}
                  className="mx-auto text-muted-foreground"
                />
                <span className="mx-auto block w-full truncate break-words text-center text-sm leading-relaxed text-foreground">
                  {filePath}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {selectedFile && (
        <FileViewDialog
          file={selectedFile}
          onSaveFile={handleSaveFile}
          onClose={() => setSelectedFile(null)}
          editDisabled={editDisabled}
        />
      )}
    </>
  );
}

export const TasksFilesSidebar = React.memo<{
  todos: TodoItem[];
  files: Record<string, RawFileEntry>;
  setFiles: (files: Record<string, RawFileEntry>) => Promise<void>;
}>(({ todos, files, setFiles }) => {
  const { isLoading, interrupt } = useChatContext();
  const [tasksOpen, setTasksOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);

  // Track previous counts to detect when content goes from empty to having items
  const prevTodosCount = useRef(todos.length);
  const prevFilesCount = useRef(Object.keys(files).length);

  // Auto-expand when todos go from empty to having content
  useEffect(() => {
    if (prevTodosCount.current === 0 && todos.length > 0) {
      setTasksOpen(true);
    }
    prevTodosCount.current = todos.length;
  }, [todos.length]);

  // Auto-expand when files go from empty to having content
  const filesCount = Object.keys(files).length;
  useEffect(() => {
    if (prevFilesCount.current === 0 && filesCount > 0) {
      setFilesOpen(true);
    }
    prevFilesCount.current = filesCount;
  }, [filesCount]);

  const getStatusIcon = useCallback((status: TodoItem["status"]) => {
    switch (status) {
      case "completed":
        return (
          <CheckCircle
            size={12}
            className="text-success/80"
          />
        );
      case "in_progress":
        return (
          <Clock
            size={12}
            className="text-warning/80"
          />
        );
      default:
        return (
          <Circle
            size={10}
            className="text-tertiary/70"
          />
        );
    }
  }, []);

  const groupedTodos = useMemo(() => {
    return {
      pending: todos.filter((t) => t.status === "pending"),
      in_progress: todos.filter((t) => t.status === "in_progress"),
      completed: todos.filter((t) => t.status === "completed"),
    };
  }, [todos]);

  const groupedLabels = {
    pending: "待办",
    in_progress: "进行中",
    completed: "已完成",
  };

  return (
    <div className="min-h-0 w-full flex-1">
      <div className="font-inter flex h-full w-full flex-col p-0">
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
          <div className="flex items-center justify-between px-3 pb-1.5 pt-2">
            <span className="text-xs font-semibold tracking-wide text-zinc-600">
              AGENT 任务
            </span>
            <button
              onClick={() => setTasksOpen((v) => !v)}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-transform duration-200 hover:bg-muted",
                tasksOpen ? "rotate-180" : "rotate-0"
              )}
              aria-label="折叠/展开任务面板"
            >
              <ChevronDown size={14} />
            </button>
          </div>
          {tasksOpen && (
            <div className="bg-muted-secondary rounded-xl px-3 pb-2">
              <ScrollArea className="h-full">
                {todos.length === 0 ? (
                  <div className="flex h-full items-center justify-center p-4 text-center">
                    <p className="text-xs text-muted-foreground">
                      暂无任务
                    </p>
                  </div>
                ) : (
                  <div className="ml-1 p-0.5">
                    {Object.entries(groupedTodos).map(([status, todos]) => (
                      <div className="mb-4">
                        <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-tertiary">
                          {groupedLabels[status as keyof typeof groupedLabels]}
                        </h3>
                        {todos.map((todo, index) => (
                          <div
                            key={`${status}_${todo.id}_${index}`}
                            className="mb-1.5 flex items-start gap-2 rounded-sm p-1 text-sm"
                          >
                            {getStatusIcon(todo.status)}
                            <span className="flex-1 break-words leading-relaxed text-inherit">
                              {todo.content}
                            </span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>
          )}

          <div className="flex items-center justify-between px-3 pb-1.5 pt-2">
            <span className="text-xs font-semibold tracking-wide text-zinc-600">
              文件系统
            </span>
            <button
              onClick={() => setFilesOpen((v) => !v)}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-transform duration-200 hover:bg-muted",
                filesOpen ? "rotate-180" : "rotate-0"
              )}
              aria-label="折叠/展开文件面板"
            >
              <ChevronDown size={14} />
            </button>
          </div>
          {filesOpen && (
            <FilesPopover
              files={files}
              setFiles={setFiles}
              editDisabled={isLoading === true || interrupt !== undefined}
            />
          )}
        </div>
      </div>
    </div>
  );
});

TasksFilesSidebar.displayName = "TasksFilesSidebar";
