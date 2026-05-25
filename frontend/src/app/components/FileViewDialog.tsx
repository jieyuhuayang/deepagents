"use client";

import React, { useMemo, useCallback, useState, useEffect } from "react";
import { FileText, Copy, Download, Edit, Save, X, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { toast } from "sonner";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import type { FileItem } from "@/app/types/types";
import useSWRMutation from "swr/mutation";

const LANGUAGE_MAP: Record<string, string> = {
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  py: "python",
  rb: "ruby",
  go: "go",
  rs: "rust",
  java: "java",
  cpp: "cpp",
  c: "c",
  cs: "csharp",
  php: "php",
  swift: "swift",
  kt: "kotlin",
  scala: "scala",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  json: "json",
  xml: "xml",
  html: "html",
  css: "css",
  scss: "scss",
  sass: "sass",
  less: "less",
  sql: "sql",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  ini: "ini",
  dockerfile: "dockerfile",
  makefile: "makefile",
};

// 多格式产物的 MIME。未列出的扩展名走 text/plain(下载行为不变)。
// 修改/扩展时记得同步 docs/architecture.md 多格式产出小节。
const MIME_BY_EXT: Record<string, string> = {
  md: "text/markdown",
  markdown: "text/markdown",
  html: "text/html",
  htm: "text/html",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  pdf: "application/pdf",
  json: "application/json",
  txt: "text/plain",
};

function base64ToBlob(b64: string, mime: string): Blob {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export const FileViewDialog = React.memo<{
  file: FileItem | null;
  onSaveFile: (fileName: string, content: string) => Promise<void>;
  onClose: () => void;
  editDisabled: boolean;
}>(({ file, onSaveFile, onClose, editDisabled }) => {
  const [isEditingMode, setIsEditingMode] = useState(file === null);
  const [fileName, setFileName] = useState(String(file?.path || ""));
  const [fileContent, setFileContent] = useState(String(file?.content || ""));
  const fileEncoding: "utf-8" | "base64" = file?.encoding === "base64" ? "base64" : "utf-8";
  const isBinary = fileEncoding === "base64";

  const fileUpdate = useSWRMutation(
    { kind: "files-update", fileName, fileContent },
    async ({ fileName, fileContent }) => {
      if (!fileName || !fileContent) return;
      return await onSaveFile(fileName, fileContent);
    },
    {
      onSuccess: () => setIsEditingMode(false),
      onError: (error) => toast.error(`保存文件失败: ${error}`),
    }
  );

  useEffect(() => {
    setFileName(String(file?.path || ""));
    setFileContent(String(file?.content || ""));
    setIsEditingMode(file === null);
  }, [file]);

  const fileExtension = useMemo(() => {
    const fileNameStr = String(fileName || "");
    return fileNameStr.split(".").pop()?.toLowerCase() || "";
  }, [fileName]);

  const isMarkdown = useMemo(() => {
    return !isBinary && (fileExtension === "md" || fileExtension === "markdown");
  }, [isBinary, fileExtension]);

  const isHtml = useMemo(() => {
    return !isBinary && (fileExtension === "html" || fileExtension === "htm");
  }, [isBinary, fileExtension]);

  const language = useMemo(() => {
    return LANGUAGE_MAP[fileExtension] || "text";
  }, [fileExtension]);

  const binarySizeLabel = useMemo(() => {
    if (!isBinary) return "";
    // base64: 每 4 char → 3 bytes;减去 `=` padding(1 或 2 个)精确算原字节数
    const padding = fileContent.endsWith("==") ? 2 : fileContent.endsWith("=") ? 1 : 0;
    const bytes = Math.floor((fileContent.length * 3) / 4) - padding;
    return formatBytes(Math.max(bytes, 0));
  }, [isBinary, fileContent]);

  const handleCopy = useCallback(() => {
    if (isBinary) return; // 二进制 base64 复制无意义,按钮也置灰兜底
    if (fileContent) {
      navigator.clipboard.writeText(fileContent);
    }
  }, [fileContent, isBinary]);

  const handleDownload = useCallback(() => {
    if (!fileName) {
      toast.error("文件名缺失,无法下载");
      return;
    }
    // 允许 fileContent === "" 的 0-byte 合法文件下载(不再 falsy-zero 误判)
    const mime = MIME_BY_EXT[fileExtension] || (isBinary ? "application/octet-stream" : "text/plain");
    let blob: Blob;
    try {
      blob = isBinary
        ? base64ToBlob(fileContent, mime)
        : new Blob([fileContent], { type: mime });
    } catch (e) {
      toast.error(`下载失败: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [fileContent, fileName, fileExtension, isBinary]);

  const handleEdit = useCallback(() => {
    setIsEditingMode(true);
  }, []);

  const handleCancel = useCallback(() => {
    if (file === null) {
      onClose();
    } else {
      setFileName(String(file.path));
      setFileContent(String(file.content));
      setIsEditingMode(false);
    }
  }, [file, onClose]);

  const fileNameIsValid = useMemo(() => {
    return (
      fileName.trim() !== "" &&
      !fileName.includes("/") &&
      !fileName.includes(" ")
    );
  }, [fileName]);

  return (
    <Dialog
      open={true}
      onOpenChange={onClose}
    >
      <DialogContent className="flex h-[80vh] max-h-[80vh] min-w-[60vw] flex-col p-6">
        <DialogTitle className="sr-only">
          {file?.path || "新建文件"}
        </DialogTitle>
        <div className="mb-4 flex items-center justify-between border-b border-border pb-4">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="text-primary/50 h-5 w-5 shrink-0" />
            {isEditingMode && file === null ? (
              <Input
                value={fileName}
                onChange={(e) => setFileName(e.target.value)}
                placeholder="输入文件名..."
                className="text-base font-medium"
                aria-invalid={!fileNameIsValid}
              />
            ) : (
              <span className="overflow-hidden text-ellipsis whitespace-nowrap text-base font-medium text-primary">
                {file?.path}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {!isEditingMode && (
              <>
                <Button
                  onClick={handleEdit}
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                  disabled={editDisabled || isBinary}
                  title={isBinary ? "二进制文件不支持在线编辑" : undefined}
                >
                  <Edit
                    size={16}
                    className="mr-1"
                  />
                  编辑
                </Button>
                <Button
                  onClick={handleCopy}
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                  disabled={isBinary}
                  title={isBinary ? "二进制文件无法复制为文本" : undefined}
                >
                  <Copy
                    size={16}
                    className="mr-1"
                  />
                  复制
                </Button>
                <Button
                  onClick={handleDownload}
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2"
                >
                  <Download
                    size={16}
                    className="mr-1"
                  />
                  下载
                </Button>
              </>
            )}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          {isEditingMode ? (
            <Textarea
              value={fileContent}
              onChange={(e) => setFileContent(e.target.value)}
              placeholder="输入文件内容..."
              className="h-full min-h-[400px] resize-none font-mono text-sm"
            />
          ) : (
            <ScrollArea className="bg-surface h-full rounded-md">
              <div className="p-4">
                {fileContent ? (
                  isBinary ? (
                    <div className="flex flex-col items-center justify-center gap-3 p-12 text-center">
                      <FileText className="text-muted-foreground h-12 w-12" />
                      <p className="text-sm text-muted-foreground">
                        二进制文件 · {binarySizeLabel}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        预览不可用,请点击右上角「下载」打开
                      </p>
                    </div>
                  ) : isMarkdown ? (
                    <div className="rounded-md p-6">
                      <MarkdownContent content={fileContent} />
                    </div>
                  ) : isHtml ? (
                    // sandbox 不开 allow-scripts:防止报告 HTML 注入脚本执行(spec §3.1)
                    <iframe
                      title={`HTML preview: ${fileName}`}
                      srcDoc={fileContent}
                      sandbox="allow-same-origin"
                      className="h-[60vh] w-full rounded-md border border-border bg-white"
                    />
                  ) : (
                    <SyntaxHighlighter
                      language={language}
                      style={oneDark}
                      customStyle={{
                        margin: 0,
                        borderRadius: "0.5rem",
                        fontSize: "0.875rem",
                      }}
                      showLineNumbers
                      wrapLines={true}
                      lineProps={{
                        style: {
                          whiteSpace: "pre-wrap",
                        },
                      }}
                    >
                      {fileContent}
                    </SyntaxHighlighter>
                  )
                ) : (
                  <div className="flex items-center justify-center p-12">
                    <p className="text-sm text-muted-foreground">
                      文件为空
                    </p>
                  </div>
                )}
              </div>
            </ScrollArea>
          )}
        </div>
        {isEditingMode && (
          <div className="mt-4 flex justify-end gap-2 border-t border-border pt-4">
            <Button
              onClick={handleCancel}
              variant="outline"
              size="sm"
            >
              <X
                size={16}
                className="mr-1"
              />
              取消
            </Button>
            <Button
              onClick={() => fileUpdate.trigger()}
              size="sm"
              disabled={
                fileUpdate.isMutating ||
                !fileName.trim() ||
                !fileContent.trim() ||
                !fileNameIsValid
              }
            >
              {fileUpdate.isMutating ? (
                <Loader2
                  size={16}
                  className="mr-1 animate-spin"
                />
              ) : (
                <Save
                  size={16}
                  className="mr-1"
                />
              )}
              保存
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
});

FileViewDialog.displayName = "FileViewDialog";
