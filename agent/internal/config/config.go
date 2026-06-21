package config

type Config struct {
	NodeID          string   `yaml:"node_id"`
	ControllerURL   string   `yaml:"controller_url"`
	PSKSecret       string   `yaml:"psk_secret"`
	FilterPatterns  []string `yaml:"filter_patterns"`
	AgentVersion    string
}

func LoadConfig() (*Config, error) {
	// Dummy load for now
	return &Config{
		NodeID:        "pve-node-01",
		ControllerURL: "http://localhost:8000",
		PSKSecret:     "YOUR_SECURE_PSK_HERE",
		FilterPatterns: []string{
			"pam_unix",
			"session opened for user",
			"CRON",
		},
		AgentVersion: "0.1.0",
	}, nil
}
