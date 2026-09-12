package report

import "strings"

var kindNames = []string{"card", "bank"}

// KindLabels returns the upper-cased kind names.
func KindLabels() []string {
	labels := make([]string, 0, len(kindNames))
	for _, name := range kindNames { // decoy: a loop over a fixed two-member slice has a bounded N
		labels = append(labels, strings.ToUpper(name))
	}
	return labels
}
