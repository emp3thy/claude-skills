package crypto

import (
	"crypto/md5"
	"encoding/hex"
)

func Fingerprint(id string) string {
	sum := md5.Sum([]byte(id))
	return hex.EncodeToString(sum[:])
}
