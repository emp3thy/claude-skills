package report

import "encoding/json"

// ParseJSON decodes text as JSON into a generic map.
func ParseJSON(text string) (map[string]any, error) {
	var out map[string]any
	err := json.Unmarshal([]byte(text), &out)
	return out, err
}
