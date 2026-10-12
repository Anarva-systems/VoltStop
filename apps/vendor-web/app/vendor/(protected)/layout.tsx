"use client";

import { ProtectedPortal, ToastViewport } from "@/components/portal";

export default function VendorPortalLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedPortal><>{children}<ToastViewport/></></ProtectedPortal>;
}
