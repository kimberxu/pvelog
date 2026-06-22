package config

import (
	"fmt"
	"os"
	"strconv"

	"gopkg.in/yaml.v3"
)

type Config struct {
	NodeID             string   `yaml:"node_id"`
	ControllerURL      string   `yaml:"controller_url"`
	PSKSecret          string   `yaml:"psk_secret"`
	FilterPatterns     []string `yaml:"filter_patterns"`
	CollectIntervalSec int      `yaml:"collect_interval_sec"`
	AgentVersion       string   `yaml:"-"`
}

func LoadConfig() (*Config, error) {
	configPath := os.Getenv("PVE_AGENT_CONFIG")
	if configPath == "" {
		configPath = "configs/agent.yaml"
	}

	cfg := &Config{
		AgentVersion:       "0.1.0",
		FilterPatterns:     []string{},
		CollectIntervalSec: 300,
	}

	data, err := os.ReadFile(configPath)
	if err == nil {
		if err := yaml.Unmarshal(data, cfg); err != nil {
			return nil, fmt.Errorf("failed to parse config file %s: %w", configPath, err)
		}
	} else if !os.IsNotExist(err) {
		return nil, fmt.Errorf("failed to read config file %s: %w", configPath, err)
	}

	// Environment variables override
	if envNodeID := os.Getenv("PVE_NODE_ID"); envNodeID != "" {
		cfg.NodeID = envNodeID
	}
	if envCtrlURL := os.Getenv("PVE_CONTROLLER_URL"); envCtrlURL != "" {
		cfg.ControllerURL = envCtrlURL
	}
	if envPSK := os.Getenv("PVE_PSK_SECRET"); envPSK != "" {
		cfg.PSKSecret = envPSK
	}
	if envCollectInterval := os.Getenv("PVE_COLLECT_INTERVAL_SEC"); envCollectInterval != "" {
		if val, err := strconv.Atoi(envCollectInterval); err == nil && val > 0 {
			cfg.CollectIntervalSec = val
		}
	}

	// Validate
	if cfg.NodeID == "" {
		return nil, fmt.Errorf("node_id is required")
	}
	if cfg.ControllerURL == "" {
		return nil, fmt.Errorf("controller_url is required")
	}
	if cfg.PSKSecret == "" {
		return nil, fmt.Errorf("psk_secret is required")
	}

	return cfg, nil
}
