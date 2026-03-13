package main

import (
	"flag"
	"fmt"
	"log"

	"github.com/sekiro-go/sekiro-go/pkg/client"
)

var (
	server   string
	group    string
	clientID string
)

func init() {
	flag.StringVar(&server, "server", "localhost:5612", "Sekiro server address")
	flag.StringVar(&group, "group", "test-group", "Client group")
	flag.StringVar(&clientID, "client-id", "test-client-1", "Client ID")
}

func main() {
	flag.Parse()

	// Create Sekiro client
	c := client.NewSekiroClient(group, clientID, "localhost", 5612)

	// Start client
	if err := c.Start(); err != nil {
		log.Fatalf("Failed to start client: %v", err)
	}

	fmt.Printf("Sekiro client started: group=%s, clientID=%s\n", group, clientID)
	fmt.Println("Press Ctrl+C to exit")

	// Keep running
	select {}
}
