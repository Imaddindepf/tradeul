import { ImageResponse } from 'next/og';

// Image metadata for Apple devices
export const size = {
  width: 180,
  height: 180,
};
export const contentType = 'image/png';

// Image generation
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
          borderRadius: '32px',
        }}
      >
        <span
          style={{
            color: 'white',
            fontSize: '110px',
            fontWeight: 700,
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          T
        </span>
      </div>
    ),
    {
      ...size,
    }
  );
}


