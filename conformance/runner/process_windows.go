//go:build windows

package main

import (
	"os/exec"
	"strconv"
)

func terminateProcess(command *exec.Cmd) error {
	if command.Process == nil {
		return nil
	}
	return exec.Command("taskkill", "/PID", strconv.Itoa(command.Process.Pid), "/T", "/F").Run()
}

func configureProcess(command *exec.Cmd) {}
