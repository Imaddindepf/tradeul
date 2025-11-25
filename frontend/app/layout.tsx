import './globals.css';
import type { Metadata } from 'next';
import { 
  Outfit, 
  JetBrains_Mono, 
  Oxygen_Mono,
  IBM_Plex_Mono,
  Fira_Code
} from 'next/font/google';
import { ClerkProvider } from '@clerk/nextjs';
import { ClientThemeProvider } from '@/components/settings/ClientThemeProvider';

// UI Font
const outfit = Outfit({ 
  subsets: ['latin'],
  variable: '--font-outfit',
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
      <html lang="en" className={`${outfit.variable} ${jetbrainsMono.variable} ${oxygenMono.variable} ${ibmPlexMono.variable} ${firaCode.variable}`}>
        <body className="font-sans antialiased">
          <ClientThemeProvider>
          {children}
          </ClientThemeProvider>
          <div id="portal-root" />
        </body>
      </html>
    </ClerkProvider>
  );
}

