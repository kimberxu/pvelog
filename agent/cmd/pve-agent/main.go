package main

import (
	"context"
	"crypto/rand"
	"flag"
	"fmt"
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

func generateBatchID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func main() {
	var configPath string
	flag.StringVar(&configPath, "config", "", "path to config file")
	flag.Parse()

	cfg, err := config.LoadConfig(configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	hostname, err := os.Hostname()
	if err != nil {
		hostname = "unknown"
	}

	filter, err := collector.NewFilter(cfg.FilterPatterns)
	if err != nil {
		log.Fatalf("Failed to create filter: %v", err)
	}

	// Fetch remote config on startup
	remoteConfig, err := config.FetchRemoteConfig(cfg.ControllerURL, cfg.PSKSecret)
	if err == nil && len(remoteConfig.FilterPatterns) > 0 {
		if err := filter.UpdatePatterns(remoteConfig.FilterPatterns); err != nil {
			log.Printf("Warning: failed to update filter patterns on startup: %v", err)
		} else {
			log.Printf("Successfully loaded %d filter patterns from controller", len(remoteConfig.FilterPatterns))
		}
	} else if err != nil {
		log.Printf("Warning: failed to fetch remote config on startup, using local patterns: %v", err)
	}

	dedup := collector.NewDedup(5 * time.Minute)
	journaldCollector := collector.NewJournaldCollector(filter, dedup)
	
	// Initialize cursor from file
	cursorFile := "data/cursor.txt"
	if err := os.MkdirAll("data", 0755); err != nil {
		log.Printf("Warning: failed to create data directory: %v", err)
	}
	if data, err := os.ReadFile(cursorFile); err == nil {
		journaldCollector.SetCursor(string(data))
		log.Printf("Loaded previous cursor")
	}

	httpPusher := pusher.NewHttpPusher(cfg)
	hbSender := heartbeat.NewHeartbeatSender(cfg)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start Config Polling Loop (every 24 hours)
	go func() {
		ticker := time.NewTicker(24 * time.Hour)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				remoteConfig, err := config.FetchRemoteConfig(cfg.ControllerURL, cfg.PSKSecret)
				if err == nil && len(remoteConfig.FilterPatterns) > 0 {
					if err := filter.UpdatePatterns(remoteConfig.FilterPatterns); err != nil {
						log.Printf("Failed to update filter patterns: %v", err)
					} else {
						log.Printf("Successfully updated %d filter patterns from controller", len(remoteConfig.FilterPatterns))
					}
				} else if err != nil {
					log.Printf("Failed to fetch remote config: %v", err)
				}
			}
		}
	}()

	// Start Heartbeat Loop
	go func() {
		ticker := time.NewTicker(60 * time.Second)
		defer ticker.Stop()
		
		sendHeartbeat := func() {
			if err := hbSender.Send(); err != nil {
				log.Printf("Heartbeat failed: %v", err)
			} else {
				log.Printf("Heartbeat sent successfully")
			}
		}

		sendHeartbeat() // Initial run
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				sendHeartbeat()
			}
		}
	}()

	// Start Log Collection Loop
	go func() {
		ticker := time.NewTicker(time.Duration(cfg.CollectIntervalSec) * time.Second)
		defer ticker.Stop()
		
		collectLogs := func() {
			entries, cursor, total, filtered, err := journaldCollector.ReadLogs(ctx)
			if err != nil {
				log.Printf("Failed to read logs: %v", err)
				return
			}

			log.Printf("Read %d logs, %d filtered, %d to push", total, filtered, len(entries))

			pushSuccess := true
			if len(entries) > 0 {
				payload := pusher.LogPushPayload{
					NodeID:        cfg.NodeID,
					Hostname:      hostname,
					BatchID:       generateBatchID(),
					SinceCursor:   cursor,
					Entries:       entries,
					EntryCount:    total,
					FilteredCount: filtered,
					AgentVersion:  cfg.AgentVersion,
				}
				if err := httpPusher.PushLogs(payload); err != nil {
					log.Printf("Failed to push logs: %v (will retry next tick)", err)
					pushSuccess = false
				} else {
					log.Printf("Successfully pushed %d logs to controller", len(entries))
				}
			}

			if pushSuccess && cursor != "" {
				// Success, commit and persist cursor
				journaldCollector.CommitCursor(cursor)
				if err := os.WriteFile(cursorFile, []byte(cursor), 0644); err != nil {
					log.Printf("Failed to save cursor to file: %v", err)
				}
			}
		}

		collectLogs() // Initial run
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				collectLogs()
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
