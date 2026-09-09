package units

// Kilobytes converts a byte count to whole kilobytes, rounding down.
func Kilobytes(n int64) int64 {
	return n / 1024
}
