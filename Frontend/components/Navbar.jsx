"use client";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { LogOut, User, Bot } from "lucide-react";

// Changed from 'export default function' to 'export function'
export function Navbar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 bg-black/50 backdrop-blur-md border-b border-white/10">
      <Link href="/" className="flex items-center gap-2">
        <div className="w-8 h-8 bg-gradient-to-tr from-blue-500 to-purple-500 rounded-lg flex items-center justify-center">
          <Bot className="text-white" size={20} />
        </div>
        <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">
          AutoSRS.ai
        </span>
      </Link>

      <div className="flex items-center gap-6">
        {user && pathname !== '/login' && pathname !== '/signup' ? (
          <>
            <Link href="/generator" className="flex items-center gap-2 text-gray-300 hover:text-white transition-colors">
              <Bot size={20} />
              <span className="hidden md:inline">Generator</span>
            </Link>
            <div className="flex items-center gap-2 text-gray-300">
              <User size={20} />
              <span className="hidden md:inline">{user.username}</span>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 rounded-lg transition-all"
            >
              <LogOut size={18} />
              <span className="hidden md:inline">Logout</span>
            </button>
          </>
        ) : (
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-sm font-medium text-gray-300 hover:text-white transition-colors">
              Login
            </Link>
            <Link
              href="/signup"
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
            >
              Sign Up
            </Link>
          </div>
        )}
      </div>
    </nav>
  );
}
