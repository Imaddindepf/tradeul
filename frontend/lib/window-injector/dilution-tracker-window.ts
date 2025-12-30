/**
 * Dilution Tracker Window Injector
 * 
 * Standalone window for stock dilution analysis
 */

import { WindowConfig, getUserFontForWindow, getFontConfig } from './base';

// ============================================================================
// DILUTION TRACKER WINDOW
// ============================================================================

export interface DilutionTrackerWindowData {
  ticker?: string;
  apiBaseUrl: string;
}

export function openDilutionTrackerWindow(
  data: DilutionTrackerWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 1400,
    height = 900,
    centered = true,
  } = config;

  const left = centered ? (window.screen.width - width) / 2 : 100;
  const top = centered ? (window.screen.height - height) / 2 : 100;

  const windowFeatures = [
    `width=${width}`,
    `height=${height}`,
    `left=${left}`,
    `top=${top}`,
    'resizable=yes',
    'scrollbars=yes',
    'status=yes',
  ].join(',');

  const newWindow = window.open('about:blank', '_blank', windowFeatures);

  if (!newWindow) {
    console.error('❌ Window blocked');
    return null;
  }

  injectDilutionTrackerContent(newWindow, data, config);

  return newWindow;
}

function injectDilutionTrackerContent(
  targetWindow: Window,
  data: DilutionTrackerWindowData,
  config: WindowConfig
): void {
  const { title } = config;
  const userFont = getUserFontForWindow();
  const fontConfig = getFontConfig(userFont);

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=${fontConfig.googleFont}&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: [${fontConfig.cssFamily}]
          }
        }
      }
    }
  </script>
  
  <style>
    * {
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    
    body {
      font-family: Inter, sans-serif;
      color: #171717;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
  </style>
</head>
<body class="bg-white">
  <div id="root" class="h-screen flex flex-col">
    <div class="flex items-center justify-center h-full bg-slate-50">
      <div class="text-center">
        <div class="animate-spin rounded-full h-14 w-14 border-b-4 border-blue-600 mx-auto mb-4"></div>
        <p class="text-slate-900 font-semibold text-base">Cargando Dilution Tracker...</p>
      </div>
    </div>
  </div>

  <script>
    const CONFIG = ${JSON.stringify(data)};
    
    // Renderizar iframe con la página standalone
    const tickerParam = CONFIG.ticker ? \`?ticker=\${CONFIG.ticker}\` : '';
    const iframeSrc = \`\${CONFIG.apiBaseUrl}/standalone/dilution-tracker\${tickerParam}\`;
    
    document.getElementById('root').innerHTML = \`
      <iframe 
        src="\${iframeSrc}" 
        style="width:100%;height:100%;border:0;display:block;" 
        title="Dilution Tracker"
      ></iframe>
    \`;
    
    console.log('✅ Dilution Tracker loaded in about:blank');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Dilution Tracker injected');
}

