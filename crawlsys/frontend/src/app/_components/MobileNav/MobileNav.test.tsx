// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MobileNav } from ".";

let pathname = "/analysis";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    onClick,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </a>
  ),
}));

describe("MobileNav", () => {
  beforeEach(() => {
    cleanup();
    pathname = "/analysis";
  });

  it("点击导航链接后关闭菜单", () => {
    render(<MobileNav />);
    const menu = screen.getByText("菜单").closest("details") as HTMLDetailsElement;

    fireEvent.click(screen.getByText("菜单"));
    expect(menu.open).toBe(true);

    fireEvent.click(screen.getByRole("link", { name: "平台" }));
    expect(menu.open).toBe(false);
  });

  it("复用系统设置导航入口", () => {
    render(<MobileNav />);

    fireEvent.click(screen.getByText("菜单"));
    expect(
      screen.getByRole("link", { name: "系统设置" }).getAttribute("href"),
    ).toBe("/settings");
  });

  it("路由变化后关闭保留在布局中的菜单", () => {
    const view = render(<MobileNav />);
    const menu = screen.getByText("菜单").closest("details") as HTMLDetailsElement;

    fireEvent.click(screen.getByText("菜单"));
    expect(menu.open).toBe(true);

    pathname = "/crawler/platforms";
    view.rerender(<MobileNav />);
    expect(menu.open).toBe(false);
  });
});
