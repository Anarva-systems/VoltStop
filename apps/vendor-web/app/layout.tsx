import type { Metadata } from "next";
import "./globals.css";
import "./admin.css";
import "./portal-refresh.css";
import "./home.css";
import { VendorAuthProvider } from "@/components/vendor-auth";

export const metadata: Metadata = {
  title: "VoltStop — Better stops for the miles ahead",
  description: "Plan EV journeys and discover partner-listed charging, food and places to stay along the NH-16 pilot corridor.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><VendorAuthProvider>{children}</VendorAuthProvider></body></html>;
}
