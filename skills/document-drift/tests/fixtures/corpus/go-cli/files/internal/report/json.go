package report

import "encoding/json"

// JSON renders findings as a JSON document.
func JSON(v any) ([]byte, error) {
	return json.MarshalIndent(v, "", "  ")
}
