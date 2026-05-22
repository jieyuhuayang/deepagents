"use client";

import React from "react";

interface ResearchCardProps {
  title: string;
  summary: string;
  sources: string[];
}

export function ResearchCard({ title, summary, sources }: ResearchCardProps) {
  return (
    <div className="my-2 rounded-lg border border-border bg-card p-4 shadow-sm">
      <h3 className="mb-2 text-base font-semibold text-foreground">{title}</h3>
      <p className="mb-3 text-sm leading-relaxed text-muted-foreground">
        {summary}
      </p>
      {sources.length > 0 && (
        <div className="border-t border-border pt-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Sources
          </h4>
          <ul className="space-y-1">
            {sources.map((url) => (
              <li key={url}>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate text-xs text-primary underline decoration-dotted hover:decoration-solid"
                >
                  {url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
