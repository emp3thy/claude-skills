package report

import "strings"

// ParseCSV splits each line of text on commas.
func ParseCSV(text string) [][]string {
	rows := make([][]string, 0)
	for _, line := range strings.Split(text, "\n") {
		rows = append(rows, strings.Split(line, ","))
	}
	return rows
}
