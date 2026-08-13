package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type safeBuffer struct {
	mu sync.Mutex
	b  bytes.Buffer
}

func (b *safeBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.b.Write(p)
}

func (b *safeBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.b.String()
}

func runAdapter(ctx context.Context, root, name string, command ...string) error {
	if len(command) == 0 {
		return fmt.Errorf("adapter %s: empty command", name)
	}
	cmd := exec.CommandContext(ctx, command[0], command[1:]...)
	cmd.Dir = root
	configureProcess(cmd)
	cmd.Cancel = func() error { return terminateProcess(cmd) }
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	if err == nil {
		return nil
	}
	if ctx.Err() != nil {
		return fmt.Errorf("adapter %s: %w; stdout=%q; stderr=%q", name, ctx.Err(), stdout.String(), stderr.String())
	}
	code := "unknown"
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		code = strconv.Itoa(exitErr.ExitCode())
	}
	return fmt.Errorf("adapter %s failed with exit code %s: %v; stdout=%q; stderr=%q", name, code, err, stdout.String(), stderr.String())
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	root, err := repositoryRoot()
	if err != nil {
		return err
	}
	port, release, err := reservePort()
	if err != nil {
		return err
	}
	release()
	server, logBuffer, err := startServer(root, port)
	if err != nil {
		return err
	}
	defer func() {
		_ = terminateProcess(server)
		_ = server.Wait()
	}()
	baseURL := "http://127.0.0.1:" + strconv.Itoa(port)
	if err := waitHealth(baseURL, 20*time.Second); err != nil {
		return fmt.Errorf("server health: %w; server log=%s", err, logBuffer.String())
	}

	adapters := []struct {
		name string
		cmd  []string
	}{
		{"Go", []string{"go", "run", "./conformance/adapters/go"}},
		{"TypeScript/Web", []string{"node", "./conformance/adapters/typescript.mjs"}},
		{"Python", []string{pythonCommand(), "conformance/adapters/python.py"}},
	}
	buildCtx, buildCancel := context.WithTimeout(context.Background(), 60*time.Second)
	if err := runAdapter(buildCtx, root, "typescript-build", npmCommand(), "--prefix", "sdk/typescript", "run", "build"); err != nil {
		buildCancel()
		return withServerLog(err, logBuffer)
	}
	buildCancel()
	for _, adapter := range adapters {
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		env := append(os.Environ(), "RPC_TEST_BASE_URL="+baseURL)
		if adapter.name == "Python" {
			env = append(env, "PYTHONDONTWRITEBYTECODE=1")
		}
		if err := runWithEnv(ctx, root, adapter.name, env, adapter.cmd...); err != nil {
			cancel()
			return withServerLog(err, logBuffer)
		}
		cancel()
		fmt.Printf("PASS %s\n", adapter.name)
	}
	if err := runJava(root, baseURL); err != nil {
		return withServerLog(err, logBuffer)
	}
	fmt.Println("PASS Java")
	legacyCtx, legacyCancel := context.WithTimeout(context.Background(), 60*time.Second)
	if err := runLegacy(legacyCtx, baseURL); err != nil {
		legacyCancel()
		return withServerLog(fmt.Errorf("legacy adapter: %w", err), logBuffer)
	}
	legacyCancel()
	fmt.Println("PASS legacy")
	return nil
}

func runWithEnv(ctx context.Context, root, name string, env []string, command ...string) error {
	cmd := exec.CommandContext(ctx, command[0], command[1:]...)
	cmd.Dir = root
	cmd.Env = env
	configureProcess(cmd)
	cmd.Cancel = func() error { return terminateProcess(cmd) }
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("adapter %s failed: %v; stdout=%q; stderr=%q", name, err, stdout.String(), stderr.String())
	}
	return nil
}

func startServer(root string, port int) (*exec.Cmd, *safeBuffer, error) {
	command := exec.Command("go", "run", ".")
	command.Dir = root
	command.Env = append(os.Environ(),
		"RPC_HOST=127.0.0.1", "RPC_PORT="+strconv.Itoa(port),
		"RPC_DISABLE_WEB_ADMIN=true", "RPC_DISABLE_METRICS=true",
		"RPC_DISABLE_ALERT=true", "RPC_DISABLE_DATABASE=true",
		"RPC_DISABLE_TRACE=true", "RPC_DISABLE_AUTO_MIGRATE=true",
		"RPC_CAPABILITY_NEGOTIATION=true")
	logBuffer := &safeBuffer{}
	command.Stdout, command.Stderr = logBuffer, logBuffer
	configureProcess(command)
	if err := command.Start(); err != nil {
		return nil, logBuffer, err
	}
	return command, logBuffer, nil
}

func waitHealth(baseURL string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	httpClient := &http.Client{Timeout: 2 * time.Second}
	for time.Now().Before(deadline) {
		response, err := httpClient.Get(baseURL + "/health")
		if err == nil {
			_, _ = io.Copy(io.Discard, response.Body)
			_ = response.Body.Close()
			if response.StatusCode >= 200 && response.StatusCode < 300 {
				return nil
			}
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("timed out after %s", timeout)
}

func reservePort() (int, func(), error) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, func() {}, err
	}
	port := listener.Addr().(*net.TCPAddr).Port
	return port, func() { _ = listener.Close() }, nil
}

func repositoryRoot() (string, error) {
	root, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(root, "go.mod")); err == nil {
			return root, nil
		}
		parent := filepath.Dir(root)
		if parent == root {
			return "", errors.New("repository root with go.mod not found")
		}
		root = parent
	}
}

