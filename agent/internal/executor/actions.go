package executor

import (
	"context"
	"encoding/json"
	"fmt"
	"time"
)

func ExecuteAction(ctx context.Context, action string, params json.RawMessage) (ExecutionResult, error) {
	var p map[string]interface{}
	if err := json.Unmarshal(params, &p); err != nil {
		return ExecutionResult{}, err
	}

	timeout := 30 * time.Second

	switch action {
	case "diagnose_ping":
		targetIP, _ := p["target_ip"].(string)
		if err := ValidatePing(targetIP); err != nil {
			return ExecutionResult{}, err
		}
		return SafeExec(ctx, timeout, "ping", "-c", "4", targetIP)

	case "diagnose_smart":
		device, _ := p["device"].(string)
		if err := ValidateSmart(device); err != nil {
			return ExecutionResult{}, err
		}
		return SafeExec(ctx, timeout, "sudo", "smartctl", "-H", fmt.Sprintf("/dev/%s", device))

	case "get_detailed_journal":
		service, _ := p["service"].(string)
		since, _ := p["since"].(string)
		until, _ := p["until"].(string)
		if err := ValidateJournal(service, since, until); err != nil {
			return ExecutionResult{}, err
		}
		args := []string{"journalctl", "-u", service, "--no-pager"}
		if since != "" {
			args = append(args, "--since", since)
		}
		if until != "" {
			args = append(args, "--until", until)
		}
		return SafeExec(ctx, timeout, "sudo", args...)

	case "check_service_status":
		service, _ := p["service"].(string)
		if err := ValidateServiceStatus(service); err != nil {
			return ExecutionResult{}, err
		}
		return SafeExec(ctx, timeout, "systemctl", "status", service, "--no-pager")

	default:
		return ExecutionResult{}, fmt.Errorf("unknown action: %s", action)
	}
}
