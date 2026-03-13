// Sekiro RPC Server - Go Implementation
package main

import (
	"flag"
	"fmt"

	"github.com/sekiro-go/sekiro-go/pkg/server"
)

var (
	port     int
	host     string
	debug    bool
	localDebug bool
)

func init() {
	flag.IntVar(&port, "port", 5612, "Server port")
	flag.StringVar(&host, "host", "0.0.0.0", "Server host")
	flag.BoolVar(&debug, "debug", false, "Enable debug logging")
	flag.BoolVar(&localDebug, "local-debug", false, "Enable local debug mode")
}

func main() {
	flag.Parse()

	config := &server.Config{
		Port:       port,
		Host:       host,
		Debug:      debug,
		LocalDebug: localDebug,
	}

	srv := server.NewServer(config)

	fmt.Printf("Starting Sekiro RPC Server...\n")
	fmt.Printf("Host: %s, Port: %d\n", host, port)

	if err := srv.Start(); err != nil {
		fmt.Printf("Server error: %v\n", err)
	}
}
