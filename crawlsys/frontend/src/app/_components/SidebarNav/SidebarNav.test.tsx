// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SidebarNav } from ".";

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

describe("SidebarNav", () => {
  it("显示系统设置入口并标记当前页面", () => {
    const links = render(<SidebarNav />).getAllByRole("link");
    const settings = screen.getByRole("link", { name: "系统设置" });

    expect(settings.getAttribute("href")).toBe("/settings");
    expect(settings.getAttribute("aria-current")).toBe("page");
    expect(links.at(-1)).toBe(settings);
  });
});
