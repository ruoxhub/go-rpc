package main

import (
	"flag"
	"fmt"
	"log"

	"github.com/mrh30000/go-rpc/pkg/client"
)

var (
	server string
	group  string
	api    string
)

func init() {
	flag.StringVar(&server, "server", "localhost:5612", "Sekiro server address")
	flag.StringVar(&group, "group", "test-group", "Target client group")
	flag.StringVar(&api, "api", "test", "API to invoke")
}

func main() {
	flag.Parse()

	// Create Sekiro invoker
	invoker := client.NewSekiroInvoker([]string{server})
	defer invoker.Destroy()

	// Create invoke request
	req := &client.InvokeRequest{
		Group:   group,
		Api:     api,
		Params:  map[string]interface{}{"key": "value"},
		Timeout: 0, // Default timeout
	}

	// Invoke
	resp, err := invoker.Invoke(req)
	if err != nil {
		log.Fatalf("Invoke failed: %v", err)
	}

	fmt.Printf("Response: code=%d, message=%s, data=%v\n", resp.Code, resp.Message, resp.Data)
}
