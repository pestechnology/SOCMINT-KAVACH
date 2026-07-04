"use client";

import { useState, useEffect } from "react";
import Image from "next/image";

export default function PlatformLogo({ platform, width = 16, height = 16, className = "" }) {
  const [errorCount, setErrorCount] = useState(0);

  useEffect(() => {
    setErrorCount(0);
  }, [platform]);

  if (!platform) {
    return <Image src="/logos/generic.svg" width={width} height={height} alt="Generic" className={className} unoptimized />;
  }

  let normalized = String(platform).toLowerCase().trim();
  // Strip protocol and common domain TLDs
  normalized = normalized.replace(/^https?:\/\/(www\.)?/, '').replace(/\.(com|org|net|io|in|co|us|uk|ca|de|jp|fr|au|ru|ch|it|nl|se|no|es|mil|gov|edu|info|biz|dev|app|xyz)(\/.*)?$/, '');
  normalized = normalized.replace(/\s+/g, '-').replace(/[^a-z0-9-_]/g, '');

  const aliases = {
    "twitter": "x",
    "x": "x",
    "hibp": "breach",
    "have-i-been-pwned": "breach",
    "docker-hub": "docker",
    "steamcommunity": "steam",
    "githubgist": "github"
  };

  const base = aliases[normalized] || normalized;

  // Try exact match, then common variants, then generic
  const variants = Array.from(new Set([
    base,
    normalized,
    `${base}-icon`,
    `${base}-logo`,
    "generic"
  ]));

  if (base === "x" || normalized === "twitter") {
    variants.unshift("x", "twitter");
  }
  if (base === "breach" || normalized === "hibp") {
    variants.unshift("hibp", "breach");
  }

  const currentVariant = variants[Math.min(errorCount, variants.length - 1)];
  const src = `/logos/${currentVariant}.svg`;

  return (
    <Image
      src={src}
      width={width}
      height={height}
      alt={platform}
      className={`shrink-0 ${className}`}
      onError={() => {
        if (errorCount < variants.length - 1) {
          setErrorCount(c => c + 1);
        }
      }}
      unoptimized
    />
  );
}
