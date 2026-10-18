# App 共享组件

本目录承载分析页与 crawler 管理页共同使用的 App Shell、导航和分析展示组件。

- `AppShell/`：全局桌面/移动布局与品牌入口。
- `MobileNav/`：移动端可折叠导航及其测试。
- `SidebarNav/`：桌面与移动端共用的主导航链接，包含系统设置入口。
- `NumberInput/`：crawler 与设置表单共用的文本型数值输入，提供数值键盘提示。
- `Loader2/`：crawler 与设置页异步按钮共用的旋转加载图标。
- `ConfirmDialog/`：跨管理页面复用的可访问确认对话框，可恢复焦点。
- `PageHeader/`：管理页面共享的标题、说明与操作区。
- `sections/`：由 analysis 详情页复用的结构化分析结果区块。
- 其余文件：analysis 详情页展示控件与格式化逻辑。

App Shell、导航和跨页面基础控件属于共享结构；crawler 业务组件继续放在 `crawler/_components`，analysis 私有展示不得下沉到 crawler。
