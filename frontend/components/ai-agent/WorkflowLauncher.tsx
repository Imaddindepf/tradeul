'use client';

import { memo, useState, useCallback, useRef } from 'react';
import {
    Play,
    Plus,
    ChevronRight,
    Layers,
    Search,
    FileText,
    TrendingUp,
    Users,
    BarChart3,
    Zap,
    Settings2,
    ArrowRight,
    MessageSquare
} from 'lucide-react';

interface WorkflowStep {
    id: string;
    type: string;
    label: string;
    icon: React.ReactNode;
    config?: Record<string, any>;
}

interface WorkflowTemplate {
    id: string;
    name: string;
    description: string;
    steps: WorkflowStep[];
    category: 'research' | 'analysis' | 'screening';
}

interface WorkflowLauncherProps {
    onStartChat: () => void;
    onExecuteWorkflow: (workflow: WorkflowTemplate) => void;
    isConnected: boolean;
}

const STEP_ICONS: Record<string, React.ReactNode> = {
    scanner: <BarChart3 className="w-3.5 h-3.5" />,
    screener: <Search className="w-3.5 h-3.5" />,
    sec_filings: <FileText className="w-3.5 h-3.5" />,
    insiders: <Users className="w-3.5 h-3.5" />,
    news: <Zap className="w-3.5 h-3.5" />,
    ai_research: <MessageSquare className="w-3.5 h-3.5" />,
    synthetic_sectors: <Layers className="w-3.5 h-3.5" />,
    top_movers: <TrendingUp className="w-3.5 h-3.5" />,
    display: <BarChart3 className="w-3.5 h-3.5" />,
};

const TEMPLATES: WorkflowTemplate[] = [
    {
        id: 'insider-activity',
        name: 'Insider Activity',
        description: 'Track insider transactions on active stocks',
        category: 'research',
        steps: [
            { id: '1', type: 'scanner', label: 'Scanner', icon: STEP_ICONS.scanner },
            { id: '2', type: 'screener', label: 'Filter', icon: STEP_ICONS.screener, config: { min_volume: 500000 } },
            { id: '3', type: 'insiders', label: 'Insiders', icon: STEP_ICONS.insiders },
            { id: '4', type: 'display', label: 'Results', icon: STEP_ICONS.display },
        ]
    },
    {
        id: 'sec-filings',
        name: 'SEC Filings',
        description: 'Find stocks with recent SEC filings',
        category: 'research',
        steps: [
            { id: '1', type: 'scanner', label: 'Gappers', icon: STEP_ICONS.scanner },
            { id: '2', type: 'sec_filings', label: 'SEC', icon: STEP_ICONS.sec_filings, config: { form_type: ['8-K', '4'] } },
            { id: '3', type: 'news', label: 'News', icon: STEP_ICONS.news },
            { id: '4', type: 'display', label: 'Results', icon: STEP_ICONS.display },
        ]
    },
    {
        id: 'thematic-sectors',
        name: 'Thematic Sectors',
        description: 'AI-powered thematic sector breakdown',
        category: 'analysis',
        steps: [
            { id: '1', type: 'top_movers', label: 'Top Movers', icon: STEP_ICONS.top_movers },
            { id: '2', type: 'synthetic_sectors', label: 'Sectors', icon: STEP_ICONS.synthetic_sectors },
            { id: '3', type: 'ai_research', label: 'Research', icon: STEP_ICONS.ai_research },
            { id: '4', type: 'display', label: 'Results', icon: STEP_ICONS.display },
        ]
    },
    {
        id: 'momentum-scanner',
        name: 'Momentum Scanner',
        description: 'High volume breakout candidates',
        category: 'screening',
        steps: [
            { id: '1', type: 'scanner', label: 'Scanner', icon: STEP_ICONS.scanner },
            { id: '2', type: 'screener', label: 'Volume', icon: STEP_ICONS.screener, config: { min_volume: 1000000, min_change: 5 } },
            { id: '3', type: 'news', label: 'Catalyst', icon: STEP_ICONS.news },
            { id: '4', type: 'display', label: 'Results', icon: STEP_ICONS.display },
        ]
    },
];

