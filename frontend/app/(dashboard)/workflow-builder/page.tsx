'use client'

import dynamic from 'next/dynamic'

// Dynamically import to avoid SSR issues with React Flow
const WorkflowCanvas = dynamic(
  () => import('@/components/workflow-builder/WorkflowCanvas'),
  { 
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-screen bg-zinc-950 text-white">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-white border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-zinc-400">Loading Workflow Builder...</p>
        </div>
      </div>
    )
  }
)

export default function WorkflowBuilderPage() {
  return <WorkflowCanvas />
}
