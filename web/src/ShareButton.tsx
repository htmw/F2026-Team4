import { useEffect, useRef, useState } from "react";

import { CheckIcon, ShareIcon } from "./icons";

// "Share": copies a read-only link to the trip. If the browser won't copy (no permission,
// an old browser), the link is shown selected so it can be copied by hand.
export function ShareButton({ url }: { url: string }) {
  const [state, setState] = useState<"idle" | "copied" | "manual">("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (state === "manual") inputRef.current?.select();
    if (state !== "copied") return;
    const timer = window.setTimeout(() => setState("idle"), 4000);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function share() {
    try {
      await navigator.clipboard.writeText(url);
      setState("copied");
    } catch {
      setState("manual");
    }
  }

  return (
    <span className="share">
      <button type="button" className="button-secondary button-small" onClick={share}>
        {state === "copied" ? <CheckIcon /> : <ShareIcon />}
        {state === "copied" ? "Link copied" : "Share"}
      </button>
      <span className="visually-hidden" role="status">
        {state === "copied" ? "A read-only link to this trip was copied." : ""}
      </span>
      {state === "manual" && (
        <label className="share-manual">
          <span>Copy this link to share a read-only view:</span>
          <input ref={inputRef} readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
        </label>
      )}
    </span>
  );
}
