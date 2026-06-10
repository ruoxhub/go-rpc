function Logo({ size = 64, strokeColor = '#667eea' }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" style={{ width: size, height: size }}>
      <circle cx="16" cy="16" r="14" stroke={strokeColor} strokeWidth="2" fill="none" />
      <path d="M10 16L14 20L22 12" stroke={strokeColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default Logo
