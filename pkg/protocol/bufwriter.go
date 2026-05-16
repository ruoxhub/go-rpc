package protocol

// BufWriter implements io.Writer backed by a byte slice pointer.
// Used for encoding RpcPacket to a reusable buffer without allocations.
type BufWriter struct {
	Buf *[]byte
}

func (w *BufWriter) Write(p []byte) (n int, err error) {
	*w.Buf = append(*w.Buf, p...)
	return len(p), nil
}
