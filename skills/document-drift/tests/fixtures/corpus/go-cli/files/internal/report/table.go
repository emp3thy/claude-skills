package report

import "strings"

// Table renders findings as an aligned text table.
func Table(rows []string) string {
	return strings.Join(rows, "; ")
}
