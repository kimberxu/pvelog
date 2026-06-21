package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"pve-aiops/agent/internal/collector"
	"pve-aiops/agent/internal/config"
	"pve-aiops/agent/internal/executor"
	"pve-aiops/agent/internal/heartbeat"
	"pve-aiops/agent/internal/pusher"
)

func main() {
	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	filter, err := collector.NewFilter(cfg.FilterPatterns)
	if err != nil {
		log.Fatalf("Failed to create filter: %v", err)
	}

	dedup := collector.NewDedup(5 * time.Minute)
	journaldCollector := collector.NewJournaldCollector(filter, dedup)
	httpPusher := pusher.NewHttpPusher(cfg)
	hbSender := heartbeat.NewHeartbeatSender(cfg)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start Heartbeat Loop
	go func() {
		ticker := time.NewTicker(60 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := hbSender.Send(); err != nil {
					log.Printf("Heartbeat failed: %v", err)
				}
			}
		}
	}()

	// Start Log Collection Loop
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				entries, cursor, total, filtered, err := journaldCollector.ReadLogs(ctx)
				if err != nil {
					log.Printf("Failed to read logs: %v", err)
					continue
				}

				if len(entries) > 0 {
					payload := pusher.LogPushPayload{
						NodeID:        cfg.NodeID,
						Hostname:      "localhost", // dynamically fetched in production
						BatchID:       "dummy-batch", // uuid
						SinceCursor:   cursor,
						Entries:       entries,
						EntryCount:    total,
						FilteredCount: filtered,
						AgentVersion:  cfg.AgentVersion,
					}
					if err := httpPusher.PushLogs(payload); err != nil {
						log.Printf("Failed to push logs: %v", err)
					}
				}
			}
		}
	}()

	// Start local diagnostic server
	handler := executor.NewHandler(cfg)
	mux := http.NewServeMux()
	mux.Handle("/api/v1/execute", handler)

	server := &http.Server{
		Addr:    "127.0.0.1:8080",
		Handler: mux,
	}

	go func() {
		log.Println("Starting local agent API on 127.0.0.1:8080")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Listen failed: %v", err)
		}
	}()

	// Wait for termination signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down...")
	cancel()
	server.Shutdown(context.Background())
}
