import type { Metadata } from "next";
import "./globals.css";
import "./admin.css";
import { VendorAuthProvider } from "@/components/vendor-auth";

export const metadata: Metadata = {
  title: "VoltStop Vendor",
  description: "Manage your VoltStop pitstop bookings and services.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><VendorAuthProvider>{children}</VendorAuthProvider></body></html>;
}
