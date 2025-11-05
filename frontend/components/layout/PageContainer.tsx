'use client';

import { ReactNode } from 'react';

interface PageContainerProps {
  children: ReactNode;
  maxWidth?: number; // px
  paddingX?: string; // tailwind classes, e.g. 'px-4'
}

export function PageContainer({ children, maxWidth = 1440, paddingX = 'px-4 lg:px-6 xl:px-8' }: PageContainerProps) {
  return (
    <div className={`mx-auto w-full ${paddingX}`} style={{ maxWidth }}>
      {children}
    </div>
  );
}



