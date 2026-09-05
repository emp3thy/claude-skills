package httpc

import (
	"net/http"
	"time"
)

var client = &http.Client{Timeout: 5 * time.Second}

func FetchWithTimeout(url string) (int, error) {
	resp, err := client.Get(url)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	return resp.StatusCode, nil
}
