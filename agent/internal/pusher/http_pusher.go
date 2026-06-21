package pusher

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"pve-aiops/agent/internal/auth"
	"pve-aiops/agent/internal/collector"
	"pve-aiops/agent/internal/config"
)

type LogPushPayload struct {
	NodeID        string               `json:"node_id"`
	Hostname      string               `json:"hostname"`
	BatchID       string               `json:"batch_id"`
	SinceCursor   string               `json:"since_cursor"`
	Entries       []collector.LogEntry `json:"entries"`
	EntryCount    int                  `json:"entry_count"`
	FilteredCount int                  `json:"filtered_count"`
	AgentVersion  string               `json:"agent_version"`
}

type HttpPusher struct {
	cfg    *config.Config
	client *http.Client
}

func NewHttpPusher(cfg *config.Config) *HttpPusher {
	return &HttpPusher{
		cfg: cfg,
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

func (p *HttpPusher) PushLogs(payload LogPushPayload) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	url := fmt.Sprintf("%s/api/v1/logs", p.cfg.ControllerURL)
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return err
	}

	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	
	// X-Signature: HMAC-SHA256(node_id + timestamp + body, PSK)
	signPayload := p.cfg.NodeID + timestamp + string(body)
	signature := auth.GenerateSignature(signPayload, p.cfg.PSKSecret)

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Node-ID", p.cfg.NodeID)
	req.Header.Set("X-Timestamp", timestamp)
	req.Header.Set("X-Signature", signature)

	resp, err := p.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("failed to push logs, status code: %d", resp.StatusCode)
	}

	return nil
}
