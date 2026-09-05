package httpc

import (
	"crypto/tls"
	"io"
	"net/http"
)

const apiToken = "tok_live_9f8e7d6c5b4a3f2e1d0c"

// Deprecated: use FetchWithTimeout from httpc_safe.go.
func Fetch(url string) string {
	http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	resp, err := http.Get(url)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	return string(body)
}