func withServerLog(err error, logBuffer *safeBuffer) error {
	return fmt.Errorf("%w; server log=%s", err, logBuffer.String())
}

func pythonCommand() string {
	if runtime.GOOS == "windows" {
		return "python"
	}
	return "python3"
}

func npmCommand() string {
	if runtime.GOOS == "windows" {
		return "npm.cmd"
	}
	return "npm"
}

func runJava(root, baseURL string) error {
	wrapper := filepath.Join("sample", "xposed", "gradlew")
	if runtime.GOOS == "windows" {
		wrapper += ".bat"
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	env := os.Environ()
	if os.Getenv("GRADLE_USER_HOME") == "" {
		env = append(env, "GRADLE_USER_HOME="+filepath.Join(os.TempDir(), "go-rpc-stage1-gradle-home"))
	}
	projectCache, err := os.MkdirTemp("", "go-rpc-stage1-gradle-project-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(projectCache)
	return runWithEnv(ctx, root, "Java", env, wrapper, "-p", "sdk/java", "--project-cache-dir", projectCache, "test", "--rerun-tasks", "--no-daemon", "-Drpc.test.baseUrl="+baseURL)
}

func runLegacy(ctx context.Context, baseURL string) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	wsURL := strings.Replace(baseURL, "http://", "ws://", 1) + "/business/register?group=conformance-legacy&clientId=legacy-client"
	conn, _, err := websocket.DefaultDialer.DialContext(ctx, wsURL, nil)
	if err != nil {
		return err
	}
	_ = conn.SetReadDeadline(readDeadline(ctx, 100*time.Millisecond))
	_, _, readErr := conn.ReadMessage()
	_ = conn.Close()
	var timeoutErr net.Error
	if readErr == nil || !errors.As(readErr, &timeoutErr) || !timeoutErr.Timeout() {
		return errors.New("legacy connection unexpectedly received registered confirmation")
	}

	secondURL := strings.Replace(baseURL, "http://", "ws://", 1) + "/business/register?" + url.Values{"group": {"conformance-legacy"}, "clientId": {"legacy-client-2"}}.Encode()
	conn, _, err = websocket.DefaultDialer.DialContext(ctx, secondURL, nil)
	if err != nil {
		return err
	}
	defer conn.Close()
	if err := conn.WriteJSON(map[string]interface{}{"type": "bind", "group": "conformance-legacy", "clientId": "legacy-client-2", "actions": []string{"conformance.echo"}}); err != nil {
		return err
	}
	responseCh := make(chan error, 1)
	done := make(chan struct{})
	requestCtx, cancel := context.WithCancel(ctx)
	go func() {
		defer close(done)
		payload := map[string]interface{}{"group": "conformance-legacy", "action": "conformance.echo", "params": map[string]interface{}{"echo": "legacy"}}
		body, _ := json.Marshal(payload)
		request, requestErr := http.NewRequestWithContext(requestCtx, http.MethodPost, baseURL+"/business/invoke", bytes.NewReader(body))
		if requestErr != nil {
			responseCh <- requestErr
			return
		}
		request.Header.Set("Content-Type", "application/json")
		response, requestErr := (&http.Client{Timeout: 10 * time.Second}).Do(request)
		if requestErr != nil {
			responseCh <- requestErr
			return
		}
		defer response.Body.Close()
		var result map[string]interface{}
		if requestErr = json.NewDecoder(response.Body).Decode(&result); requestErr != nil {
			responseCh <- requestErr
			return
		}
		if response.StatusCode < 200 || response.StatusCode >= 300 {
			responseCh <- fmt.Errorf("legacy HTTP status %s", response.Status)
			return
		}
		if result["group"] != "conformance-legacy" || result["clientId"] != "legacy-client-2" || result["trace_id"] == nil {
			responseCh <- fmt.Errorf("legacy response metadata mismatch: %#v", result)
			return
		}
		legacyEcho := result["echo"]
		if legacyEcho == nil {
			if data, ok := result["data"].(map[string]interface{}); ok {
				legacyEcho = data["echo"]
			}
		}
		if legacyEcho != "legacy" {
			responseCh <- fmt.Errorf("legacy response data mismatch: %#v", result)
			return
		}
		responseCh <- nil
	}()
	_ = conn.SetReadDeadline(readDeadline(ctx, 10*time.Second))
	_, message, err := conn.ReadMessage()
	if err != nil {
		return err
	}
	var invoke map[string]interface{}
	if err := json.Unmarshal(message, &invoke); err != nil {
		return err
	}
	if _, forbidden := invoke["__rpc_context__"]; forbidden {
		return errors.New("legacy invoke unexpectedly included __rpc_context__")
	}
	if err := conn.WriteJSON(map[string]interface{}{"type": "invoke_response", "__sekiro_seq__": invoke["__sekiro_seq__"], "group": invoke["group"], "clientId": invoke["clientId"], "status": 0, "data": map[string]interface{}{"echo": "legacy"}}); err != nil {
		return err
	}
	select {
	case err := <-responseCh:
		cancel()
		<-done
		return err
	case <-ctx.Done():
		cancel()
		<-done
		return ctx.Err()
	}
}

func readDeadline(ctx context.Context, duration time.Duration) time.Time {
	deadline := time.Now().Add(duration)
	if contextDeadline, ok := ctx.Deadline(); ok && contextDeadline.Before(deadline) {
		return contextDeadline
	}
	return deadline
}
