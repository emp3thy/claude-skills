package units

// Label returns a short unit label for display.
func Label(plural bool) string {
	if plural {
		return "KBs"
	}
	return "KB"
}
