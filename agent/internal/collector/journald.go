package collector

import (
	"bufio"
	"context"
	"encoding/json"
	"os/exec"
	"strconv"
)

type LogEntry struct {
	Timestamp string `json:"timestamp"`
	Priority  int    `json:"priority"`
	Unit      string `json:"unit"`
	Message   string `json:"message"`
}

type JournaldCollector struct {
	cursor string
	filter *Filter
	dedup  *Dedup
}

func NewJournaldCollector(filter *Filter, dedup *Dedup) *JournaldCollector {
	return &JournaldCollector{
		filter: filter,
		dedup:  dedup,
	}
}

// ReadLogs reads from journalctl incrementally
func (c *JournaldCollector) ReadLogs(ctx context.Context) ([]LogEntry, string, int, int, error) {
	var args []string
	if c.cursor != "" {
		args = []string{"--no-pager", "-o", "json", "--after-cursor", c.cursor}
	} else {
		args = []string{"--no-pager", "-o", "json", "-n", "100"}
	}
	
	cmd := exec.CommandContext(ctx, "journalctl", args...)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, "", 0, 0, err
	}
	
	if err := cmd.Start(); err != nil {
		return nil, "", 0, 0, err
	}
	
	scanner := bufio.NewScanner(stdout)
	var entries []LogEntry
	var totalCount int
	var filteredCount int
	var lastCursor string
	
	for scanner.Scan() {
		totalCount++
		line := scanner.Bytes()
		
		var raw map[string]interface{}
		if err := json.Unmarshal(line, &raw); err != nil {
			continue
		}
		
		msg, _ := raw["MESSAGE"].(string)
		
		if cursor, ok := raw["__CURSOR"].(string); ok {
			lastCursor = cursor
		}
		
		if c.filter.ShouldIgnore(msg) {
			filteredCount++
			continue
		}
		
		if c.dedup.IsDuplicate(msg) {
			filteredCount++
			continue
		}
		
		priorityStr, _ := raw["PRIORITY"].(string)
		priority, _ := strconv.Atoi(priorityStr)
		unit, _ := raw["_SYSTEMD_UNIT"].(string)
		tsStr, _ := raw["__REALTIME_TIMESTAMP"].(string)
		
		entries = append(entries, LogEntry{
			Timestamp: tsStr,
			Priority:  priority,
			Unit:      unit,
			Message:   msg,
		})
	}
	
	cmd.Wait()
	
	// If no new cursor found, return the old one
	nextCursor := c.cursor
	if lastCursor != "" {
		nextCursor = lastCursor
	}
	
	return entries, nextCursor, totalCount, filteredCount, nil
}

// CommitCursor updates the internal cursor after a successful push
func (c *JournaldCollector) CommitCursor(cursor string) {
	c.cursor = cursor
}

// SetCursor initializes the cursor (e.g., from persisted state)
func (c *JournaldCollector) SetCursor(cursor string) {
	c.cursor = cursor
}
