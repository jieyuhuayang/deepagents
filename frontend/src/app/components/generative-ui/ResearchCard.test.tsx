/**
 * ResearchCard 渲染测试 —— SDD 三层测试的前端 Test-Alongside 种子。
 *
 * ResearchCard 注册到 LOCAL_UI_COMPONENTS,走 generative-ui 通道
 * (后端 emit_research_card → push_ui_message)。它是 vendored patch
 * 最易回归的本地组件之一,故有独立组件测试守护。
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResearchCard } from "./ResearchCard";

describe("ResearchCard", () => {
  it("renders title, summary and source links", () => {
    render(
      <ResearchCard
        title="调研标题"
        summary="一段摘要"
        sources={["https://a.com", "https://b.com"]}
      />,
    );
    expect(screen.getByRole("heading", { name: "调研标题" })).toBeInTheDocument();
    expect(screen.getByText("一段摘要")).toBeInTheDocument();

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "https://a.com");
  });

  it("hides 来源 section when sources is empty", () => {
    render(<ResearchCard title="t" summary="s" sources={[]} />);
    expect(screen.queryByText("来源")).not.toBeInTheDocument();
  });
});
