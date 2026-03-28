// Sekiro RPC Server - Go Implementation
package main

import (
	"flag"
	"fmt"

	"github.com/sekiro-go/sekiro-go/pkg/server"
)

var (
	port       int
	host       string
	debug      bool
	localDebug bool
	configPath string
)

func init() {
	flag.IntVar(&port, "port", 0, "Server port")
	flag.StringVar(&host, "host", "", "Server host")
	flag.BoolVar(&debug, "debug", false, "Enable debug logging")
	flag.BoolVar(&localDebug, "local-debug", false, "Enable local debug mode")
	flag.StringVar(&configPath, "c", "config.yaml", "Path to YAML config")
}

func main() {
	flag.Parse()

	config := &server.Config{
		Port:       port,
		Host:       host,
		Debug:      debug,
		LocalDebug: localDebug,
		ConfigPath: configPath,
	}

	srv := server.NewServer(config)

	fmt.Printf("Starting Sekiro RPC Server...\n")
	fmt.Printf("Host: %s, Port: %d\n", config.Host, config.Port)

	if err := srv.Start(); err != nil {
		fmt.Printf("Server error: %v\n", err)
	}
}
