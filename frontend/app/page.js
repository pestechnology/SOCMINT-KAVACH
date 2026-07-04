"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/cases" : "/login");
  }, [router]);
  return (
    <div className="flex items-center justify-center h-screen text-gray-400">Loading…</div>
  );
}
