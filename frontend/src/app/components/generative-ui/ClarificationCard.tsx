"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  MessageCircleQuestion,
  Check,
  CheckCircle2,
  Plus,
} from "lucide-react";
import { useResumeInterrupt } from "@/app/hooks/useResumeInterrupt";
import { cn } from "@/lib/utils";

export interface Option {
  value: string;
  label: string;
  is_default: boolean;
}

export interface Question {
  id: string;
  question: string;
  options: Option[];
  multi_select: boolean;
}

export interface ClarificationCardProps {
  restate: string;
  questions: Question[];
  completed?: boolean;
  answers?: Record<string, string | string[]>;
}

/**
 * Gen-UI clarification card.
 *
 * Pushed via `push_ui_message("clarification_card", props)` from the backend
 * `request_clarification` tool. The tool internally calls langgraph's
 * `interrupt()` to halt the graph; this component collects user choices and
 * resumes via `useResumeInterrupt()`.
 *
 * After resume, the tool pushes a second UI message (merge=True) with
 * `completed: true` + `answers`, switching the component into ReadOnlySummary.
 *
 * Spec: docs/features/v0.4.0/001-clarification-card/spec.md
 */
export function ClarificationCard({
  restate,
  questions,
  completed,
  answers,
}: ClarificationCardProps) {
  // Read-only summary: triggered by the tool's second push_ui_message
  // (merge=True) after the user's resume payload reaches the backend.
  if (completed && answers) {
    return (
      <ReadOnlySummary
        restate={restate}
        questions={questions}
        answers={answers}
      />
    );
  }

  return <InteractiveForm restate={restate} questions={questions} />;
}

// ── Interactive state ─────────────────────────────────────────────────

function InteractiveForm({
  restate,
  questions,
}: {
  restate: string;
  questions: Question[];
}) {
  const resume = useResumeInterrupt();

  // Initialize: pre-select each question's is_default option(s).
  // During SDK streaming, tool_call.args JSON accumulates incrementally —
  // a transient render may see questions with options=undefined. Guard
  // every options access with `?? []`.
  const [selections, setSelections] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(
      (questions ?? []).map((q) => [
        q.id,
        (q.options ?? [])
          .filter((o) => o?.is_default)
          .map((o) => o.value),
      ]),
    ),
  );
  const [freeTextOpen, setFreeTextOpen] = useState<Record<string, boolean>>({});
  const [freeText, setFreeText] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);

  const toggle = (qId: string, val: string, multi: boolean) =>
    setSelections((p) => {
      const cur = p[qId] || [];
      if (multi) {
        return {
          ...p,
          [qId]: cur.includes(val)
            ? cur.filter((v) => v !== val)
            : [...cur, val],
        };
      }
      // Single-select: replace
      return { ...p, [qId]: [val] };
    });

  const collectAnswers = (): Record<string, string | string[]> => {
    const out: Record<string, string | string[]> = {};
    for (const q of questions) {
      const picked = selections[q.id] || [];
      const custom = freeTextOpen[q.id] ? (freeText[q.id] || "").trim() : "";
      if (q.multi_select) {
        // Multi-select: append free-text to the list
        const vals = [...picked, ...(custom ? [custom] : [])];
        if (vals.length) out[q.id] = vals;
      } else {
        // Single-select: free-text OVERRIDES the chip selection
        // (spec.md §6 decision 2(c))
        const v = custom || picked[0];
        if (v) out[q.id] = v;
      }
    }
    return out;
  };

  const isValid = questions.every((q) => {
    const picked = selections[q.id] || [];
    const custom = freeTextOpen[q.id] ? (freeText[q.id] || "").trim() : "";
    return picked.length > 0 || !!custom;
  });

  const handleSubmit = () => {
    if (!isValid || submitted) return;
    setSubmitted(true);
    resume(collectAnswers());
  };

  return (
    <div
      className={cn(
        "my-2 w-full rounded-lg border border-border bg-card p-4 shadow-sm",
        submitted && "pointer-events-none opacity-50",
      )}
    >
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-foreground">
        <MessageCircleQuestion
          size={16}
          className="text-blue-500 dark:text-blue-400"
        />
        <span className="text-xs font-semibold uppercase tracking-wider">
          需要补充信息
        </span>
      </div>

      {/* Restate */}
      <p className="mb-4 border-b border-border pb-3 text-sm text-muted-foreground">
        {restate}
      </p>

      {/* Questions */}
      <div className="space-y-5">
        {questions.map((q, idx) => (
          <div key={q.id}>
            <div className="mb-2 flex items-baseline gap-2">
              <span className="text-sm font-medium text-foreground">
                {idx + 1}. {q.question}
              </span>
              {q.multi_select && (
                <span className="text-xs text-muted-foreground">[多选]</span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {(q.options ?? []).map((opt) => {
                const isSelected = (selections[q.id] || []).includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => toggle(q.id, opt.value, q.multi_select)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs transition-colors",
                      isSelected
                        ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-400 dark:bg-blue-950/40 dark:text-blue-300"
                        : "border-border bg-background text-foreground hover:bg-accent",
                    )}
                  >
                    {opt.label}
                    {opt.is_default && (
                      <span className="ml-1 text-yellow-500 dark:text-yellow-400">
                        ★
                      </span>
                    )}
                  </button>
                );
              })}

              {/* "+ 其他" — click to reveal Input */}
              {!freeTextOpen[q.id] ? (
                <button
                  type="button"
                  onClick={() =>
                    setFreeTextOpen((p) => ({ ...p, [q.id]: true }))
                  }
                  className="flex items-center gap-1 rounded-full border border-dashed border-border bg-background px-3 py-1 text-xs text-muted-foreground hover:bg-accent"
                >
                  <Plus size={12} />
                  其他
                </button>
              ) : (
                <Input
                  value={freeText[q.id] || ""}
                  onChange={(e) =>
                    setFreeText((p) => ({ ...p, [q.id]: e.target.value }))
                  }
                  placeholder="手填..."
                  className="h-7 w-48 text-xs"
                  autoFocus
                />
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Submit */}
      <div className="mt-5 flex justify-end">
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={!isValid || submitted}
        >
          <Check size={14} />
          {submitted ? "提交中..." : "提交"}
        </Button>
      </div>
    </div>
  );
}

// ── Read-only summary state ───────────────────────────────────────────

function ReadOnlySummary({
  restate,
  questions,
  answers,
}: {
  restate: string;
  questions: Question[];
  answers: Record<string, string | string[]>;
}) {
  // Label lookup: if value is in options, show option.label; otherwise show
  // the value string itself (free-text fallback).
  const labelFor = (q: Question, value: string) =>
    (q.options ?? []).find((o) => o.value === value)?.label ?? value;

  return (
    <div className="my-2 w-full rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-foreground">
        <CheckCircle2
          size={16}
          className="text-green-600 dark:text-green-500"
        />
        <span className="text-xs font-semibold uppercase tracking-wider">
          已提交
        </span>
      </div>

      <p className="mb-3 border-b border-border pb-2 text-sm text-muted-foreground">
        {restate}
      </p>

      <ul className="space-y-2 text-sm">
        {questions.map((q, idx) => {
          const ans = answers[q.id];
          const labels = Array.isArray(ans)
            ? ans.map((v) => labelFor(q, v))
            : ans
              ? [labelFor(q, ans)]
              : ["(未填)"];
          return (
            <li key={q.id}>
              <div className="text-xs text-muted-foreground">
                {idx + 1}. {q.question}
              </div>
              <div className="ml-4 mt-0.5 text-foreground">
                → {labels.join("、")}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
