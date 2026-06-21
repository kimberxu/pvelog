package collector

import (
	"crypto/sha256"
	"encoding/hex"
	"sync"
	"time"
)

type Dedup struct {
	mu    sync.RWMutex
	cache map[string]time.Time
	ttl   time.Duration
}

func NewDedup(ttl time.Duration) *Dedup {
	d := &Dedup{
		cache: make(map[string]time.Time),
		ttl:   ttl,
	}
	go d.cleanup()
	return d
}

func (d *Dedup) cleanup() {
	for {
		time.Sleep(d.ttl / 2)
		now := time.Now()
		d.mu.Lock()
		for k, v := range d.cache {
			if now.Sub(v) > d.ttl {
				delete(d.cache, k)
			}
		}
		d.mu.Unlock()
	}
}

func (d *Dedup) IsDuplicate(message string) bool {
	hash := sha256.Sum256([]byte(message))
	key := hex.EncodeToString(hash[:])
	
	d.mu.Lock()
	defer d.mu.Unlock()
	
	if _, exists := d.cache[key]; exists {
		return true
	}
	d.cache[key] = time.Now()
	return false
}
