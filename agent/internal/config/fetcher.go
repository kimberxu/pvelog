package config

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type ConfigResponse struct {
	FilterPatterns []string `json:"filter_patterns"`
}

func FetchRemoteConfig(controllerURL, pskSecret string) (*ConfigResponse, error) {
	client := &http.Client{
		Timeout: 10 * time.Second,
	}

	url := fmt.Sprintf("%s/api/v1/config", controllerURL)
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", pskSecret))

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var configResp ConfigResponse
	if err := json.NewDecoder(resp.Body).Decode(&configResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &configResp, nil
}
