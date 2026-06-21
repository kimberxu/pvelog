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
		minutes, _ := p["minutes"].(float64)
		if err := ValidateJournal(service, int(minutes)); err != nil {
			return ExecutionResult{}, err
		}
		since := fmt.Sprintf("-%dmin", int(minutes))
		return SafeExec(ctx, timeout, "sudo", "journalctl", "-u", service, "--since", since, "--no-pager")

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
