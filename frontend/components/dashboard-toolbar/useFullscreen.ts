'use client';

import { useCallback, useEffect, useState } from 'react';

/**
 * Cross-browser fullscreen handle. Tracks state via the native
 * `fullscreenchange` event and exposes a toggle that flips the document
 * element in/out of fullscreen.
 */
export function useFullscreen() {
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    const handleChange = () => {
      const fsElement =
        document.fullscreenElement ||
        // @ts-ignore — vendor prefixes for Safari
        document.webkitFullscreenElement ||
        // @ts-ignore
        document.mozFullScreenElement ||
        // @ts-ignore
        document.msFullscreenElement ||
        null;
      setIsFullscreen(Boolean(fsElement));
    };

    handleChange();
    document.addEventListener('fullscreenchange', handleChange);
    document.addEventListener('webkitfullscreenchange', handleChange);
    document.addEventListener('mozfullscreenchange', handleChange);
    document.addEventListener('MSFullscreenChange', handleChange);

    return () => {
      document.removeEventListener('fullscreenchange', handleChange);
      document.removeEventListener('webkitfullscreenchange', handleChange);
      document.removeEventListener('mozfullscreenchange', handleChange);
      document.removeEventListener('MSFullscreenChange', handleChange);
    };
  }, []);

  const enter = useCallback(async () => {
    if (typeof document === 'undefined') return;
    const el: any = document.documentElement;
    try {
      if (el.requestFullscreen) await el.requestFullscreen();
      else if (el.webkitRequestFullscreen) await el.webkitRequestFullscreen();
      else if (el.mozRequestFullScreen) await el.mozRequestFullScreen();
      else if (el.msRequestFullscreen) await el.msRequestFullscreen();
    } catch (err) {
      console.warn('[useFullscreen] requestFullscreen rejected', err);
    }
  }, []);

  const exit = useCallback(async () => {
    if (typeof document === 'undefined') return;
    const doc: any = document;
    try {
      if (doc.exitFullscreen) await doc.exitFullscreen();
      else if (doc.webkitExitFullscreen) await doc.webkitExitFullscreen();
      else if (doc.mozCancelFullScreen) await doc.mozCancelFullScreen();
      else if (doc.msExitFullscreen) await doc.msExitFullscreen();
    } catch (err) {
      console.warn('[useFullscreen] exitFullscreen rejected', err);
    }
  }, []);

  const toggle = useCallback(() => {
    if (isFullscreen) {
      exit();
    } else {
      enter();
    }
  }, [isFullscreen, enter, exit]);

  return { isFullscreen, enter, exit, toggle };
}
