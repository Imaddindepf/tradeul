import './globals.css';
import type { Metadata } from 'next';
import {
  Inter,
  Instrument_Serif,
  JetBrains_Mono,
  Oxygen_Mono,
  IBM_Plex_Mono,
  Fira_Code
} from 'next/font/google';
import { ClerkProvider } from '@clerk/nextjs';
import { ClientThemeProvider } from '@/components/settings/ClientThemeProvider';
import { I18nProvider } from '@/components/providers/I18nProvider';
import { ChunkLoadErrorHandler } from '@/components/ChunkLoadErrorHandler';
import { BacktestFloatingProvider } from '@/contexts/BacktestFloatingContext';

// UI Font - Using Inter for better stability
const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

// Editorial display serif — italics for landing page headlines
const instrumentSerif = Instrument_Serif({
  weight: '400',
  style: ['normal', 'italic'],
  subsets: ['latin'],
  variable: '--font-instrument-serif',
  display: 'swap',
});

// Monospace Fonts for Trading Data (User selectable)
const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
});

const oxygenMono = Oxygen_Mono({
  weight: '400',
  subsets: ['latin'],
  variable: '--font-oxygen-mono',
  display: 'swap',
});

const ibmPlexMono = IBM_Plex_Mono({
  weight: ['400', '500', '600'],
  subsets: ['latin'],
  variable: '--font-ibm-plex-mono',
  display: 'swap',
});

const firaCode = Fira_Code({
  subsets: ['latin'],
  variable: '--font-fira-code',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Tradeul · Real-Time Market Intelligence',
  description: 'Professional trading platform with real-time market data, dilution tracking, and intelligent scanning.',
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/icon', type: 'image/png', sizes: '32x32' },
    ],
    apple: '/apple-icon',
  },
  // Prevent Google Translate from breaking React DOM
  other: {
    'google': 'notranslate',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" translate="no" suppressHydrationWarning className={`${inter.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable} ${oxygenMono.variable} ${ibmPlexMono.variable} ${firaCode.variable} notranslate`}>
      <body className="font-sans antialiased">
        <ClerkProvider>
          <ChunkLoadErrorHandler />
          <I18nProvider>
            <ClientThemeProvider>
              <BacktestFloatingProvider>
                {children}
              </BacktestFloatingProvider>
            </ClientThemeProvider>
          </I18nProvider>
        </ClerkProvider>
        <div id="portal-root" />
      </body>
    </html>
  );
}
