import './globals.css';
import type { Metadata } from 'next';
import { Outfit, JetBrains_Mono } from 'next/font/google';
import { ClerkProvider } from '@clerk/nextjs';

const outfit = Outfit({ 
  subsets: ['latin'],
  variable: '--font-outfit',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({ 
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Tradeul — Real-Time Market Intelligence',
  description: 'Professional trading platform with real-time market data, dilution tracking, and intelligent scanning.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en" className={`${outfit.variable} ${jetbrainsMono.variable}`}>
        <body className="font-sans antialiased">
          {children}
          <div id="portal-root" />
        </body>
      </html>
    </ClerkProvider>
  );
}

