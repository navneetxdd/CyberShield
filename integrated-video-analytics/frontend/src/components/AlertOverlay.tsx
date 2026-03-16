import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";

interface AlertOverlayProps {
  eventLogs: any[];
  onFlash?: (active: boolean) => void;
  enabled?: boolean;
}

function playBeep() {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);
    oscillator.type = "square";
    oscillator.frequency.setValueAtTime(880, ctx.currentTime);
    gainNode.gain.setValueAtTime(0.15, ctx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    oscillator.start(ctx.currentTime);
    oscillator.stop(ctx.currentTime + 0.25);
  } catch {
    // Audio context not supported
  }
}

export function AlertOverlay({ eventLogs, onFlash, enabled = true }: AlertOverlayProps) {
  const lastSeenRef = useRef<string>("");

  useEffect(() => {
    if (!enabled) return;
    if (!eventLogs || eventLogs.length === 0) return;
    const latest = eventLogs[eventLogs.length - 1];
    if (!latest) return;
    const uid = `${latest.time}-${latest.type}`;
    if (uid === lastSeenRef.current) return;

    const type = (latest.type || "").toUpperCase();
    const isTactical =
      type.includes("TACTICAL") || type.includes("WATCHLIST") ||
      type.includes("BOLO") || type.includes("INTERCEPT");

    if (isTactical) {
      lastSeenRef.current = uid;
      playBeep();
      if (onFlash) {
        onFlash(true);
        setTimeout(() => onFlash(false), 3000);
      }
      toast.error(`⚠ ${latest.type}: ${latest.detail}`, {
        duration: 12000,
        description: "Subject detected on active feed — immediate review required",
      });
    }
  }, [eventLogs]);

  return null;
}
