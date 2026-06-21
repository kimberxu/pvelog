package collector

import (
	"regexp"
)

type Filter struct {
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

func (f *Filter) ShouldIgnore(message string) bool {
	for _, re := range f.patterns {
		if re.MatchString(message) {
			return true
		}
	}
	return false
}
