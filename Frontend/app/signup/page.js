'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '../../context/AuthContext';
import AnimatedBackground from '../../components/AnimatedBackground.jsx';
import { motion } from 'framer-motion';
import { Mail, Lock, User, Eye, EyeOff, AlertCircle, CheckCircle } from 'lucide-react';

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [message, setMessage] = useState(null);
  const [messageType, setMessageType] = useState('');

  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
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

    const result = await signup(
      formData.username,
      formData.email,
      formData.password,
      formData.confirmPassword
    );

    if (result.success) {
      setMessageType('success');
      setMessage('✅ Account created successfully! Redirecting to login...');
      setTimeout(() => {
        router.push('/login');
      }, 2000);
    } else {
      setMessageType('error');
      setMessage(result.message);
    }

    setLoading(false);
  };

  return (
    <AnimatedBackground>
      <div className="min-h-screen flex items-center justify-center px-4 pt-24 pb-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-sm"
        >
          <div className="backdrop-blur-md bg-white/10 border border-white/20 rounded-2xl p-6 shadow-2xl">
            <div className="text-center mb-2">
              <div className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500 mb-2">
                AutoSRS.ai
              </div>
              <p className="text-gray-300">Create your account</p>
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

            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Username
                </label>
                <div className="relative">
                  <User size={20} className="absolute left-3 top-3 text-gray-400" />
                  <input
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleChange}
                    placeholder="john_doe"
                    required
                    className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/20 rounded-lg focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-base text-white placeholder-gray-500 transition"
                  />
                </div>
                <p className="text-[10px] text-gray-400 mt-0.5">3-20 chars, letters/numbers/underscore</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Email
                </label>
                <div className="relative">
                  <Mail size={20} className="absolute left-3 top-3 text-gray-400" />
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="john@example.com"
                    required
                    className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/20 rounded-lg focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-base text-white placeholder-gray-500 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Password
                </label>
                <div className="relative">
                  <Lock size={20} className="absolute left-3 top-3 text-gray-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="••••••••"
                    required
                    className="w-full pl-10 pr-10 py-2.5 bg-white/5 border border-white/20 rounded-lg focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-base text-white placeholder-gray-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-300 transition"
                  >
                    {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 mt-0.5">
                  Min 6 chars: Uppercase, lowercase, number, special (!@#$%^&*)
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock size={20} className="absolute left-3 top-3 text-gray-400" />
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    name="confirmPassword"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    placeholder="••••••••"
                    required
                    className="w-full pl-10 pr-10 py-2.5 bg-white/5 border border-white/20 rounded-lg focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-base text-white placeholder-gray-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-300 transition"
                  >
                    {showConfirmPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
              </div>

              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                type="submit"
                disabled={loading}
                className="w-full py-2.5 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 rounded-lg font-medium text-lg text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating Account...' : 'Create Account'}
              </motion.button>
            </form>

            <div className="flex items-center gap-3 my-4">
              <div className="flex-1 h-px bg-white/10"></div>
              <span className="text-sm text-gray-400">or</span>
              <div className="flex-1 h-px bg-white/10"></div>
            </div>

            <p className="text-center text-gray-300">
              Already have an account?{' '}
              <Link href="/login" className="text-blue-400 hover:text-blue-300 font-medium transition">
                Login
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