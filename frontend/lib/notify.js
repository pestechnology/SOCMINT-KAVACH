"use client";
/* lib/notify.js — desktop notification when an investigation finishes.

   Uses the browser's own Notification API: no email server, no webhook, no push
   service, and nothing about the subject leaves the machine. Every call is guarded —
   the API is absent in SSR and on some mobile browsers, and throws in a few of them
   even when present, so a failure here must never break the page it fires from. */

function available() {
  return typeof window !== "undefined" && "Notification" in window;
}

export function permission() {
  return available() ? Notification.permission : "unsupported";
}

/** Ask once, from a user gesture (browsers ignore it otherwise). Resolves to the
 *  resulting permission string; never rejects. */
export async function requestPermission() {
  if (!available()) return "unsupported";
  if (Notification.permission !== "default") return Notification.permission;
  try {
    return await Notification.requestPermission();
  } catch (_) {
    return Notification.permission;
  }
}

/** Fire one notification. Returns false when it could not be shown, so the caller can
 *  fall back to the in-page banner. `tag` collapses repeats for the same case. */
export function notify(title, { body = "", tag = "", onClick } = {}) {
  if (!available() || Notification.permission !== "granted") return false;
  try {
    const n = new Notification(title, { body, tag });
    if (onClick) {
      n.onclick = () => {
        try { window.focus(); } catch (_) {}
        n.close();
        onClick();
      };
    }
    return true;
  } catch (_) {
    return false;   // some browsers require a ServiceWorkerRegistration instead
  }
}
