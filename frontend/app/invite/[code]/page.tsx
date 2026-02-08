'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth, SignInButton } from '@clerk/nextjs';
import { Loader2, Users, Check, X, AlertTriangle, Copy, ExternalLink } from 'lucide-react';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://tradeul.com';

interface InviteLinkInfo {
    code: string;
    group_name: string;
    group_icon?: string;
    member_count: number;
    is_valid: boolean;
    error?: string;
}

export default function InvitePage() {
    const params = useParams();
    const router = useRouter();
    const { isSignedIn, getToken, isLoaded } = useAuth();
    const code = params.code as string;

    const [linkInfo, setLinkInfo] = useState<InviteLinkInfo | null>(null);
    const [loading, setLoading] = useState(true);
    const [joining, setJoining] = useState(false);
    const [copied, setCopied] = useState(false);
    const [joinResult, setJoinResult] = useState<{
        success: boolean;
        message: string;
        alreadyMember?: boolean;
    } | null>(null);

    const hasAttemptedAutoJoin = useRef(false);

    // Fetch link info
    useEffect(() => {
        async function fetchLinkInfo() {
            try {
                const res = await fetch(`${CHAT_API_URL}/api/chat/invites/invite-links/${code}/info`);
                if (res.ok) {
                    setLinkInfo(await res.json());
                } else {
                    setLinkInfo({
                        code,
                        group_name: '',
                        member_count: 0,
                        is_valid: false,
                        error: 'No se pudo obtener informacion del enlace'
                    });
                }
            } catch (error) {
                setLinkInfo({
                    code,
                    group_name: '',
                    member_count: 0,
                    is_valid: false,
                    error: 'Error de conexion'
                });
            } finally {
                setLoading(false);
            }
        }

        if (code) {
            fetchLinkInfo();
        }
    }, [code]);

    // Handle join
    const handleJoin = useCallback(async () => {
        if (!isSignedIn || joining || joinResult) return;

        setJoining(true);
        try {
            const token = await getToken();
            const res = await fetch(`${CHAT_API_URL}/api/chat/invites/invite-links/${code}/join`, {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            });

            const data = await res.json();

            if (res.ok) {
                setJoinResult({
                    success: true,
                    message: data.message,
                    alreadyMember: data.already_member
                });
                setTimeout(() => {
                    router.push('/workspace');
                }, 1000);
            } else {
                setJoinResult({
                    success: false,
                    message: data.detail || 'Error al unirse al grupo'
                });
            }
        } catch (error) {
            setJoinResult({
                success: false,
                message: 'Error de conexion'
            });
        } finally {
            setJoining(false);
        }
    }, [isSignedIn, joining, joinResult, getToken, code, router]);

    // Auto-join when user signs in and link is valid
    useEffect(() => {
        if (isSignedIn && isLoaded && linkInfo?.is_valid && !joinResult && !hasAttemptedAutoJoin.current) {
            hasAttemptedAutoJoin.current = true;
            handleJoin();
        }
    }, [isSignedIn, isLoaded, linkInfo?.is_valid, joinResult, handleJoin]);

    // Copy link
    const copyLink = async () => {
        try {
            await navigator.clipboard.writeText(`${APP_URL}/invite/${code}`);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (e) {
            console.error('Failed to copy:', e);
        }
    };

    if (loading || !isLoaded) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center">
                <Loader2 className="w-4 h-4 animate-spin text-primary" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
            {/* Compact card */}
            <div className="w-full max-w-xs bg-card border border-border rounded-lg shadow-sm overflow-hidden">
                {/* Header */}
                <div className="px-4 py-3 border-b border-border bg-muted/30">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                            {linkInfo?.group_icon ? (
                                <span className="text-sm">{linkInfo.group_icon}</span>
                            ) : (
                                <Users className="w-4 h-4 text-primary" />
                            )}
                        </div>
                        <div className="flex-1 min-w-0">
                            <h1 className="text-sm font-medium truncate">
                                {linkInfo?.is_valid ? linkInfo.group_name : 'Invitacion'}
                            </h1>
                            {linkInfo?.is_valid && (
                                <p className="text-[10px] text-muted-foreground">
                                    {linkInfo.member_count} miembro{linkInfo.member_count !== 1 ? 's' : ''}
                                </p>
                            )}
                        </div>
                        {linkInfo?.is_valid && (
                            <button
                                onClick={copyLink}
                                className="p-1.5 rounded hover:bg-muted transition-colors"
                                title="Copiar enlace"
                            >
                                {copied ? (
                                    <Check className="w-3.5 h-3.5 text-success" />
                                ) : (
                                    <Copy className="w-3.5 h-3.5 text-muted-foreground" />
                                )}
                            </button>
                        )}
                    </div>
                </div>

                {/* Content */}
                <div className="p-4">
                    {joinResult ? (
                        // Result state
                        <div className="text-center py-2">
                            {joinResult.success ? (
                                <>
                                    <Check className="w-6 h-6 text-success mx-auto mb-2" />
                                    <p className="text-xs font-medium">
                                        {joinResult.alreadyMember ? 'Ya eres miembro' : 'Unido'}
                                    </p>
                                    <p className="text-[10px] text-muted-foreground mt-1">
                                        Redirigiendo...
                                    </p>
                                </>
                            ) : (
                                <>
                                    <X className="w-6 h-6 text-danger mx-auto mb-2" />
                                    <p className="text-xs font-medium">Error</p>
                                    <p className="text-[10px] text-muted-foreground mt-1">
                                        {joinResult.message}
                                    </p>
                                    <button
                                        onClick={() => router.push('/workspace')}
                                        className="mt-3 px-3 py-1.5 text-[10px] bg-muted hover:bg-muted/80 rounded transition-colors"
                                    >
                                        Ir al inicio
                                    </button>
                                </>
                            )}
                        </div>
                    ) : linkInfo?.is_valid ? (
                        // Valid invite
                        <>
                            <p className="text-xs text-muted-foreground text-center mb-3">
                                Te han invitado a unirte
                            </p>

                            {isSignedIn ? (
                                <button
                                    onClick={handleJoin}
                                    disabled={joining}
                                    className="w-full py-2 bg-primary hover:bg-primary/90 text-white rounded text-xs font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5"
                                >
                                    {joining ? (
                                        <>
                                            <Loader2 className="w-3 h-3 animate-spin" />
                                            Uniendo...
                                        </>
                                    ) : (
                                        <>
                                            <ExternalLink className="w-3 h-3" />
                                            Unirse al grupo
                                        </>
                                    )}
                                </button>
                            ) : (
                                <>
                                    <p className="text-[10px] text-muted-foreground text-center mb-2">
                                        Inicia sesion para continuar
                                    </p>
                                    <SignInButton mode="modal">
                                        <button className="w-full py-2 bg-primary hover:bg-primary/90 text-white rounded text-xs font-medium transition-colors">
                                            Iniciar sesion
                                        </button>
                                    </SignInButton>
                                </>
                            )}
                        </>
                    ) : (
                        // Invalid invite
                        <div className="text-center py-2">
                            <AlertTriangle className="w-6 h-6 text-warning mx-auto mb-2" />
                            <p className="text-xs font-medium">Enlace no valido</p>
                            <p className="text-[10px] text-muted-foreground mt-1">
                                {linkInfo?.error || 'Este enlace ha expirado o no existe'}
                            </p>
                            <button
                                onClick={() => router.push('/workspace')}
                                className="mt-3 px-3 py-1.5 text-[10px] bg-muted hover:bg-muted/80 rounded transition-colors"
                            >
                                Ir al inicio
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