export const WorkflowLauncher = memo(function WorkflowLauncher({
    onStartChat,
    onExecuteWorkflow,
    isConnected
}: WorkflowLauncherProps) {
    const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowTemplate | null>(null);
    const [isExecuting, setIsExecuting] = useState(false);
    const [hoveredWorkflow, setHoveredWorkflow] = useState<string | null>(null);

    const handleExecute = useCallback(async (workflow: WorkflowTemplate) => {
        setIsExecuting(true);
        setSelectedWorkflow(workflow);

        try {
            await onExecuteWorkflow(workflow);
        } finally {
            setIsExecuting(false);
        }
    }, [onExecuteWorkflow]);

    return (
        <div className="flex flex-col h-full bg-white">
            {/* Header */}
            <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Layers className="w-4 h-4 text-blue-600" />
                        <span className="text-[13px] font-medium text-gray-800">Workflows</span>
                    </div>
                    <button
                        onClick={onStartChat}
                        className="flex items-center gap-1 px-2.5 py-1 text-[11px] text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded transition-colors"
                    >
                        <MessageSquare className="w-3 h-3" />
                        <span>Chat</span>
                        <ChevronRight className="w-3 h-3" />
                    </button>
                </div>
            </div>

            {/* Workflows List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {TEMPLATES.map((workflow) => (
                    <div
                        key={workflow.id}
                        onMouseEnter={() => setHoveredWorkflow(workflow.id)}
                        onMouseLeave={() => setHoveredWorkflow(null)}
                        className={`
              group relative p-3 rounded-lg border transition-all cursor-pointer
              ${selectedWorkflow?.id === workflow.id
                                ? 'border-blue-500 bg-blue-50/50'
                                : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                            }
            `}
                    >
                        <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                                <h3 className="text-[12px] font-medium text-gray-800 truncate">
                                    {workflow.name}
                                </h3>
                                <p className="text-[11px] text-gray-500 mt-0.5 line-clamp-1">
                                    {workflow.description}
                                </p>
                            </div>

                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleExecute(workflow);
                                }}
                                disabled={!isConnected || isExecuting}
                                className={`
                  flex-shrink-0 p-1.5 rounded transition-all
                  ${isConnected
                                        ? 'bg-blue-600 hover:bg-blue-700 text-white'
                                        : 'bg-gray-200 text-gray-400'
                                    }
                  disabled:opacity-50
                `}
                            >
                                <Play className="w-3 h-3" />
                            </button>
                        </div>

                        {/* Steps Preview */}
                        <div className="flex items-center gap-1 mt-2.5">
                            {workflow.steps.map((step, idx) => (
                                <div key={step.id} className="flex items-center">
                                    <div
                                        className={`
                      flex items-center justify-center w-6 h-6 rounded
                      ${hoveredWorkflow === workflow.id || selectedWorkflow?.id === workflow.id
                                                ? 'bg-blue-100 text-blue-600'
                                                : 'bg-gray-100 text-gray-500'
                                            }
                      transition-colors
                    `}
                                        title={step.label}
                                    >
                                        {step.icon}
                                    </div>
                                    {idx < workflow.steps.length - 1 && (
                                        <ArrowRight className={`
                      w-3 h-3 mx-0.5
                      ${hoveredWorkflow === workflow.id || selectedWorkflow?.id === workflow.id
                                                ? 'text-blue-400'
                                                : 'text-gray-300'
                                            }
                    `} />
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            {/* Create New */}
            <div className="flex-shrink-0 p-3 border-t border-gray-200">
                <button
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 text-[12px] text-gray-500 hover:text-gray-700 hover:bg-gray-50 border border-dashed border-gray-300 hover:border-gray-400 rounded-lg transition-colors"
                >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create Workflow</span>
                </button>
            </div>

            {/* Status */}
            <div className="flex-shrink-0 px-3 py-2 bg-gray-50 border-t border-gray-200">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-400'}`} />
                        <span className="text-[10px] text-gray-500">
                            {isConnected ? 'Connected' : 'Connecting...'}
                        </span>
                    </div>
                    <span className="text-[10px] text-gray-400">
                        {TEMPLATES.length} workflows
                    </span>
                </div>
            </div>
        </div>
    );
});
