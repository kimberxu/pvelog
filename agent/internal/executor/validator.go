package executor

import (
	"errors"
	"regexp"
)

var (
	rxIP     = regexp.MustCompile(`^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)`)
	rxDevice = regexp.MustCompile(`^(sd[a-z]|nvme[0-9]n[0-9]|vd[a-z])$`)
)

func ValidatePing(targetIP string) error {
	if !rxIP.MatchString(targetIP) {
		return errors.New("target IP not allowed")
	}
	return nil
}

func ValidateSmart(device string) error {
	if !rxDevice.MatchString(device) {
		return errors.New("device not allowed")
	}
	return nil
}

func ValidateJournal(service string, minutes int) error {
	if minutes < 1 || minutes > 60 {
		return errors.New("minutes out of range")
	}
	return nil
}

func ValidateServiceStatus(service string) error {
	allowed := map[string]bool{
		"corosync":    true,
		"pveproxy":    true,
		"ceph-mon":    true,
		"pvedaemon":   true,
		"pve-cluster": true,
	}
	if !allowed[service] {
		return errors.New("service not allowed")
	}
	return nil
}
