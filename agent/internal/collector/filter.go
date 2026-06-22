package collector

import (
	"regexp"
	"sync"
)

type Filter struct {
	mu       sync.RWMutex
	patterns []*regexp.Regexp
}

func NewFilter(regexes []string) (*Filter, error) {
	var patterns []*regexp.Regexp
	for _, r := range regexes {
		re, err := regexp.Compile(r)
		if err != nil {
			return nil, err
		}
		patterns = append(patterns, re)
	}
	return &Filter{patterns: patterns}, nil
}

func (f *Filter) UpdatePatterns(regexes []string) error {
	var newPatterns []*regexp.Regexp
	for _, r := range regexes {
		re, err := regexp.Compile(r)
		if err != nil {
			return err
		}
		newPatterns = append(newPatterns, re)
	}

	f.mu.Lock()
	f.patterns = newPatterns
	f.mu.Unlock()
	return nil
}

func (f *Filter) ShouldIgnore(message string) bool {
	f.mu.RLock()
	defer f.mu.RUnlock()

	for _, re := range f.patterns {
		if re.MatchString(message) {
			return true
		}
	}
	return false
}
