package heartbeat

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"

	"pve-aiops/agent/internal/auth"
	"pve-aiops/agent/internal/config"
)

type HeartbeatPayload struct {
	NodeID             string             `json:"node_id"`
	Hostname           string             `json:"hostname"`
	UptimeSeconds      int                `json:"uptime_seconds"`
	AgentVersion       string             `json:"agent_version"`
	AgentUrl           string             `json:"agent_url"`
	CpuUsagePercent    float64            `json:"cpu_usage_percent"`
	MemoryUsagePercent float64            `json:"memory_usage_percent"`
	DiskUsage          map[string]float64 `json:"disk_usage"`
}

type HeartbeatSender struct {
	cfg    *config.Config
	client *http.Client
}

func NewHeartbeatSender(cfg *config.Config) *HeartbeatSender {
	return &HeartbeatSender{
		cfg: cfg,
		client: &http.Client{
			Timeout: 5 * time.Second,
		},
	}
}

func (s *HeartbeatSender) Send() error {
	hostname, err := os.Hostname()
	if err != nil {
		hostname = "unknown"
	}

	_, port, err := net.SplitHostPort(s.cfg.AgentListenAddr)
	if err != nil {
		port = "38472"
	}
	agentUrl := fmt.Sprintf("http://%s:%s", hostname, port)

	payload := HeartbeatPayload{
		NodeID:             s.cfg.NodeID,
		Hostname:           hostname,
		UptimeSeconds:      3600,
		AgentVersion:       s.cfg.AgentVersion,
		AgentUrl:           agentUrl,
		CpuUsagePercent:    10.5,
		MemoryUsagePercent: 40.2,
		DiskUsage: map[string]float64{
			"/": 60.5,
		},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	url := fmt.Sprintf("%s/api/v1/heartbeat", s.cfg.ControllerURL)
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return err
	}

	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	signPayload := s.cfg.NodeID + timestamp + string(body)
	signature := auth.GenerateSignature(signPayload, s.cfg.PSKSecret)

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Node-ID", s.cfg.NodeID)
	req.Header.Set("X-Timestamp", timestamp)
	req.Header.Set("X-Signature", signature)

	resp, err := s.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("heartbeat failed, status: %d", resp.StatusCode)
	}

	return nil
}
