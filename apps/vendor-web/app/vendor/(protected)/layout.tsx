"use client";

import { DialogEscapeBridge, ProtectedPortal, ToastViewport } from "@/components/portal";

export default function VendorPortalLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedPortal><>{children}<ToastViewport/><DialogEscapeBridge/></></ProtectedPortal>;
}
