import { AuthProvider } from "@/context/AuthContext";
import "./globals.css";
// Note: Humne Navbar ko named import { Navbar } ke sath import kiya hai
import { Navbar } from "@/components/Navbar";

export const metadata = {
  title: "AutoSRS.AI",
  description: "Authentication System",
};

// Yeh 'export default' hona zaroori hai
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <Navbar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
