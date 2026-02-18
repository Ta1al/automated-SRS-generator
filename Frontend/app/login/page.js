'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '../../context/AuthContext';
import AnimatedBackground from '../../components/AnimatedBackground.jsx';
import { motion } from 'framer-motion';
import { Lock, Eye, EyeOff, AlertCircle, CheckCircle } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState(null);
  const [messageType, setMessageType] = useState('');

  const [formData, setFormData] = useState({
    username: '',
    password: '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage(null);

    const result = await login(formData.username, formData.password);

    if (result.success) {
      setMessageType('success');
      setMessage('✅ Login successful! Redirecting...');
      setTimeout(() => {
        router.push('/');
      }, 2000);
    } else {
      setMessageType('error');
      setMessage(result.message);
    }

    setLoading(false);
  };

  return (
    <AnimatedBackground>
      <div className="min-h-screen flex items-center justify-center px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-md"
        >
          <div className="backdrop-blur-md bg-white/10 border border-white/20 rounded-2xl p-8 shadow-2xl">
            <div className="text-center mb-8">
              <div className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500 mb-2">
                AutoSRS.ai
              </div>
              <p className="text-gray-300">Welcome back</p>
            </div>

            {message && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`mb-4 p-4 rounded-lg flex items-start gap-3 ${
                  messageType === 'success'
                    ? 'bg-green-500/20 border border-green-500/50 text-green-300'
                    : 'bg-red-500/20 border border-red-500/50 text-red-300'
                }`}
              >
                {messageType === 'success' ? (
                  <CheckCircle size={20} className="mt-0.5 flex-shrink-0" />
                ) : (
                  <AlertCircle size={20} className="mt-0.5 flex-shrink-0" />
                )}
                <span className="text-sm">{message}</span>
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Username
                </label>
                <div className="relative">
                  <input
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleChange}
                    placeholder="john_doe"
                    required
                    className="w-full px-4 py-2.5 bg-white/5 border border-white/20 rounded-lg focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-white placeholder-gray-500 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Password
                </label>
                <div className="relative">
                  <Lock size={18} className="absolute left-3 top-3 text-gray-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="••••••••"
                    required
                    className="w-full pl-10 pr-10 py-2.5 bg-white/5 border border-white/20 rounded-lg focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-white placeholder-gray-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-3 text-gray-400 hover:text-gray-300 transition"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                type="submit"
                disabled={loading}
                className="w-full py-2.5 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 rounded-lg font-medium text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Logging In...' : 'Login'}
              </motion.button>
            </form>

            <div className="flex items-center gap-3 my-6">
              <div className="flex-1 h-px bg-white/10"></div>
              <span className="text-sm text-gray-400">or</span>
              <div className="flex-1 h-px bg-white/10"></div>
            </div>

            <p className="text-center text-gray-300">
              Don't have an account?{' '}
              <Link href="/signup" className="text-blue-400 hover:text-blue-300 font-medium transition">
                Sign up
              </Link>
            </p>

            <div className="mt-4 text-center">
              <Link href="/" className="text-sm text-gray-400 hover:text-gray-300 transition">
                ← Back to Home
              </Link>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatedBackground>
  );
}