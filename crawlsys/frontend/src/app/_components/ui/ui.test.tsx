// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Switch,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "./index";

afterEach(cleanup);

describe("shadcn/ui 原子组件库测试", () => {
  describe("Button 组件", () => {
    it("正确渲染默认按钮及点击回调", () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>点击保存</Button>);
      const btn = screen.getByRole("button", { name: "点击保存" });
      expect(btn).toBeTruthy();
      fireEvent.click(btn);
      expect(handleClick).toHaveBeenCalledOnce();
    });

    it("支持各种 variant 样式与禁用状态", () => {
      render(
        <Button variant="destructive" size="sm" disabled>
          删除
        </Button>,
      );
      const btn = screen.getByRole("button", { name: "删除" });
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    });

    it("支持 asChild 将样式透传至子元素（如 Link/a）", () => {
      render(
        <Button asChild variant="gradient">
          <a href="/test">跳转链接</a>
        </Button>,
      );
      const link = screen.getByRole("link", { name: "跳转链接" });
      expect(link.tagName).toBe("A");
      expect(link.className).toContain("bg-gradient-back");
    });
  });

  describe("Badge 组件", () => {
    it("支持预设 variant 渲染", () => {
      render(
        <>
          <Badge variant="success">成功</Badge>
          <Badge variant="destructive">危险</Badge>
          <Badge variant="outline">轮廓</Badge>
        </>,
      );
      expect(screen.getByText("成功")).toBeTruthy();
      expect(screen.getByText("危险")).toBeTruthy();
      expect(screen.getByText("轮廓")).toBeTruthy();
    });
  });

  describe("Card 复合组件", () => {
    it("支持完整 Header/Title/Description/Content/Footer 组合渲染", () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>测试卡片</CardTitle>
            <CardDescription>这是卡片副标题说明</CardDescription>
          </CardHeader>
          <CardContent>主体内容区域</CardContent>
          <CardFooter>
            <Button>确定</Button>
          </CardFooter>
        </Card>,
      );
      expect(screen.getByText("测试卡片")).toBeTruthy();
      expect(screen.getByText("这是卡片副标题说明")).toBeTruthy();
      expect(screen.getByText("主体内容区域")).toBeTruthy();
      expect(screen.getByRole("button", { name: "确定" })).toBeTruthy();
    });
  });

  describe("Input, Textarea, Select, Label, Switch 表单组件", () => {
    it("Input 正确处理输入事件与禁用状态", () => {
      render(<Input aria-label="用户名" placeholder="请输入用户名" disabled />);
      const input = screen.getByLabelText("用户名");
      expect((input as HTMLInputElement).disabled).toBe(true);
    });

    it("Label 与 Input 正常结合无障碍标注", () => {
      render(
        <div>
          <Label htmlFor="account">账号</Label>
          <Input id="account" />
        </div>,
      );
      expect(screen.getByLabelText("账号")).toBeTruthy();
    });

    it("Select 渲染选项与受控变更", () => {
      const handleChange = vi.fn();
      render(
        <Select aria-label="模式选择" defaultValue="fast" onChange={handleChange}>
          <option value="fast">快速模式</option>
          <option value="deep">深度模式</option>
        </Select>,
      );
      const select = screen.getByLabelText("模式选择") as HTMLSelectElement;
      expect(select.value).toBe("fast");
      fireEvent.change(select, { target: { value: "deep" } });
      expect(handleChange).toHaveBeenCalled();
    });

    it("Switch 切换开闭状态与触发回调", () => {
      const handleChecked = vi.fn();
      render(<Switch aria-label="自动重试" checked={false} onCheckedChange={handleChecked} />);
      const checkbox = screen.getByRole("checkbox", { name: "自动重试" });
      fireEvent.click(checkbox);
      expect(handleChecked).toHaveBeenCalledWith(true);
    });
  });

  describe("Table 复合组件", () => {
    it("正确渲染语义表格结构", () => {
      render(
        <Table>
          <TableCaption>任务日志</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>编号</TableHead>
              <TableHead>状态</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>101</TableCell>
              <TableCell>运行中</TableCell>
            </TableRow>
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell colSpan={2}>汇总: 1 条</TableCell>
            </TableRow>
          </TableFooter>
        </Table>,
      );
      expect(screen.getByRole("table")).toBeTruthy();
      expect(screen.getByRole("columnheader", { name: "编号" })).toBeTruthy();
      expect(screen.getByRole("cell", { name: "101" })).toBeTruthy();
      expect(screen.getByText("汇总: 1 条")).toBeTruthy();
    });
  });

  describe("Dialog 弹窗与 Sheet 抽屉组件", () => {
    it("Dialog 打开并支持键盘 Esc 或关闭按钮触发回调", () => {
      const handleClose = vi.fn();
      render(
        <Dialog open={true} onOpenChange={handleClose}>
          <DialogContent onClose={handleClose}>
            <DialogHeader>
              <DialogTitle>新建任务</DialogTitle>
              <DialogDescription>填写新任务参数</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button onClick={handleClose}>完成</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>,
      );
      expect(screen.getByRole("dialog")).toBeTruthy();
      expect(screen.getByText("新建任务")).toBeTruthy();
      const closeBtn = screen.getByRole("button", { name: "Close" });
      fireEvent.click(closeBtn);
      expect(handleClose).toHaveBeenCalled();
    });

    it("Sheet 打开并呈现侧边抽屉语义", () => {
      const handleClose = vi.fn();
      render(
        <Sheet open={true} onOpenChange={handleClose}>
          <SheetContent side="right" showCloseButton onClose={handleClose}>
            <SheetHeader>
              <SheetTitle>模型详情</SheetTitle>
              <SheetDescription>模型物理字段详情</SheetDescription>
            </SheetHeader>
            <div>抽屉核心内容</div>
            <SheetFooter>
              <Button onClick={handleClose}>关闭</Button>
            </SheetFooter>
          </SheetContent>
        </Sheet>,
      );
      expect(screen.getByRole("dialog")).toBeTruthy();
      expect(screen.getByText("模型详情")).toBeTruthy();
      expect(screen.getByText("抽屉核心内容")).toBeTruthy();
    });
  });

  describe("Alert, Separator, Skeleton 组件", () => {
    it("Alert 渲染不同警告/成功/错误信息", () => {
      render(
        <Alert variant="destructive">
          <AlertTitle>错误提示</AlertTitle>
          <AlertDescription>无法连接远程服务</AlertDescription>
        </Alert>,
      );
      expect(screen.getByRole("alert")).toBeTruthy();
      expect(screen.getByText("错误提示")).toBeTruthy();
      expect(screen.getByText("无法连接远程服务")).toBeTruthy();
    });

    it("Separator 渲染水平与垂直分隔线", () => {
      const { container } = render(
        <>
          <Separator orientation="horizontal" />
          <Separator orientation="vertical" />
        </>,
      );
      expect(container.querySelectorAll('[role="none"]').length).toBe(2);
    });

    it("Skeleton 渲染动画占位条", () => {
      const { container } = render(<Skeleton className="h-6 w-24" />);
      expect(container.querySelector(".animate-pulse")).toBeTruthy();
    });
  });
});
