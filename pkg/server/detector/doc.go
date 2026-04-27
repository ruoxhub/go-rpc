// Package detector contains the legacy protocol-detection path.
//
// Deprecated: 当前服务启动路径未接入 detector；生产入口以 Gin/HTTPServer 为准。
// 保留本包仅用于历史协议实验与现有单元测试，除非明确计划恢复单端口协议探测，
// 否则不要继续扩展这里的行为并误认为其已在生产链路生效。
package detector
