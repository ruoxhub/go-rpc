package compress

// NoneCompressor implements no compression (pass-through)
type NoneCompressor struct{}

// Method returns the compression method name
func (n *NoneCompressor) Method() string {
	return "none"
}

// Compress returns input data unchanged
func (n *NoneCompressor) Compress(input []byte) ([]byte, error) {
	return input, nil
}

// Decompress returns input data unchanged
func (n *NoneCompressor) Decompress(input []byte) ([]byte, error) {
	return input, nil
}
