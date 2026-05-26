"use client";

import React, { useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  CircleCheckBigIcon,
  Loader2,
  StopCircle,
} from "lucide-react";
import type { SubAgent } from "@/app/types/types";

interface SubAgentIndicatorProps {
  subAgent: SubAgent;
  onClick: () => void;
  isExpanded?: boolean;
}

export const SubAgentIndicator = React.memo<SubAgentIndicatorProps>(
  ({ subAgent, onClick, isExpanded = true }) => {
    const statusIcon = useMemo(() => {
      // 优先看 output:有结果就视为完成(覆盖 history 载入时 status 缺失/未升级的场景)
      if (subAgent.output) {
        return (
          <CircleCheckBigIcon
            size={14}
            className="shrink-0 text-emerald-500"
          />
        );
      }
      if (subAgent.status === "error") {
        return (
          <AlertCircle
            size={14}
            className="shrink-0 text-destructive"
          />
        );
      }
      // SubAgent 类型上没有 "interrupted",但 ChatInterface.tsx:175 实际会注入该值
      if ((subAgent.status as string) === "interrupted") {
        return (
          <StopCircle
            size={14}
            className="shrink-0 text-orange-500"
          />
        );
      }
      // 其余(pending / active / 未知)都按"未完成"显示转圈
      return (
        <Loader2
          size={14}
          className="shrink-0 animate-spin text-muted-foreground"
        />
      );
    }, [subAgent.status, subAgent.output]);

    return (
      <div className="w-fit max-w-[70vw] overflow-hidden rounded-lg border-none bg-card shadow-none outline-none">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClick}
          className="flex w-full items-center justify-between gap-2 border-none px-4 py-2 text-left shadow-none outline-none transition-colors duration-200"
        >
          <div className="flex w-full items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {statusIcon}
              <span className="font-sans text-[15px] font-bold leading-[140%] tracking-[-0.6px] text-[#3F3F46]">
                {subAgent.subAgentName}
              </span>
            </div>
            {isExpanded ? (
              <ChevronUp
                size={14}
                className="shrink-0 text-[#70707B]"
              />
            ) : (
              <ChevronDown
                size={14}
                className="shrink-0 text-[#70707B]"
              />
            )}
          </div>
        </Button>
      </div>
    );
  }
);

SubAgentIndicator.displayName = "SubAgentIndicator";
